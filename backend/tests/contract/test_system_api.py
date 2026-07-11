from pathlib import Path

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field, field_validator

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.domain.shared.errors import DomainError

AUTHORIZATION = {"Authorization": "Bearer local-secret"}
LEAKED_SECRET = "leaked-secret"
RAW_VALIDATOR_MESSAGE = "validator exposed submitted value"


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_root=tmp_path, session_token="local-secret")


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
async def test_readiness_uses_lifespan_database_and_disposes_it(tmp_path: Path) -> None:
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
async def test_domain_errors_use_stable_conflict_envelope(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async def raise_domain_error() -> None:
        raise DomainError(
            code="workflow.invalid_state",
            message="Workflow state conflict",
            details={"state": "completed"},
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
            "details": {"state": "completed"},
            "retryable": False,
        }
    }


class _ValidationPayload(BaseModel):
    count: int = Field(gt=0)


class _LeakyValidationPayload(BaseModel):
    secret: str

    @field_validator("secret")
    @classmethod
    def reject_secret(cls, value: str) -> str:
        raise ValueError(f"{RAW_VALIDATOR_MESSAGE}: {value}")


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
    assert payload["error"]["details"]["errors"]
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
    errors = payload["error"]["details"]["errors"]
    assert response.status_code == 422
    assert payload["error"]["code"] == "request.validation_failed"
    assert errors
    assert LEAKED_SECRET not in response.text
    assert RAW_VALIDATOR_MESSAGE not in response.text
    assert all(set(error) == {"location", "type"} for error in errors)
    assert all(isinstance(part, str | int) for error in errors for part in error["location"])


@pytest.mark.asyncio
async def test_structured_http_error_preserves_nonstandard_status(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async def raise_nonstandard_http_error() -> None:
        raise HTTPException(
            status_code=499,
            detail={
                "code": "client.closed",
                "message": "Client closed",
                "details": {},
                "retryable": False,
            },
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
async def test_unhandled_errors_are_generic_and_do_not_leak_secrets(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))

    async def raise_unhandled_error() -> None:
        raise RuntimeError("internal-secret local-secret")

    app.add_api_route("/test/unhandled-error", raise_unhandled_error, methods=["GET"])

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
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
    assert "internal-secret" not in response.text
    assert "local-secret" not in response.text
