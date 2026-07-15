import os
import subprocess
import sys
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
from agent_platform.domain.contracts import STAGE_ORDER
from agent_platform.domain.model_runtime import ModelProvider
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


@pytest.mark.asyncio
async def test_fake_model_completes_all_five_stages_with_gates_and_handoffs(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n",
        encoding="utf-8",
    )
    (workspace / "tests" / "test_smoke.py").write_text(
        "def test_smoke():\n    assert True\n",
        encoding="utf-8",
    )
    _migrate(data_root)
    settings = _settings(data_root)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            project = await client.post(
                "/api/v1/projects",
                headers=AUTHORIZATION,
                json={
                    "name": "Five-stage project",
                    "goal": "Complete the backend V1 workflow",
                    "local_working_directory": str(workspace),
                    "workspace_mode": "direct",
                    "correlation_id": "five_stage_project",
                },
            )
            project_id = project.json()["registration"]["project"]["id"]
            await client.post(
                f"/api/v1/projects/{project_id}/preflight",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "five_stage_preflight"},
            )
            created = await client.post(
                f"/api/v1/projects/{project_id}/workflows",
                headers=AUTHORIZATION,
                json={"title": "Five-stage V1", "correlation_id": "five_stage_create"},
            )
            initial = created.json()
            workflow_id = initial["workflow"]["id"]
            rooms = initial["rooms"]
            await client.post(
                f"/api/v1/workflows/{workflow_id}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "five_stage_start"},
            )
            mode = await client.post(
                f"/api/v1/workflows/{workflow_id}/mode",
                headers=AUTHORIZATION,
                json={
                    "mode": "autonomous",
                    "expected_version": 2,
                    "correlation_id": "five_stage_autonomous",
                },
            )
            assert mode.status_code == 200, mode.text

            configuration = app.state.model_configuration_service
            profile_ids: list[str] = []
            secrets: dict[str, str] = {}
            for index, role in enumerate(("primary", "reviewer_a", "reviewer_b")):
                credential_ref = f"credential.five_stage.{role}"
                profile = await configuration.create_profile(
                    name=f"Five-stage {role}",
                    provider=ModelProvider.FAKE,
                    base_url="https://fake.invalid/v1",
                    model=f"fake-{role}",
                    credential_ref=credential_ref,
                    masked_hint=f"****{index}",
                    correlation_id=f"five_stage_profile_{role}",
                )
                profile_ids.append(profile.id)
                secrets[credential_ref] = f"secret-{role}"
            for room in rooms:
                await configuration.assign_room(
                    room["id"],
                    primary_profile_id=profile_ids[0],
                    reviewer_a_profile_id=profile_ids[1],
                    reviewer_b_profile_id=profile_ids[2],
                    expected_version=None,
                    correlation_id=f"five_stage_assign_{room['stage']}",
                )
            fake = ScriptedFakeModelAdapter(
                tuple(
                    FakeModelScript((f"fake-output-{index}",))
                    for index in range(len(STAGE_ORDER) * 4)
                )
            )
            runtime = AgentRuntimeService(
                app.state.database,
                settings,
                InMemorySecretStore(secrets),
                (fake,),
                ModelOutputStore(settings.model_output_root, max_output_bytes=100_000),
                PromptComposer(PackageRoleCardLoader()),
                ContextBuilder(max_characters=10_000),
                RollingSummaryBuilder(trigger_characters=2000, max_summary_characters=1000),
                AgentRunRegistry(),
            )
            app.state.agent_runtime_service = runtime

            handoff_ids: list[str] = []
            for index, stage in enumerate(STAGE_ORDER):
                snapshot_response = await client.get(
                    f"/api/v1/workflows/{workflow_id}", headers=AUTHORIZATION
                )
                snapshot = snapshot_response.json()
                workflow = snapshot["workflow"]
                current_run = next(
                    run
                    for run in snapshot["stage_runs"]
                    if run["stage"] == stage.value and run["state"] == "ready"
                )
                current_room = next(
                    room for room in snapshot["rooms"] if room["stage_run_id"] == current_run["id"]
                )
                transition_url = f"/api/v1/workflows/{workflow_id}/stages/{stage.value}/transition"
                discussing = await client.post(
                    transition_url,
                    headers=AUTHORIZATION,
                    json={
                        "target_state": "discussing",
                        "expected_workflow_version": workflow["version"],
                        "expected_stage_version": current_run["version"],
                        "correlation_id": f"five_stage_{stage.value}_discussing",
                    },
                )
                assert discussing.status_code == 200, discussing.text
                created_run = await client.post(
                    f"/api/v1/rooms/{current_room['id']}/agent-runs",
                    headers=AUTHORIZATION,
                    json={
                        "request_key": f"formal-{stage.value}-request-0001",
                        "formal": True,
                        "correlation_id": f"five_stage_{stage.value}_run",
                    },
                )
                assert created_run.status_code == 200, created_run.text
                streamed = await client.post(
                    f"/api/v1/agent-runs/{created_run.json()['run']['id']}/stream",
                    headers=AUTHORIZATION,
                    json={
                        "instruction": f"Produce the {stage.value} deliverable",
                        "correlation_id": f"five_stage_{stage.value}_stream",
                    },
                )
                assert streamed.status_code == 200, streamed.text
                producing = await client.post(
                    transition_url,
                    headers=AUTHORIZATION,
                    json={
                        "target_state": "producing",
                        "expected_workflow_version": discussing.json()["workflow"]["version"],
                        "expected_stage_version": discussing.json()["stage_run"]["version"],
                        "correlation_id": f"five_stage_{stage.value}_producing",
                    },
                )
                assert producing.status_code == 200, producing.text
                relative_path = f"artifacts/{stage.value}/{stage.value}.md"
                artifact_path = workspace.joinpath(*relative_path.split("/"))
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                artifact_path.write_text(
                    f"# {stage.value}\n\nCompleted by fake models.\n",
                    encoding="utf-8",
                )
                version = await client.post(
                    f"/api/v1/stage-runs/{current_run['id']}/artifact-versions",
                    headers=AUTHORIZATION,
                    json={
                        "name": f"{stage.value} deliverable",
                        "relative_path": relative_path,
                        "correlation_id": f"five_stage_{stage.value}_artifact",
                    },
                )
                assert version.status_code == 201, version.text
                p2r = await client.post(
                    transition_url,
                    headers=AUTHORIZATION,
                    json={
                        "target_state": "p2r_reviewing",
                        "expected_workflow_version": producing.json()["workflow"]["version"],
                        "expected_stage_version": producing.json()["stage_run"]["version"],
                        "correlation_id": f"five_stage_{stage.value}_p2r",
                    },
                )
                assert p2r.status_code == 200, p2r.text
                checking = await client.post(
                    transition_url,
                    headers=AUTHORIZATION,
                    json={
                        "target_state": "quality_checking",
                        "expected_workflow_version": p2r.json()["workflow"]["version"],
                        "expected_stage_version": p2r.json()["stage_run"]["version"],
                        "correlation_id": f"five_stage_{stage.value}_checking",
                    },
                )
                assert checking.status_code == 200, checking.text
                gate = await client.post(
                    f"/api/v1/stage-runs/{current_run['id']}/quality-gates",
                    headers=AUTHORIZATION,
                    json={
                        "artifact_version_ids": [version.json()["version"]["id"]],
                        "correlation_id": f"five_stage_{stage.value}_gate",
                    },
                )
                assert gate.status_code == 201, gate.text
                assert gate.json()["gate"]["status"] == "pass"
                assert gate.json()["gate"]["resolution"] == "automatic"
                assert gate.json()["handoff"] is not None
                handoff_ids.append(gate.json()["handoff"]["id"])
                assert gate.json()["handoff"]["from_stage"] == stage.value
                if index + 1 < len(STAGE_ORDER):
                    assert gate.json()["handoff"]["to_stage"] == STAGE_ORDER[index + 1].value
                else:
                    assert gate.json()["handoff"]["to_stage"] is None

            completed = await client.get(f"/api/v1/workflows/{workflow_id}", headers=AUTHORIZATION)
            handoffs = await client.get(
                f"/api/v1/workflows/{workflow_id}/handoffs", headers=AUTHORIZATION
            )
            artifacts = await client.get(
                f"/api/v1/workflows/{workflow_id}/artifacts", headers=AUTHORIZATION
            )

    assert completed.json()["workflow"]["status"] == "completed"
    assert all(run["state"] == "completed" for run in completed.json()["stage_runs"])
    assert [handoff["id"] for handoff in handoffs.json()["handoffs"]] == handoff_ids
    assert len(artifacts.json()["versions"]) == 5
    assert all(version["status"] == "locked" for version in artifacts.json()["versions"])
    assert len(fake.invocations) == 20
