import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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
        websocket_replay_batch_size=2,
    )


def _ready_workflow(client: TestClient, workspace: Path) -> tuple[str, dict[str, object]]:
    created = client.post(
        "/api/v1/projects",
        headers=AUTHORIZATION,
        json={
            "name": "Stream project",
            "goal": "Exercise event streaming",
            "local_working_directory": str(workspace),
            "workspace_mode": "direct",
            "correlation_id": "stream_project_create",
        },
    )
    project_id = created.json()["registration"]["project"]["id"]
    preflight = client.post(
        f"/api/v1/projects/{project_id}/preflight",
        headers=AUTHORIZATION,
        json={"expected_version": 1, "correlation_id": "stream_project_preflight"},
    )
    assert preflight.status_code == 200
    workflow = client.post(
        f"/api/v1/projects/{project_id}/workflows",
        headers=AUTHORIZATION,
        json={"title": "Stream workflow", "correlation_id": "stream_workflow_create"},
    )
    assert workflow.status_code == 201, workflow.text
    snapshot = workflow.json()
    workflow_id = snapshot["workflow"]["id"]
    started = client.post(
        f"/api/v1/workflows/{workflow_id}/start",
        headers=AUTHORIZATION,
        json={"expected_version": 1, "correlation_id": "stream_workflow_start"},
    )
    assert started.status_code == 200, started.text
    return workflow_id, snapshot


def _ticket(client: TestClient, workflow_id: str) -> str:
    response = client.post(
        "/api/v1/events/tickets",
        headers=AUTHORIZATION,
        json={"workflow_id": workflow_id},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["ticket"])


def test_websocket_ticket_replay_live_delivery_and_reconnect(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _migrate(data_root)
    app = create_app(_settings(data_root))

    with TestClient(app) as client:
        workflow_id, snapshot = _ready_workflow(client, workspace)
        ticket = _ticket(client, workflow_id)
        with client.websocket_connect(
            f"/api/v1/events/ws?ticket={ticket}&after_event_id=0"
        ) as websocket:
            replayed: list[dict[str, object]] = []
            while True:
                frame = websocket.receive_json()
                if frame["type"] == "ready":
                    last_event_id = frame["last_event_id"]
                    break
                replayed.append(frame)
            replay_ids = [int(frame["event_id"]) for frame in replayed]
            assert replay_ids == sorted(set(replay_ids))
            assert [frame["event"]["event_type"] for frame in replayed] == [
                "workflow.created",
                "workflow.started",
            ]

            transitioned = client.post(
                f"/api/v1/workflows/{workflow_id}/stages/planner/transition",
                headers=AUTHORIZATION,
                json={
                    "target_state": "discussing",
                    "expected_workflow_version": 2,
                    "expected_stage_version": 1,
                    "correlation_id": "stream_live_transition",
                },
            )
            assert transitioned.status_code == 200, transitioned.text
            live = websocket.receive_json()
            assert live["type"] == "event"
            assert live["event"]["event_type"] == "stage_run.transitioned"
            assert live["event_id"] > last_event_id
            last_event_id = live["event_id"]

        with pytest.raises(WebSocketDisconnect) as reused:
            with client.websocket_connect(
                f"/api/v1/events/ws?ticket={ticket}&after_event_id={last_event_id}"
            ):
                pass
        assert reused.value.code == 4401

        reconnect_ticket = _ticket(client, workflow_id)
        with client.websocket_connect(
            f"/api/v1/events/ws?ticket={reconnect_ticket}&after_event_id={last_event_id}"
        ) as websocket:
            ready = websocket.receive_json()
            assert ready == {
                "schema_version": 1,
                "type": "ready",
                "last_event_id": last_event_id,
            }

        replay = client.get(
            f"/api/v1/events/replay?workflow_id={workflow_id}&after_event_id=0",
            headers=AUTHORIZATION,
        )
        assert replay.status_code == 200
        assert len(replay.json()["events"]) == 2
