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
async def test_workflow_messages_tasks_and_replay_survive_restart(tmp_path: Path) -> None:
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
            created = await client.post(
                "/api/v1/projects",
                headers=AUTHORIZATION,
                json={
                    "name": "Restart project",
                    "goal": "Persist Stage 3 state",
                    "local_working_directory": str(workspace),
                    "workspace_mode": "direct",
                    "correlation_id": "restart_project_create",
                },
            )
            project_id = created.json()["registration"]["project"]["id"]
            preflight = await client.post(
                f"/api/v1/projects/{project_id}/preflight",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "restart_preflight"},
            )
            assert preflight.status_code == 200
            created_workflow = await client.post(
                f"/api/v1/projects/{project_id}/workflows",
                headers=AUTHORIZATION,
                json={"title": "Restart workflow", "correlation_id": "restart_workflow"},
            )
            snapshot = created_workflow.json()
            workflow_id = snapshot["workflow"]["id"]
            room_id = snapshot["rooms"][0]["id"]
            started = await client.post(
                f"/api/v1/workflows/{workflow_id}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "restart_start"},
            )
            assert started.status_code == 200
            discussing = await client.post(
                f"/api/v1/workflows/{workflow_id}/stages/planner/transition",
                headers=AUTHORIZATION,
                json={
                    "target_state": "discussing",
                    "expected_workflow_version": 2,
                    "expected_stage_version": 1,
                    "correlation_id": "restart_discussing",
                },
            )
            assert discussing.status_code == 200
            message = await client.post(
                f"/api/v1/rooms/{room_id}/messages",
                headers=AUTHORIZATION,
                json={
                    "content": "Persistent message",
                    "expected_room_version": 1,
                    "correlation_id": "restart_message",
                },
            )
            assert message.status_code == 201
            task = await client.post(
                f"/api/v1/rooms/{room_id}/tasks",
                headers=AUTHORIZATION,
                json={"title": "Persistent task", "correlation_id": "restart_task"},
            )
            assert task.status_code == 201
            task_id = task.json()["id"]

    restarted = create_app(settings)
    async with restarted.router.lifespan_context(restarted):
        async with AsyncClient(
            transport=ASGITransport(app=restarted),
            base_url="http://test",
        ) as client:
            workflow = await client.get(
                f"/api/v1/workflows/{workflow_id}",
                headers=AUTHORIZATION,
            )
            messages = await client.get(
                f"/api/v1/rooms/{room_id}/messages",
                headers=AUTHORIZATION,
            )
            tasks = await client.get(
                f"/api/v1/workflows/{workflow_id}/tasks",
                headers=AUTHORIZATION,
            )
            replay = await client.get(
                f"/api/v1/events/replay?workflow_id={workflow_id}&after_event_id=0",
                headers=AUTHORIZATION,
            )

    assert workflow.status_code == 200
    assert workflow.json()["workflow"]["status"] == "running"
    assert workflow.json()["stage_runs"][0]["state"] == "discussing"
    assert [item["content"] for item in messages.json()["messages"]] == ["Persistent message"]
    assert [(item["id"], item["status"]) for item in tasks.json()["tasks"]] == [(task_id, "queued")]
    assert [event["event_type"] for event in replay.json()["events"]] == [
        "workflow.created",
        "workflow.started",
        "stage_run.transitioned",
        "message.appended",
        "task.queued",
    ]
