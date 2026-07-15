import asyncio
import json
import os
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agent_platform.application.model_runtime import (
    AgentRunRegistry,
    AgentRuntimeService,
    ContextBuilder,
    PromptComposer,
    RollingSummaryBuilder,
)
from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.domain.model_runtime import AgentRunStatus, ModelProvider
from agent_platform.domain.shared.errors import DomainError
from agent_platform.infrastructure.model_runtime import (
    FakeModelScript,
    InMemorySecretStore,
    ModelOutputStore,
    ScriptedFakeModelAdapter,
)
from agent_platform.infrastructure.resources.role_cards import PackageRoleCardLoader

AUTHORIZATION = {"Authorization": "Bearer local-secret"}
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _migrate(data_root: Path) -> None:
    environment = os.environ.copy()
    environment["AGENT_PLATFORM_DATA_ROOT"] = str(data_root)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _settings(data_root: Path) -> Settings:
    return Settings(
        data_root=data_root,
        session_token="local-secret",
        worker_heartbeat_timeout_seconds=1.0,
        worker_watchdog_interval_seconds=0.1,
        outbox_poll_interval_seconds=0.01,
        outbox_lease_seconds=1.0,
        outbox_publish_timeout_seconds=0.5,
        model_summary_trigger_characters=2000,
        model_summary_max_characters=1000,
        model_context_max_characters=10_000,
    )


async def _ready_room(client: AsyncClient, workspace: Path) -> tuple[str, str]:
    project = await client.post(
        "/api/v1/projects",
        headers=AUTHORIZATION,
        json={
            "name": "Agent runtime project",
            "goal": "Exercise P0 P1 P2R",
            "local_working_directory": str(workspace),
            "workspace_mode": "direct",
            "correlation_id": "runtime_project_create",
        },
    )
    project_id = project.json()["registration"]["project"]["id"]
    preflight = await client.post(
        f"/api/v1/projects/{project_id}/preflight",
        headers=AUTHORIZATION,
        json={"expected_version": 1, "correlation_id": "runtime_preflight"},
    )
    assert preflight.status_code == 200
    workflow = await client.post(
        f"/api/v1/projects/{project_id}/workflows",
        headers=AUTHORIZATION,
        json={"title": "Agent runtime", "correlation_id": "runtime_workflow"},
    )
    snapshot = workflow.json()
    workflow_id = snapshot["workflow"]["id"]
    room_id = snapshot["rooms"][0]["id"]
    started = await client.post(
        f"/api/v1/workflows/{workflow_id}/start",
        headers=AUTHORIZATION,
        json={"expected_version": 1, "correlation_id": "runtime_start"},
    )
    assert started.status_code == 200
    discussing = await client.post(
        f"/api/v1/workflows/{workflow_id}/stages/planner/transition",
        headers=AUTHORIZATION,
        json={
            "target_state": "discussing",
            "expected_workflow_version": 2,
            "expected_stage_version": 1,
            "correlation_id": "runtime_discussing",
        },
    )
    assert discussing.status_code == 200
    return workflow_id, room_id


def _runtime(
    app: object,
    settings: Settings,
    fake: ScriptedFakeModelAdapter,
    secrets: InMemorySecretStore,
) -> AgentRuntimeService:
    database = app.state.database  # type: ignore[attr-defined]
    return AgentRuntimeService(
        database,
        settings,
        secrets,
        (fake,),
        ModelOutputStore(settings.model_output_root, max_output_bytes=100_000),
        PromptComposer(PackageRoleCardLoader()),
        ContextBuilder(max_characters=10_000),
        RollingSummaryBuilder(trigger_characters=2000, max_summary_characters=1000),
        AgentRunRegistry(),
    )


async def _profiles_and_assignment(
    app: object, room_id: str
) -> tuple[dict[str, str], InMemorySecretStore]:
    configuration = app.state.model_configuration_service  # type: ignore[attr-defined]
    profile_ids: dict[str, str] = {}
    secret_values: dict[str, str] = {}
    for name in ("primary", "reviewer_a", "reviewer_b"):
        credential_ref = f"credential.{name}"
        profile = await configuration.create_profile(
            name=name,
            provider=ModelProvider.FAKE,
            base_url="https://fake.invalid/v1",
            model=f"fake-{name}",
            credential_ref=credential_ref,
            masked_hint=f"****{name[-1]}",
            correlation_id=f"profile_{name}",
        )
        profile_ids[name] = profile.id
        secret_values[credential_ref] = f"secret-value-{name}"
    await configuration.assign_room(
        room_id,
        primary_profile_id=profile_ids["primary"],
        reviewer_a_profile_id=profile_ids["reviewer_a"],
        reviewer_b_profile_id=profile_ids["reviewer_b"],
        expected_version=None,
        correlation_id="assign_models",
    )
    return profile_ids, InMemorySecretStore(secret_values)


@pytest.mark.asyncio
async def test_formal_agent_run_executes_primary_two_independent_reviews_and_reconciliation(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _migrate(data_root)
    settings = _settings(data_root)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            _, room_id = await _ready_room(client, workspace)
            profile_ids, secrets = await _profiles_and_assignment(app, room_id)
            fake = ScriptedFakeModelAdapter(
                (
                    FakeModelScript(("draft ", "answer"), input_tokens=10, output_tokens=2),
                    FakeModelScript(("review-a",), input_tokens=4, output_tokens=1),
                    FakeModelScript(("review-b",), input_tokens=5, output_tokens=1),
                    FakeModelScript(("final answer",), input_tokens=12, output_tokens=2),
                )
            )
            runtime = _runtime(app, settings, fake, secrets)
            app.state.agent_runtime_service = runtime
            configuration = app.state.model_configuration_service
            await configuration.assign_room(
                room_id,
                primary_profile_id=profile_ids["primary"],
                reviewer_a_profile_id=None,
                reviewer_b_profile_id=None,
                expected_version=1,
                correlation_id="assign_primary_only",
            )
            with pytest.raises(DomainError, match="Reviewer A and Reviewer B"):
                await runtime.create_run(
                    room_id,
                    request_key="formal-missing-reviewers",
                    formal=True,
                    correlation_id="formal_missing_reviewers",
                )
            await configuration.assign_room(
                room_id,
                primary_profile_id=profile_ids["primary"],
                reviewer_a_profile_id=profile_ids["reviewer_a"],
                reviewer_b_profile_id=profile_ids["reviewer_b"],
                expected_version=2,
                correlation_id="assign_dual_reviewers",
            )
            profiles_response = await client.get(
                "/api/v1/model-profiles",
                headers=AUTHORIZATION,
            )
            assignment_response = await client.get(
                f"/api/v1/rooms/{room_id}/model-assignment",
                headers=AUTHORIZATION,
            )
            assert len(profiles_response.json()["profiles"]) == 3
            assert assignment_response.status_code == 200
            created_response = await client.post(
                f"/api/v1/rooms/{room_id}/agent-runs",
                headers=AUTHORIZATION,
                json={
                    "request_key": "formal-run-request-0001",
                    "formal": True,
                    "correlation_id": "formal_run_create",
                },
            )
            assert created_response.status_code == 200, created_response.text
            run_id = created_response.json()["run"]["id"]
            stream_response = await client.post(
                f"/api/v1/agent-runs/{run_id}/stream",
                headers=AUTHORIZATION,
                json={
                    "instruction": "Produce the plan",
                    "correlation_id": "formal_run_stream",
                },
            )
            assert stream_response.status_code == 200, stream_response.text
            frames = [json.loads(line) for line in stream_response.text.splitlines()]
            snapshot = await runtime.get_run(run_id)
            output_response = await client.get(
                f"/api/v1/agent-runs/{run_id}/output",
                headers=AUTHORIZATION,
            )
            output = output_response.text
            messages = await app.state.workflow_service.list_messages(  # type: ignore[attr-defined]
                room_id,
                after_sequence=0,
                limit=100,
            )
            duplicate_response = await client.post(
                f"/api/v1/rooms/{room_id}/agent-runs",
                headers=AUTHORIZATION,
                json={
                    "request_key": "formal-run-request-0001",
                    "formal": True,
                    "correlation_id": "formal_run_duplicate",
                },
            )

    assert snapshot.run.status is AgentRunStatus.SUCCEEDED
    assert [(call.role.value, call.phase.value) for call in snapshot.calls] == [
        ("primary", "p0"),
        ("reviewer_a", "p1"),
        ("reviewer_b", "p1"),
        ("primary", "p2r"),
    ]
    assert len(snapshot.usage) == 4
    assert output == "final answer"
    assert [message.content for message in messages] == ["Produce the plan", "final answer"]
    assert frames[-1]["status"] == AgentRunStatus.SUCCEEDED.value
    assert len(fake.invocations) == 4
    reviewer_b_prompt = fake.invocations[2].model_dump_json()
    assert "review-a" not in reviewer_b_prompt
    reconciliation_prompt = fake.invocations[3].model_dump_json()
    assert "review-a" in reconciliation_prompt and "review-b" in reconciliation_prompt

    assert duplicate_response.json()["created"] is False
    assert duplicate_response.json()["run"]["id"] == run_id
    assert len(fake.invocations) == 4
    with pytest.raises(DomainError, match="different parameters"):
        await runtime.create_run(
            room_id,
            request_key="formal-run-request-0001",
            formal=False,
            correlation_id="formal_run_idempotency_conflict",
        )

    secret_bytes = b"secret-value-"
    assert all(
        secret_bytes not in path.read_bytes() for path in data_root.rglob("*") if path.is_file()
    )

    restarted = create_app(settings)
    async with restarted.router.lifespan_context(restarted):
        async with AsyncClient(
            transport=ASGITransport(app=restarted),
            base_url="http://test",
        ) as client:
            persisted = await client.get(
                f"/api/v1/agent-runs/{run_id}",
                headers=AUTHORIZATION,
            )
            persisted_output = await client.get(
                f"/api/v1/agent-runs/{run_id}/output",
                headers=AUTHORIZATION,
            )
    assert persisted.json()["run"]["status"] == "succeeded"
    assert persisted_output.text == "final answer"


@pytest.mark.asyncio
async def test_reviewer_failure_is_partial_and_preserves_primary_output(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _migrate(data_root)
    settings = _settings(data_root)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            _, room_id = await _ready_room(client, workspace)
            _, secrets = await _profiles_and_assignment(app, room_id)
            fake = ScriptedFakeModelAdapter(
                (
                    FakeModelScript(("primary draft",)),
                    FakeModelScript(("partial review",), error_code="model.reviewer_a_failed"),
                    FakeModelScript(("review-b",)),
                )
            )
            runtime = _runtime(app, settings, fake, secrets)
            creation = await runtime.create_run(
                room_id,
                request_key="partial-run-request-01",
                formal=True,
                correlation_id="partial_create",
            )

            _ = [
                frame
                async for frame in runtime.stream_run(
                    creation.run.id,
                    instruction="Produce a reviewed answer",
                    correlation_id="partial_stream",
                )
            ]
            snapshot = await runtime.get_run(creation.run.id)
            output = await runtime.get_output(creation.run.id)

    assert snapshot.run.status is AgentRunStatus.PARTIAL_FAILURE
    assert snapshot.run.error_code == "agent_run.reviewer_failed"
    assert output == "primary draft"
    assert len(snapshot.calls) == 3
    assert len(fake.invocations) == 3


@pytest.mark.asyncio
async def test_cancellation_reaches_adapter_and_persists_terminal_states(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _migrate(data_root)
    settings = _settings(data_root)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            _, room_id = await _ready_room(client, workspace)
            _, secrets = await _profiles_and_assignment(app, room_id)
            fake = ScriptedFakeModelAdapter((FakeModelScript(("slow",), delay_seconds=30),))
            runtime = _runtime(app, settings, fake, secrets)
            creation = await runtime.create_run(
                room_id,
                request_key="cancel-run-request-001",
                formal=False,
                correlation_id="cancel_create",
            )
            with pytest.raises(DomainError, match="active agent run"):
                await runtime.create_run(
                    room_id,
                    request_key="cancel-run-request-002",
                    formal=False,
                    correlation_id="cancel_duplicate_active",
                )
            stream = runtime.stream_run(
                creation.run.id,
                instruction="Long operation",
                correlation_id="cancel_stream",
            )
            assert (await anext(stream)).type.value == "run_started"
            assert (await anext(stream)).type.value == "call_started"
            pending = asyncio.create_task(anext(stream))
            await asyncio.sleep(0.02)

            await runtime.cancel_run(creation.run.id)
            with suppress(asyncio.CancelledError):
                await pending
            await stream.aclose()
            snapshot = await runtime.get_run(creation.run.id)

    assert fake.cancellation_observed is True
    assert snapshot.run.status is AgentRunStatus.CANCELLED
    assert snapshot.calls[0].status.value == "cancelled"
