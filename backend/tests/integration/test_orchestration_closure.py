import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.domain.contracts import STAGE_ORDER
from agent_platform.infrastructure.model_runtime import InMemorySecretStore

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
        model_context_max_characters=40_000,
        model_summary_trigger_characters=20_000,
        model_summary_max_characters=10_000,
    )


@pytest.mark.asyncio
async def test_high_level_orchestration_completes_all_five_stages(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    workspace.joinpath("README.md").write_text("# Orchestration fixture\n", encoding="utf-8")
    _migrate(data_root)
    secrets = {
        "credential.primary": "fake-primary-secret",
        "credential.reviewer_a": "fake-reviewer-a-secret",
        "credential.reviewer_b": "fake-reviewer-b-secret",
    }
    app = create_app(_settings(data_root), secret_store=InMemorySecretStore(secrets))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            project_response = await client.post(
                "/api/v1/projects",
                headers=AUTHORIZATION,
                json={
                    "name": "Orchestration project",
                    "goal": "Complete the real high-level delivery path",
                    "local_working_directory": str(workspace),
                    "workspace_mode": "direct",
                    "correlation_id": "orchestration_project_create",
                },
            )
            assert project_response.status_code == 201, project_response.text
            registration = project_response.json()["registration"]
            project_id = registration["project"]["id"]
            preflight = await client.post(
                f"/api/v1/projects/{project_id}/preflight",
                headers=AUTHORIZATION,
                json={
                    "expected_version": registration["project"]["version"],
                    "correlation_id": "orchestration_preflight",
                },
            )
            assert preflight.status_code == 200, preflight.text
            workflow_response = await client.post(
                f"/api/v1/projects/{project_id}/workflows",
                headers=AUTHORIZATION,
                json={
                    "title": "High-level five-stage delivery",
                    "correlation_id": "orchestration_workflow_create",
                },
            )
            assert workflow_response.status_code == 201, workflow_response.text
            workflow_snapshot = workflow_response.json()
            workflow_id = workflow_snapshot["workflow"]["id"]

            profile_ids: list[str] = []
            for name in ("primary", "reviewer_a", "reviewer_b"):
                profile = await client.post(
                    "/api/v1/model-profiles",
                    headers=AUTHORIZATION,
                    json={
                        "name": name,
                        "provider": "fake",
                        "base_url": "https://fake.invalid/v1",
                        "model": f"fake-{name}",
                        "credential_ref": f"credential.{name}",
                        "masked_hint": f"****{name[-1]}",
                        "correlation_id": f"orchestration_profile_{name}",
                    },
                )
                assert profile.status_code == 201, profile.text
                profile_ids.append(profile.json()["id"])
            for room in workflow_snapshot["rooms"]:
                assignment = await client.put(
                    f"/api/v1/rooms/{room['id']}/model-assignment",
                    headers=AUTHORIZATION,
                    json={
                        "primary_profile_id": profile_ids[0],
                        "reviewer_a_profile_id": profile_ids[1],
                        "reviewer_b_profile_id": profile_ids[2],
                        "expected_version": None,
                        "correlation_id": f"orchestration_assign_{room['stage']}",
                    },
                )
                assert assignment.status_code == 200, assignment.text
            started = await client.post(
                f"/api/v1/workflows/{workflow_id}/start",
                headers=AUTHORIZATION,
                json={
                    "expected_version": workflow_snapshot["workflow"]["version"],
                    "correlation_id": "orchestration_workflow_start",
                },
            )
            assert started.status_code == 200, started.text

            for stage in STAGE_ORDER:
                streamed = await client.post(
                    f"/api/v1/workflows/{workflow_id}/orchestration/stream",
                    headers=AUTHORIZATION,
                    json={
                        "request_key": f"formal-{stage.value}-request-0001",
                        "instruction": f"Complete the {stage.value} stage",
                        "correlation_id": f"orchestration_{stage.value}",
                    },
                )
                assert streamed.status_code == 200, streamed.text
                frames = [json.loads(line) for line in streamed.text.splitlines()]
                assert frames[-1]["type"] == "completed", frames
                assert not [frame for frame in frames if frame["type"] == "error"]
                assert any(frame["type"] == "tool_completed" for frame in frames)
                assert any(frame["type"] == "artifact_created" for frame in frames)
                assert any(frame["type"] == "gate_evaluated" for frame in frames)
                approval_frame = next(
                    frame for frame in frames if frame["type"] == "approval_required"
                )
                approval = approval_frame["data"]
                decision = await client.post(
                    f"/api/v1/approvals/{approval['id']}/decision",
                    headers=AUTHORIZATION,
                    json={
                        "approved": True,
                        "expected_version": approval["version"],
                        "reason": "Approved by high-level orchestration integration test",
                        "correlation_id": f"orchestration_{stage.value}_approval",
                    },
                )
                assert decision.status_code == 200, decision.text
                assert decision.json()["handoff"] is not None

            final_snapshot = await client.get(
                f"/api/v1/workflows/{workflow_id}", headers=AUTHORIZATION
            )
            tasks = await client.get(
                f"/api/v1/workflows/{workflow_id}/tasks", headers=AUTHORIZATION
            )
            tools = await client.get(
                f"/api/v1/workflows/{workflow_id}/tool-calls", headers=AUTHORIZATION
            )
            artifacts = await client.get(
                f"/api/v1/workflows/{workflow_id}/artifacts", headers=AUTHORIZATION
            )
            handoffs = await client.get(
                f"/api/v1/workflows/{workflow_id}/handoffs", headers=AUTHORIZATION
            )

    assert final_snapshot.json()["workflow"]["status"] == "completed"
    assert all(run["state"] == "completed" for run in final_snapshot.json()["stage_runs"])
    assert len(tasks.json()["tasks"]) == 5
    assert all(task["status"] == "succeeded" for task in tasks.json()["tasks"])
    assert len(tools.json()["calls"]) == 5
    assert all(call["status"] == "succeeded" for call in tools.json()["calls"])
    assert len(artifacts.json()["versions"]) == 5
    assert all(version["status"] == "locked" for version in artifacts.json()["versions"])
    assert len(handoffs.json()["handoffs"]) == 5
