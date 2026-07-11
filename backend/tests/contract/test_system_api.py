import asyncio
import os
import sqlite3
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

import agent_platform.bootstrap.app_factory as app_factory_module
from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.domain.shared.errors import DomainError
from agent_platform.interfaces.api.errors import PublicHttpError

AUTHORIZATION = {"Authorization": "Bearer local-secret"}
LEAKED_SECRET = "leaked-secret"
RAW_VALIDATOR_MESSAGE = "validator exposed submitted value"
DICTIONARY_KEY_SECRET = "dictionary-key-secret"
DICTIONARY_VALUE_SECRET = "dictionary-value-secret"
RAW_DICTIONARY_ERROR_MESSAGE = "Input should be a valid integer"
TYPE_SECRET_VALUE = "type-secret-value"
PATH_SECRET_MARKER = "PATH-SECRET-MARKER"
OUTER_MIDDLEWARE_SECRET = "outer-middleware-secret"


class _OuterFailureMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        del request, call_next
        raise RuntimeError(OUTER_MIDDLEWARE_SECRET)


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_root=tmp_path, session_token="local-secret")


def _apply_foundation_migration(data_root: Path) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["AGENT_PLATFORM_DATA_ROOT"] = str(data_root)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic local-secret"},
        {"Authorization": "Bearer wrong-secret"},
    ],
)
async def test_health_rejects_invalid_local_sessions(
    tmp_path: Path,
    headers: dict[str, str],
) -> None:
    app = create_app(_settings(tmp_path))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/health", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "error": {
            "code": "auth.invalid_session",
            "message": "Invalid local session",
            "details": {},
            "retryable": False,
        }
    }
    assert "local-secret" not in response.text


@pytest.mark.asyncio
async def test_health_accepts_exact_local_bearer_token(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/health", headers=AUTHORIZATION)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_token", "raw_credential"),
    [
        ("local-secret", b"\xe9"),
        ("local-secret", "秘密".encode()),
    ],
)
async def test_health_rejects_non_ascii_session_tokens_without_server_error(
    tmp_path: Path,
    configured_token: str,
    raw_credential: bytes,
) -> None:
    app = create_app(Settings(data_root=tmp_path, session_token=configured_token))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/health",
            headers=[(b"Authorization", b"Bearer " + raw_credential)],
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.invalid_session"
    assert configured_token not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization_headers",
    [
        [
            (b"Authorization", b"Bearer local-secret"),
            (b"Authorization", b"Bearer wrong-secret"),
        ],
        [
            (b"Authorization", b"Bearer wrong-secret"),
            (b"Authorization", b"Bearer local-secret"),
        ],
    ],
)
async def test_health_rejects_duplicate_authorization_headers(
    tmp_path: Path,
    authorization_headers: list[tuple[bytes, bytes]],
) -> None:
    app = create_app(_settings(tmp_path))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/health",
            headers=authorization_headers,
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.invalid_session"
    assert "local-secret" not in response.text


@pytest.mark.asyncio
async def test_readiness_uses_lifespan_database_and_disposes_it(tmp_path: Path) -> None:
    _apply_foundation_migration(tmp_path)
    app = create_app(_settings(tmp_path))

    async with app.router.lifespan_context(app):
        database = app.state.database
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/readiness", headers=AUTHORIZATION)

        assert app.state.database is database

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ready"}
    assert not hasattr(app.state, "database")


@pytest.mark.asyncio
async def test_readiness_rejects_fresh_unmigrated_database(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/readiness", headers=AUTHORIZATION)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "readiness.unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation_sql",
    [
        "UPDATE alembic_version SET version_num = 'wrong_revision'",
        "DELETE FROM alembic_version",
        "DROP TABLE event_log",
        "DROP TABLE outbox_events",
    ],
)
async def test_readiness_rejects_incomplete_or_wrong_foundation_schema(
    tmp_path: Path,
    mutation_sql: str,
) -> None:
    settings = _settings(tmp_path)
    _apply_foundation_migration(tmp_path)
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(mutation_sql)

    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/readiness", headers=AUTHORIZATION)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "readiness.unavailable"


@pytest.mark.asyncio
async def test_readiness_returns_stable_error_when_database_is_unavailable(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path))

    class UnavailableEngine:
        def connect(self) -> None:
            raise RuntimeError("database-secret")

    class UnavailableDatabase:
        engine = UnavailableEngine()

    async with app.router.lifespan_context(app):
        app.state.database = UnavailableDatabase()
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/readiness", headers=AUTHORIZATION)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "readiness.unavailable",
            "message": "Service not ready",
            "details": {},
            "retryable": True,
        }
    }
    assert "database-secret" not in response.text


@pytest.mark.asyncio
async def test_lifespan_disposal_resists_repeated_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispose_started = asyncio.Event()
    allow_dispose = asyncio.Event()
    dispose_completed = asyncio.Event()

    class ControlledDatabase:
        async def dispose(self) -> None:
            dispose_started.set()
            await allow_dispose.wait()
            dispose_completed.set()

    database = ControlledDatabase()
    monkeypatch.setattr(app_factory_module, "create_database", lambda _: database)
    app = create_app(_settings(tmp_path))
    lifespan_entered = asyncio.Event()

    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            lifespan_entered.set()
            await asyncio.Event().wait()

    lifespan_task = asyncio.create_task(run_lifespan())
    await asyncio.wait_for(lifespan_entered.wait(), timeout=1)

    lifespan_task.cancel()
    await asyncio.wait_for(dispose_started.wait(), timeout=1)
    lifespan_task.cancel()
    await asyncio.sleep(0)
    escaped_before_dispose = lifespan_task.done()
    state_removed_before_dispose = not hasattr(app.state, "database")

    allow_dispose.set()
    with pytest.raises(asyncio.CancelledError):
        await lifespan_task

    assert escaped_before_dispose is False
    assert state_removed_before_dispose is False
    assert dispose_completed.is_set()
    assert not hasattr(app.state, "database")


@pytest.mark.asyncio
async def test_domain_errors_use_stable_conflict_envelope(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async def raise_domain_error() -> None:
        raise DomainError(
            code="workflow.invalid_state",
            message="Workflow state conflict",
            details={
                "state": "completed",
                "authorization": "Bearer domain-secret",
                "nested": {"token": "domain-token-secret"},
                "cause": RuntimeError("domain-exception-secret"),
            },
        )

    app.add_api_route("/test/domain-error", raise_domain_error, methods=["GET"])

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/test/domain-error")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "workflow.invalid_state",
            "message": "Workflow state conflict",
            "details": {
                "state": "completed",
                "authorization": "***",
                "nested": {"token": "***"},
                "cause": None,
            },
            "retryable": False,
        }
    }
    assert "domain-secret" not in response.text
    assert "domain-token-secret" not in response.text
    assert "domain-exception-secret" not in response.text


class _ValidationPayload(BaseModel):
    count: int = Field(gt=0)


class _LeakyValidationPayload(BaseModel):
    secret: str

    @field_validator("secret")
    @classmethod
    def reject_secret(cls, value: str) -> str:
        raise ValueError(f"{RAW_VALIDATOR_MESSAGE}: {value}")


class _DictionaryKeyValidationPayload(BaseModel):
    values: dict[int, int]


class _DynamicTypeValidationPayload(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def reject_value(cls, value: str) -> str:
        raise PydanticCustomError(f"custom_{value}", "Invalid custom value")


@pytest.mark.asyncio
async def test_request_validation_errors_do_not_echo_input(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async def validate_payload(payload: _ValidationPayload) -> None:
        del payload

    app.add_api_route("/test/validation", validate_payload, methods=["POST"])
    raw_secret = "validation-secret-value"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/test/validation",
            json={"count": raw_secret},
        )

    payload = response.json()
    assert response.status_code == 422
    assert payload["error"]["code"] == "request.validation_failed"
    assert payload["error"]["message"] == "Request validation failed"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["details"] == {}
    assert raw_secret not in response.text


@pytest.mark.asyncio
async def test_request_validation_sanitizes_validator_messages_and_context(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path))

    async def validate_payload(payload: _LeakyValidationPayload) -> None:
        del payload

    app.add_api_route("/test/leaky-validation", validate_payload, methods=["POST"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/test/leaky-validation",
            json={"secret": LEAKED_SECRET},
        )

    payload = response.json()
    assert response.status_code == 422
    assert payload["error"]["code"] == "request.validation_failed"
    assert payload["error"]["details"] == {}
    assert LEAKED_SECRET not in response.text
    assert RAW_VALIDATOR_MESSAGE not in response.text


@pytest.mark.asyncio
async def test_request_validation_does_not_echo_dictionary_keys(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async def validate_payload(payload: _DictionaryKeyValidationPayload) -> None:
        del payload

    app.add_api_route(
        "/test/dictionary-key-validation",
        validate_payload,
        methods=["POST"],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/test/dictionary-key-validation",
            json={"values": {DICTIONARY_KEY_SECRET: DICTIONARY_VALUE_SECRET}},
        )

    payload = response.json()
    assert response.status_code == 422
    assert payload["error"]["code"] == "request.validation_failed"
    assert payload["error"]["details"] == {}
    assert DICTIONARY_KEY_SECRET not in response.text
    assert DICTIONARY_VALUE_SECRET not in response.text
    assert RAW_DICTIONARY_ERROR_MESSAGE not in response.text


@pytest.mark.asyncio
async def test_request_validation_does_not_echo_dynamic_error_types(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async def validate_payload(payload: _DynamicTypeValidationPayload) -> None:
        del payload

    app.add_api_route(
        "/test/dynamic-type-validation",
        validate_payload,
        methods=["POST"],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/test/dynamic-type-validation",
            json={"value": TYPE_SECRET_VALUE},
        )

    payload = response.json()
    assert response.status_code == 422
    assert payload["error"]["code"] == "request.validation_failed"
    assert payload["error"]["details"] == {}
    assert TYPE_SECRET_VALUE not in response.text
    assert f"custom_{TYPE_SECRET_VALUE}" not in response.text


@pytest.mark.asyncio
async def test_structured_http_error_preserves_nonstandard_status(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async def raise_nonstandard_http_error() -> None:
        raise PublicHttpError(
            status_code=499,
            code="client.closed",
            message="Client closed",
        )

    app.add_api_route(
        "/test/nonstandard-http-error",
        raise_nonstandard_http_error,
        methods=["GET"],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/test/nonstandard-http-error")

    assert response.status_code == 499
    assert response.json() == {
        "error": {
            "code": "client.closed",
            "message": "Client closed",
            "details": {},
            "retryable": False,
        }
    }


@pytest.mark.asyncio
async def test_generic_http_exception_does_not_echo_untrusted_detail(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async def raise_untrusted_http_error() -> None:
        raise HTTPException(
            status_code=418,
            detail={
                "code": "auth.secret",
                "message": "Bearer framework-secret",
                "details": {
                    "authorization": "Bearer framework-secret",
                    "token": "framework-token-secret",
                },
                "retryable": True,
            },
            headers={"X-Safe-Header": "preserved"},
        )

    app.add_api_route(
        "/test/untrusted-http-error",
        raise_untrusted_http_error,
        methods=["GET"],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/test/untrusted-http-error")

    assert response.status_code == 418
    assert response.headers["x-safe-header"] == "preserved"
    assert response.json() == {
        "error": {
            "code": "http.error",
            "message": "I'm a Teapot",
            "details": {},
            "retryable": False,
        }
    }
    assert "framework-secret" not in response.text
    assert "framework-token-secret" not in response.text


@pytest.mark.asyncio
async def test_streaming_error_after_response_start_closes_without_propagating(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(_settings(tmp_path))

    async def broken_stream() -> AsyncIterator[bytes]:
        yield b"partial-body"
        raise RuntimeError("streaming-secret local-secret")

    async def stream_response() -> StreamingResponse:
        return StreamingResponse(broken_stream())

    app.add_api_route("/test/streaming-error", stream_response, methods=["GET"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/test/streaming-error")

    captured_logs = capsys.readouterr()
    assert response.status_code == 200
    assert response.content == b"partial-body"
    assert "streaming-secret" not in captured_logs.out
    assert "streaming-secret" not in captured_logs.err
    assert "local-secret" not in captured_logs.out
    assert "local-secret" not in captured_logs.err


@pytest.mark.asyncio
async def test_pre_start_unhandled_errors_are_generic_and_do_not_leak_secrets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(_settings(tmp_path))

    async def raise_unhandled_error() -> None:
        raise RuntimeError("internal-secret local-secret")

    app.add_api_route("/test/unhandled-error", raise_unhandled_error, methods=["GET"])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/test/unhandled-error",
            headers=AUTHORIZATION,
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal.error",
            "message": "Internal server error",
            "details": {},
            "retryable": False,
        }
    }
    captured_logs = capsys.readouterr()
    assert "internal-secret" not in response.text
    assert "local-secret" not in response.text
    assert "internal-secret" not in captured_logs.out
    assert "internal-secret" not in captured_logs.err
    assert "local-secret" not in captured_logs.out
    assert "local-secret" not in captured_logs.err


@pytest.mark.asyncio
async def test_unexpected_error_logs_do_not_include_raw_request_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(_settings(tmp_path))

    async def raise_path_error(marker: str) -> None:
        del marker
        raise RuntimeError("path failure")

    app.add_api_route("/test/path-error/{marker}", raise_path_error, methods=["GET"])
    requested_path = f"/test/path-error/{PATH_SECRET_MARKER}"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(requested_path)

    captured_logs = capsys.readouterr()
    assert response.status_code == 500
    assert PATH_SECRET_MARKER not in captured_logs.out
    assert PATH_SECRET_MARKER not in captured_logs.err
    assert requested_path not in captured_logs.out
    assert requested_path not in captured_logs.err


@pytest.mark.asyncio
async def test_error_boundary_wraps_middleware_added_after_factory_creation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(_settings(tmp_path))
    app.add_middleware(_OuterFailureMiddleware)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/health", headers=AUTHORIZATION)

    captured_logs = capsys.readouterr()
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal.error"
    assert OUTER_MIDDLEWARE_SECRET not in response.text
    assert OUTER_MIDDLEWARE_SECRET not in captured_logs.out
    assert OUTER_MIDDLEWARE_SECRET not in captured_logs.err
