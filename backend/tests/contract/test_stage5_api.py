import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.domain.contracts import StageRunState
from agent_platform.domain.model_runtime import AgentRun, AgentRunStatus
from agent_platform.infrastructure.database.models import WorkflowRow
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

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


async def _project_and_workflow(
    client: AsyncClient,
    workspace: Path,
) -> tuple[str, dict[str, object]]:
    created = await client.post(
        "/api/v1/projects",
        headers=AUTHORIZATION,
        json={
            "name": "Stage 5 project",
            "goal": "Exercise tools, gates, approvals and handoff",
            "local_working_directory": str(workspace),
            "workspace_mode": "direct",
            "correlation_id": "stage5_project_create",
        },
    )
    assert created.status_code == 201, created.text
    project_id = str(created.json()["registration"]["project"]["id"])
    preflight = await client.post(
        f"/api/v1/projects/{project_id}/preflight",
        headers=AUTHORIZATION,
        json={"expected_version": 1, "correlation_id": "stage5_preflight"},
    )
    assert preflight.status_code == 200, preflight.text
    workflow = await client.post(
        f"/api/v1/projects/{project_id}/workflows",
        headers=AUTHORIZATION,
        json={"title": "Stage 5 workflow", "correlation_id": "stage5_workflow_create"},
    )
    assert workflow.status_code == 201, workflow.text
    snapshot: dict[str, object] = workflow.json()
    workflow_id = str(snapshot["workflow"]["id"])
    started = await client.post(
        f"/api/v1/workflows/{workflow_id}/start",
        headers=AUTHORIZATION,
        json={"expected_version": 1, "correlation_id": "stage5_workflow_start"},
    )
    assert started.status_code == 200, started.text
    discussing = await client.post(
        f"/api/v1/workflows/{workflow_id}/stages/planner/transition",
        headers=AUTHORIZATION,
        json={
            "target_state": "discussing",
            "expected_workflow_version": 2,
            "expected_stage_version": 1,
            "correlation_id": "stage5_planner_discussing",
        },
    )
    assert discussing.status_code == 200, discussing.text
    return workflow_id, snapshot


@pytest.mark.asyncio
async def test_tools_capability_approval_and_task_scoped_expiry(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n",
        encoding="utf-8",
    )
    (workspace / "tests" / "test_sample.py").write_text(
        "def test_sample():\n    assert True\n",
        encoding="utf-8",
    )
    _migrate(data_root)
    app = create_app(_settings(data_root))

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            workflow_id, snapshot = await _project_and_workflow(client, workspace)
            room_id = str(snapshot["rooms"][0]["id"])
            task_response = await client.post(
                f"/api/v1/rooms/{room_id}/tasks",
                headers=AUTHORIZATION,
                json={"title": "Planner tools", "correlation_id": "stage5_task_create"},
            )
            task_id = str(task_response.json()["id"])
            started = await client.post(
                f"/api/v1/tasks/{task_id}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "stage5_task_start"},
            )
            assert started.status_code == 200

            written = await client.post(
                f"/api/v1/tasks/{task_id}/tool-calls",
                headers=AUTHORIZATION,
                json={
                    "tool_name": "filesystem.write_planner_artifact",
                    "idempotency_key": "stage5-write-plan-0001",
                    "arguments": {
                        "path": "artifacts/planner/plan.md",
                        "content": "# Plan\n",
                        "expected_hash": None,
                    },
                    "timeout_seconds": 30,
                    "correlation_id": "stage5_write_plan",
                },
            )
            assert written.status_code == 200, written.text
            assert written.json()["call"]["status"] == "succeeded"
            assert (workspace / "artifacts" / "planner" / "plan.md").read_text(
                encoding="utf-8"
            ) == "# Plan\n"

            requested = await client.post(
                f"/api/v1/tasks/{task_id}/capability-requests",
                headers=AUTHORIZATION,
                json={
                    "capability": "shell.test",
                    "reason": "Run the registered project tests",
                    "command": ["python", "-m", "pytest"],
                    "risk_level": "medium",
                    "idempotency_key": "stage5-capability-0001",
                    "correlation_id": "stage5_capability_request",
                },
            )
            assert requested.status_code == 201, requested.text
            capability = requested.json()
            decided = await client.post(
                f"/api/v1/capability-requests/{capability['id']}/decision",
                headers=AUTHORIZATION,
                json={
                    "approved": True,
                    "expected_version": 1,
                    "reason": "Approved for this task",
                    "correlation_id": "stage5_capability_approve",
                },
            )
            assert decided.status_code == 200, decided.text
            assert decided.json()["status"] == "approved"

            tested = await client.post(
                f"/api/v1/tasks/{task_id}/tool-calls",
                headers=AUTHORIZATION,
                json={
                    "tool_name": "shell.test",
                    "idempotency_key": "stage5-shell-test-0001",
                    "arguments": {"command_index": 0},
                    "timeout_seconds": 30,
                    "correlation_id": "stage5_shell_test",
                },
            )
            assert tested.status_code == 200, tested.text
            assert tested.json()["call"]["status"] == "succeeded", tested.text
            assert tested.json()["call"]["error_code"] is None
            assert tested.json()["output"]["exit_code"] == 0

            completed = await client.post(
                f"/api/v1/tasks/{task_id}/complete",
                headers=AUTHORIZATION,
                json={
                    "expected_version": 2,
                    "succeeded": True,
                    "result": {"plan": "ready"},
                    "correlation_id": "stage5_task_complete",
                },
            )
            assert completed.status_code == 200, completed.text
            requests = await client.get(
                f"/api/v1/workflows/{workflow_id}/capability-requests",
                headers=AUTHORIZATION,
            )
            assert requests.json()["requests"][0]["status"] == "expired"


@pytest.mark.asyncio
async def test_manual_gate_locks_artifact_and_creates_handoff(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _migrate(data_root)
    app = create_app(_settings(data_root))

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            workflow_id, snapshot = await _project_and_workflow(client, workspace)
            room_id = str(snapshot["rooms"][0]["id"])
            stage_run_id = str(snapshot["stage_runs"][0]["id"])
            task = await client.post(
                f"/api/v1/rooms/{room_id}/tasks",
                headers=AUTHORIZATION,
                json={"title": "Produce plan", "correlation_id": "gate_task_create"},
            )
            task_id = str(task.json()["id"])
            await client.post(
                f"/api/v1/tasks/{task_id}/start",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "gate_task_start"},
            )
            written = await client.post(
                f"/api/v1/tasks/{task_id}/tool-calls",
                headers=AUTHORIZATION,
                json={
                    "tool_name": "filesystem.write_planner_artifact",
                    "idempotency_key": "gate-write-plan-0001",
                    "arguments": {
                        "path": "artifacts/planner/plan.md",
                        "content": "# Approved plan\n",
                        "expected_hash": None,
                    },
                    "correlation_id": "gate_write_plan",
                },
            )
            assert written.status_code == 200, written.text
            await client.post(
                f"/api/v1/tasks/{task_id}/complete",
                headers=AUTHORIZATION,
                json={
                    "expected_version": 2,
                    "succeeded": True,
                    "result": {},
                    "correlation_id": "gate_task_complete",
                },
            )
            producing = await client.post(
                f"/api/v1/workflows/{workflow_id}/stages/planner/transition",
                headers=AUTHORIZATION,
                json={
                    "target_state": "producing",
                    "expected_workflow_version": 3,
                    "expected_stage_version": 2,
                    "correlation_id": "gate_producing",
                },
            )
            assert producing.status_code == 200, producing.text
            version_response = await client.post(
                f"/api/v1/stage-runs/{stage_run_id}/artifact-versions",
                headers=AUTHORIZATION,
                json={
                    "name": "Planner plan",
                    "relative_path": "artifacts/planner/plan.md",
                    "correlation_id": "gate_artifact_version",
                },
            )
            assert version_response.status_code == 201, version_response.text
            version_id = str(version_response.json()["version"]["id"])

            p2r = await client.post(
                f"/api/v1/workflows/{workflow_id}/stages/planner/transition",
                headers=AUTHORIZATION,
                json={
                    "target_state": "p2r_reviewing",
                    "expected_workflow_version": 4,
                    "expected_stage_version": 3,
                    "correlation_id": "gate_p2r",
                },
            )
            assert p2r.status_code == 200, p2r.text
            now = datetime.now(UTC)
            async with SqlAlchemyUnitOfWork(
                app.state.database.sessions,
                write=True,
                write_lock=app.state.database.write_lock,
            ) as uow:
                await uow.model_runtime.add_run(
                    AgentRun(
                        schema_version=1,
                        id="agentrun_gate_seed",
                        workflow_id=workflow_id,
                        room_id=room_id,
                        request_key="formal-gate-seed-0001",
                        formal=True,
                        status=AgentRunStatus.SUCCEEDED,
                        final_output_ref="seed-output",
                        final_output_hash="0" * 64,
                        final_output_bytes=1,
                        version=1,
                        created_at=now,
                        completed_at=now,
                    )
                )
                await uow.commit()
            checking = await client.post(
                f"/api/v1/workflows/{workflow_id}/stages/planner/transition",
                headers=AUTHORIZATION,
                json={
                    "target_state": "quality_checking",
                    "expected_workflow_version": 5,
                    "expected_stage_version": 4,
                    "correlation_id": "gate_quality_checking",
                },
            )
            assert checking.status_code == 200, checking.text
            evaluated = await client.post(
                f"/api/v1/stage-runs/{stage_run_id}/quality-gates",
                headers=AUTHORIZATION,
                json={
                    "artifact_version_ids": [version_id],
                    "correlation_id": "gate_evaluate",
                },
            )
            assert evaluated.status_code == 201, evaluated.text
            body = evaluated.json()
            assert body["gate"]["status"] == "pass"
            assert body["gate"]["resolution"] == "pending"
            assert body["approval"]["status"] == "pending"
            approved = await client.post(
                f"/api/v1/approvals/{body['approval']['id']}/decision",
                headers=AUTHORIZATION,
                json={
                    "approved": True,
                    "expected_version": 1,
                    "reason": "Plan is accepted",
                    "correlation_id": "gate_approve",
                },
            )
            assert approved.status_code == 200, approved.text
            approved_body = approved.json()
            assert approved_body["gate"]["resolution"] == "approved"
            assert approved_body["handoff"]["from_stage"] == "planner"
            assert approved_body["handoff"]["to_stage"] == "designer"
            workflow = await client.get(f"/api/v1/workflows/{workflow_id}", headers=AUTHORIZATION)
            workflow_body = workflow.json()
            assert workflow_body["workflow"]["current_stage"] == "designer"
            assert workflow_body["stage_runs"][0]["state"] == "completed"
            assert workflow_body["stage_runs"][1]["state"] == "ready"
            inventory = await client.get(
                f"/api/v1/workflows/{workflow_id}/artifacts",
                headers=AUTHORIZATION,
            )
            assert inventory.json()["versions"][0]["status"] == "locked"


@pytest.mark.asyncio
async def test_autonomous_warning_blocks_and_creates_rewrite_request(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    artifact_path = workspace / "artifacts" / "builder" / "build-report.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("# Build report\n", encoding="utf-8")
    _migrate(data_root)
    app = create_app(_settings(data_root))

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            workflow_id, snapshot = await _project_and_workflow(client, workspace)
            mode = await client.post(
                f"/api/v1/workflows/{workflow_id}/mode",
                headers=AUTHORIZATION,
                json={
                    "mode": "autonomous",
                    "expected_version": 3,
                    "correlation_id": "autonomous_mode",
                },
            )
            assert mode.status_code == 200, mode.text
            builder_run = snapshot["stage_runs"][2]
            builder_room = snapshot["rooms"][2]
            async with SqlAlchemyUnitOfWork(
                app.state.database.sessions,
                write=True,
                write_lock=app.state.database.write_lock,
            ) as uow:
                await uow.governance.set_stage_state(
                    str(builder_run["id"]),
                    StageRunState.QUALITY_CHECKING,
                    updated_at=datetime.now(UTC),
                )
                workflow_row = await uow.session.get(WorkflowRow, workflow_id)
                assert workflow_row is not None
                workflow_row.current_stage = "builder"
                await uow.model_runtime.add_run(
                    AgentRun(
                        schema_version=1,
                        id="agentrun_warning_seed",
                        workflow_id=workflow_id,
                        room_id=str(builder_room["id"]),
                        request_key="formal-warning-seed-0001",
                        formal=True,
                        status=AgentRunStatus.SUCCEEDED,
                        final_output_ref="warning-seed-output",
                        final_output_hash="1" * 64,
                        final_output_bytes=1,
                        version=1,
                        created_at=datetime.now(UTC),
                        completed_at=datetime.now(UTC),
                    )
                )
                await uow.commit()
            version = await client.post(
                f"/api/v1/stage-runs/{builder_run['id']}/artifact-versions",
                headers=AUTHORIZATION,
                json={
                    "name": "Build report",
                    "relative_path": "artifacts/builder/build-report.md",
                    "correlation_id": "warning_artifact_version",
                },
            )
            assert version.status_code == 201, version.text
            evaluated = await client.post(
                f"/api/v1/stage-runs/{builder_run['id']}/quality-gates",
                headers=AUTHORIZATION,
                json={
                    "artifact_version_ids": [version.json()["version"]["id"]],
                    "correlation_id": "warning_gate_evaluate",
                },
            )
            assert evaluated.status_code == 201, evaluated.text
            body = evaluated.json()
            assert body["gate"]["status"] == "warning"
            assert body["gate"]["resolution"] == "rewrite_required"
            assert body["approval"] is None
            assert body["handoff"] is None
            assert body["change_request"]["target_stage"] == "builder"
            workflow = await client.get(f"/api/v1/workflows/{workflow_id}", headers=AUTHORIZATION)
            workflow_body = workflow.json()
            assert workflow_body["workflow"]["status"] == "warning_blocked"
            assert workflow_body["stage_runs"][2]["state"] == "warning_blocked"

            resumed = await client.post(
                f"/api/v1/workflows/{workflow_id}/stages/builder/transition",
                headers=AUTHORIZATION,
                json={
                    "target_state": "discussing",
                    "expected_workflow_version": workflow_body["workflow"]["version"],
                    "expected_stage_version": workflow_body["stage_runs"][2]["version"],
                    "correlation_id": "warning_return_to_discussion",
                },
            )
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()["workflow"]["status"] == "running"
            assert resumed.json()["stage_run"]["state"] == "discussing"
