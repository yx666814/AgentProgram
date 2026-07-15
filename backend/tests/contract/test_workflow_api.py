import asyncio
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


async def _ready_project(client: AsyncClient, workspace: Path) -> str:
    created = await client.post(
        "/api/v1/projects",
        headers=AUTHORIZATION,
        json={
            "name": "Workflow project",
            "goal": "Exercise Stage 3",
            "local_working_directory": str(workspace),
            "workspace_mode": "direct",
            "correlation_id": "create_workflow_project",
        },
    )
    assert created.status_code == 201, created.text
    project_id = str(created.json()["registration"]["project"]["id"])
    preflight = await client.post(
        f"/api/v1/projects/{project_id}/preflight",
        headers=AUTHORIZATION,
        json={"expected_version": 1, "correlation_id": "preflight_workflow_project"},
    )
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["project"]["status"] == "ready"
    return project_id


@pytest.mark.asyncio
async def test_workflow_messages_task_queue_concurrency_and_reopen(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _migrate(data_root)
    app = create_app(_settings(data_root))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            project_id = await _ready_project(client, workspace)
            created = await client.post(
                f"/api/v1/projects/{project_id}/workflows",
                headers=AUTHORIZATION,
                json={"title": "Deliver V1", "correlation_id": "workflow_create_1"},
            )
            assert created.status_code == 201, created.text
            snapshot = created.json()
            workflow_id = snapshot["workflow"]["id"]
            planner_room = snapshot["rooms"][0]
            assert [run["state"] for run in snapshot["stage_runs"]] == [
                "ready",
                "locked",
                "locked",
                "locked",
                "locked",
            ]

            started = await client.post(
                f"/api/v1/workflows/{workflow_id}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "workflow_start_1"},
            )
            assert started.status_code == 200, started.text
            duplicate = await client.post(
                f"/api/v1/workflows/{workflow_id}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 2, "correlation_id": "workflow_start_duplicate"},
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["error"]["code"] == "workflow.already_started"

            transition_url = f"/api/v1/workflows/{workflow_id}/stages/planner/transition"
            transition_payload = {
                "target_state": "discussing",
                "expected_workflow_version": 2,
                "expected_stage_version": 1,
            }
            first, second = await asyncio.gather(
                client.post(
                    transition_url,
                    headers=AUTHORIZATION,
                    json={**transition_payload, "correlation_id": "planner_discuss_a"},
                ),
                client.post(
                    transition_url,
                    headers=AUTHORIZATION,
                    json={**transition_payload, "correlation_id": "planner_discuss_b"},
                ),
            )
            assert sorted((first.status_code, second.status_code)) == [200, 409]
            transitioned = first if first.status_code == 200 else second
            workflow_version = transitioned.json()["workflow"]["version"]
            stage_version = transitioned.json()["stage_run"]["version"]

            message = await client.post(
                f"/api/v1/rooms/{planner_room['id']}/messages",
                headers=AUTHORIZATION,
                json={
                    "content": "Plan the delivery",
                    "expected_room_version": 1,
                    "correlation_id": "message_1",
                },
            )
            assert message.status_code == 201, message.text
            correction = await client.post(
                f"/api/v1/rooms/{planner_room['id']}/messages",
                headers=AUTHORIZATION,
                json={
                    "content": "Plan the complete V1 delivery",
                    "correction_of_id": message.json()["message"]["id"],
                    "expected_room_version": 2,
                    "correlation_id": "message_2",
                },
            )
            assert correction.status_code == 201, correction.text
            assert correction.json()["message"]["sequence"] == 2
            assert correction.json()["message"]["kind"] == "correction"

            tasks = []
            for index in range(2):
                response = await client.post(
                    f"/api/v1/rooms/{planner_room['id']}/tasks",
                    headers=AUTHORIZATION,
                    json={
                        "title": f"Planner task {index}",
                        "payload": {"index": index},
                        "correlation_id": f"task_queue_{index}",
                    },
                )
                assert response.status_code == 201, response.text
                tasks.append(response.json())
            out_of_order = await client.post(
                f"/api/v1/tasks/{tasks[1]['id']}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "task_out_of_order"},
            )
            assert out_of_order.status_code == 409
            running = await client.post(
                f"/api/v1/tasks/{tasks[0]['id']}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "task_start_1"},
            )
            assert running.status_code == 200, running.text
            cancelled = await client.post(
                f"/api/v1/tasks/{tasks[0]['id']}/cancel",
                headers=AUTHORIZATION,
                json={"expected_version": 2, "correlation_id": "task_cancel_1"},
            )
            assert cancelled.status_code == 200
            second_running = await client.post(
                f"/api/v1/tasks/{tasks[1]['id']}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "task_start_2"},
            )
            assert second_running.status_code == 200
            completed_task = await client.post(
                f"/api/v1/tasks/{tasks[1]['id']}/complete",
                headers=AUTHORIZATION,
                json={
                    "expected_version": 2,
                    "succeeded": True,
                    "result": {"artifact": "plan"},
                    "correlation_id": "task_complete_2",
                },
            )
            assert completed_task.status_code == 200
            assert completed_task.json()["status"] == "succeeded"

            for target in (
                "producing",
                "p2r_reviewing",
                "quality_checking",
                "waiting_approval",
                "handoff_ready",
                "completed",
            ):
                response = await client.post(
                    transition_url,
                    headers=AUTHORIZATION,
                    json={
                        "target_state": target,
                        "expected_workflow_version": workflow_version,
                        "expected_stage_version": stage_version,
                        "correlation_id": f"planner_{target}",
                    },
                )
                assert response.status_code == 200, response.text
                workflow_version = response.json()["workflow"]["version"]
                stage_version = response.json()["stage_run"]["version"]
            assert response.json()["unlocked_stage_run"]["stage"] == "designer"
            assert response.json()["unlocked_stage_run"]["state"] == "ready"

            consultation = await client.post(
                f"/api/v1/rooms/{planner_room['id']}/messages",
                headers=AUTHORIZATION,
                json={
                    "content": "Explain the completed plan",
                    "expected_room_version": 4,
                    "correlation_id": "planner_consultation",
                },
            )
            assert consultation.status_code == 201, consultation.text
            assert consultation.json()["message"]["kind"] == "consultation"
            messages = await client.get(
                f"/api/v1/rooms/{planner_room['id']}/messages?after_sequence=1",
                headers=AUTHORIZATION,
            )
            assert [item["sequence"] for item in messages.json()["messages"]] == [2, 3]

            current = await client.get(
                f"/api/v1/workflows/{workflow_id}",
                headers=AUTHORIZATION,
            )
            designer_room = next(
                room for room in current.json()["rooms"] if room["stage"] == "designer"
            )
            invalidated_task = await client.post(
                f"/api/v1/rooms/{designer_room['id']}/tasks",
                headers=AUTHORIZATION,
                json={
                    "title": "Designer queued work",
                    "correlation_id": "designer_task_before_reopen",
                },
            )
            assert invalidated_task.status_code == 201, invalidated_task.text
            reopened = await client.post(
                f"/api/v1/workflows/{workflow_id}/stages/planner/reopen",
                headers=AUTHORIZATION,
                json={
                    "expected_version": workflow_version,
                    "correlation_id": "planner_reopen_1",
                },
            )
            assert reopened.status_code == 200, reopened.text
            assert reopened.json()["workflow"]["current_stage"] == "planner"
            assert [run["attempt"] for run in reopened.json()["stage_runs"]] == [2, 2, 2, 2, 2]
            assert [run["state"] for run in reopened.json()["stage_runs"]] == [
                "ready",
                "locked",
                "locked",
                "locked",
                "locked",
            ]
            history = await client.get(
                f"/api/v1/workflows/{workflow_id}/stage-runs/history",
                headers=AUTHORIZATION,
            )
            assert len(history.json()["stage_runs"]) == 10
            listed_tasks = await client.get(
                f"/api/v1/workflows/{workflow_id}/tasks",
                headers=AUTHORIZATION,
            )
            by_id = {task["id"]: task for task in listed_tasks.json()["tasks"]}
            assert by_id[invalidated_task.json()["id"]]["status"] == "cancelled"
