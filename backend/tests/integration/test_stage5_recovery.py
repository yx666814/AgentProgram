import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings

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
    )


@pytest.mark.asyncio
async def test_restart_marks_active_work_as_interrupted_and_resumes(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _migrate(data_root)
    settings = _settings(data_root)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            project = await client.post(
                "/api/v1/projects",
                headers=AUTHORIZATION,
                json={
                    "name": "Recovery project",
                    "goal": "Recover an interrupted workflow",
                    "local_working_directory": str(workspace),
                    "workspace_mode": "direct",
                    "correlation_id": "recovery_project",
                },
            )
            project_id = project.json()["registration"]["project"]["id"]
            await client.post(
                f"/api/v1/projects/{project_id}/preflight",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "recovery_preflight"},
            )
            created = await client.post(
                f"/api/v1/projects/{project_id}/workflows",
                headers=AUTHORIZATION,
                json={"title": "Recovery workflow", "correlation_id": "recovery_create"},
            )
            snapshot = created.json()
            workflow_id = snapshot["workflow"]["id"]
            room_id = snapshot["rooms"][0]["id"]
            await client.post(
                f"/api/v1/workflows/{workflow_id}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "recovery_start"},
            )
            await client.post(
                f"/api/v1/workflows/{workflow_id}/stages/planner/transition",
                headers=AUTHORIZATION,
                json={
                    "target_state": "discussing",
                    "expected_workflow_version": 2,
                    "expected_stage_version": 1,
                    "correlation_id": "recovery_discussing",
                },
            )
            task = await client.post(
                f"/api/v1/rooms/{room_id}/tasks",
                headers=AUTHORIZATION,
                json={"title": "Interrupted task", "correlation_id": "recovery_task"},
            )
            task_id = task.json()["id"]
            running = await client.post(
                f"/api/v1/tasks/{task_id}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "recovery_task_start"},
            )
            assert running.json()["status"] == "running"

    restarted = create_app(settings)
    async with restarted.router.lifespan_context(restarted):
        async with AsyncClient(
            transport=ASGITransport(app=restarted), base_url="http://test"
        ) as client:
            workflow = await client.get(f"/api/v1/workflows/{workflow_id}", headers=AUTHORIZATION)
            assert workflow.json()["workflow"]["status"] == "interrupted"
            assert workflow.json()["stage_runs"][0]["state"] == "interrupted"
            tasks = await client.get(
                f"/api/v1/workflows/{workflow_id}/tasks", headers=AUTHORIZATION
            )
            assert tasks.json()["tasks"][0]["status"] == "cancelled"
            recoveries = await client.get("/api/v1/recovery", headers=AUTHORIZATION)
            recovery = recoveries.json()["recoveries"][0]
            assert recovery["interrupted_tasks"] == 1
            resumed = await client.post(
                f"/api/v1/recovery/{recovery['id']}/resume",
                headers=AUTHORIZATION,
                json={"correlation_id": "recovery_resume"},
            )
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()["status"] == "resumed"
            workflow = await client.get(f"/api/v1/workflows/{workflow_id}", headers=AUTHORIZATION)
            assert workflow.json()["workflow"]["status"] == "running"
            assert workflow.json()["stage_runs"][0]["state"] == "discussing"


@pytest.mark.asyncio
async def test_pause_resume_and_stop_preserve_workspace(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    user_file = workspace / "user.txt"
    user_file.write_text("keep", encoding="utf-8")
    _migrate(data_root)
    app = create_app(_settings(data_root))

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            project = await client.post(
                "/api/v1/projects",
                headers=AUTHORIZATION,
                json={
                    "name": "Control project",
                    "goal": "Exercise workflow controls",
                    "local_working_directory": str(workspace),
                    "workspace_mode": "direct",
                    "correlation_id": "control_project",
                },
            )
            project_id = project.json()["registration"]["project"]["id"]
            await client.post(
                f"/api/v1/projects/{project_id}/preflight",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "control_preflight"},
            )
            created = await client.post(
                f"/api/v1/projects/{project_id}/workflows",
                headers=AUTHORIZATION,
                json={"title": "Control workflow", "correlation_id": "control_create"},
            )
            workflow_id = created.json()["workflow"]["id"]
            await client.post(
                f"/api/v1/workflows/{workflow_id}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "control_start"},
            )
            discussing = await client.post(
                f"/api/v1/workflows/{workflow_id}/stages/planner/transition",
                headers=AUTHORIZATION,
                json={
                    "target_state": "discussing",
                    "expected_workflow_version": 2,
                    "expected_stage_version": 1,
                    "correlation_id": "control_discussing",
                },
            )
            assert discussing.json()["workflow"]["version"] == 3
            paused = await client.post(
                f"/api/v1/workflows/{workflow_id}/pause",
                headers=AUTHORIZATION,
                json={"expected_version": 3, "correlation_id": "control_pause"},
            )
            assert paused.status_code == 200, paused.text
            assert paused.json()["status"] == "paused"
            resumed = await client.post(
                f"/api/v1/workflows/{workflow_id}/resume",
                headers=AUTHORIZATION,
                json={"expected_version": 4, "correlation_id": "control_resume"},
            )
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()["status"] == "running"
            stopped = await client.post(
                f"/api/v1/workflows/{workflow_id}/stop",
                headers=AUTHORIZATION,
                json={"expected_version": 5, "correlation_id": "control_stop"},
            )
            assert stopped.status_code == 200, stopped.text
            assert stopped.json()["status"] == "stopped"

    assert user_file.read_text(encoding="utf-8") == "keep"
