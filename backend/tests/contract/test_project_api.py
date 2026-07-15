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
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


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
async def test_direct_project_preflight_checkpoint_restore_close_and_open(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tracked = workspace / "tracked.txt"
    tracked.write_text("original", encoding="utf-8")
    _migrate(data_root)
    app = create_app(_settings(data_root))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            created = await client.post(
                "/api/v1/projects",
                headers=AUTHORIZATION,
                json={
                    "name": "Direct project",
                    "goal": "Exercise the complete project API",
                    "local_working_directory": str(workspace),
                    "workspace_mode": "direct",
                    "correlation_id": "create_direct_1",
                },
            )
            assert created.status_code == 201, created.text
            created_body = created.json()
            project_id = created_body["registration"]["project"]["id"]
            assert created_body["registration"]["project"]["status"] == "preflight_required"
            assert created_body["preflight_required"] is True

            preflight = await client.post(
                f"/api/v1/projects/{project_id}/preflight",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "preflight_direct_1"},
            )
            assert preflight.status_code == 200, preflight.text
            assert preflight.json()["result"]["status"] == "warning"
            assert preflight.json()["project"]["status"] == "ready"
            assert preflight.json()["project"]["version"] == 2

            checkpoint = await client.post(
                f"/api/v1/projects/{project_id}/checkpoints",
                headers=AUTHORIZATION,
                json={"reason": "manual", "correlation_id": "checkpoint_direct_1"},
            )
            assert checkpoint.status_code == 201, checkpoint.text
            checkpoint_id = checkpoint.json()["id"]

            tracked.write_text("user change", encoding="utf-8")
            extra = workspace / "extra-user-file.txt"
            extra.write_text("keep me", encoding="utf-8")
            restore_plan = await client.post(
                f"/api/v1/projects/{project_id}/checkpoints/{checkpoint_id}/restore-plan",
                headers=AUTHORIZATION,
                json={"correlation_id": "restore_plan_direct_1"},
            )
            assert restore_plan.status_code == 200, restore_plan.text
            plan_body = restore_plan.json()
            assert plan_body["plan"]["overwrite_paths"] == ["tracked.txt"]
            assert plan_body["plan"]["preserved_extra_paths"] == ["extra-user-file.txt"]
            protection_id = plan_body["protection_checkpoint"]["id"]

            restored = await client.post(
                f"/api/v1/projects/{project_id}/checkpoints/{checkpoint_id}/restore",
                headers=AUTHORIZATION,
                json={
                    "protection_checkpoint_id": protection_id,
                    "expected_project_version": 2,
                    "correlation_id": "restore_direct_1",
                },
            )
            assert restored.status_code == 200, restored.text
            assert restored.json()["project"]["status"] == "preflight_required"
            assert restored.json()["project"]["version"] == 3
            assert tracked.read_text(encoding="utf-8") == "original"
            assert extra.read_text(encoding="utf-8") == "keep me"

            closed = await client.post(
                f"/api/v1/projects/{project_id}/close",
                headers=AUTHORIZATION,
                json={"expected_version": 3, "correlation_id": "close_direct_1"},
            )
            assert closed.status_code == 200
            assert closed.json()["project"]["status"] == "closed"
            assert tracked.exists() and extra.exists()

            opened = await client.post(
                f"/api/v1/projects/{project_id}/open",
                headers=AUTHORIZATION,
                json={"expected_version": 4, "correlation_id": "open_direct_1"},
            )
            assert opened.status_code == 200
            assert opened.json()["project"]["status"] == "preflight_required"
            assert opened.json()["project"]["version"] == 5


@pytest.mark.asyncio
async def test_managed_project_imports_files_without_deleting_source(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    source = tmp_path / "source"
    source.mkdir()
    source_file = source / "source.txt"
    source_file.write_text("source content", encoding="utf-8")
    _migrate(data_root)
    app = create_app(_settings(data_root))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            created = await client.post(
                "/api/v1/projects",
                headers=AUTHORIZATION,
                json={
                    "name": "Managed project",
                    "goal": "Import an existing local project",
                    "local_working_directory": str(source),
                    "workspace_mode": "managed",
                    "correlation_id": "create_managed_1",
                },
            )
            assert created.status_code == 201, created.text
            body = created.json()
            project_id = body["registration"]["project"]["id"]
            managed_root = Path(body["registration"]["workspace"]["root_path"])
            assert managed_root.parent == data_root / "workspaces"
            assert (managed_root / "source.txt").read_text(encoding="utf-8") == "source content"
            assert source_file.read_text(encoding="utf-8") == "source content"

            closed = await client.post(
                f"/api/v1/projects/{project_id}/close",
                headers=AUTHORIZATION,
                json={"expected_version": 1, "correlation_id": "close_managed_1"},
            )
            assert closed.status_code == 200
            assert _exists(source_file)
            assert _exists(managed_root)


@pytest.mark.asyncio
async def test_external_scan_conflict_and_keep_agent_resolution_change_real_file(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tracked = workspace / "file.txt"
    tracked.write_text("baseline", encoding="utf-8")
    _migrate(data_root)
    app = create_app(_settings(data_root))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            created = await client.post(
                "/api/v1/projects",
                headers=AUTHORIZATION,
                json={
                    "name": "Conflict project",
                    "goal": "Resolve a real three-way file conflict",
                    "local_working_directory": str(workspace),
                    "workspace_mode": "direct",
                    "correlation_id": "create_conflict_1",
                },
            )
            assert created.status_code == 201, created.text
            project_id = created.json()["registration"]["project"]["id"]

            baseline = await client.post(
                f"/api/v1/projects/{project_id}/checkpoints",
                headers=AUTHORIZATION,
                json={"reason": "manual", "correlation_id": "baseline_conflict_1"},
            )
            baseline_id = baseline.json()["id"]
            tracked.write_text("agent version", encoding="utf-8")
            agent = await client.post(
                f"/api/v1/projects/{project_id}/checkpoints",
                headers=AUTHORIZATION,
                json={"reason": "pre_mutation", "correlation_id": "agent_conflict_1"},
            )
            agent_id = agent.json()["id"]
            tracked.write_text("user version", encoding="utf-8")

            scanned = await client.post(
                f"/api/v1/projects/{project_id}/external-changes/scan",
                headers=AUTHORIZATION,
                json={
                    "baseline_checkpoint_id": baseline_id,
                    "agent_checkpoint_id": agent_id,
                    "correlation_id": "scan_conflict_1",
                },
            )
            assert scanned.status_code == 200, scanned.text
            conflicts = scanned.json()["conflicts"]
            assert len(conflicts) == 1
            conflict_id = conflicts[0]["id"]

            resolved = await client.post(
                f"/api/v1/projects/{project_id}/conflicts/{conflict_id}/resolve",
                headers=AUTHORIZATION,
                json={
                    "resolution": "keep_agent",
                    "expected_conflict_version": 1,
                    "expected_project_version": 1,
                    "agent_checkpoint_id": agent_id,
                    "correlation_id": "resolve_conflict_1",
                },
            )
            assert resolved.status_code == 200, resolved.text
            assert resolved.json()["conflict"]["status"] == "resolved"
            assert resolved.json()["protection_checkpoint_id"] is not None
            assert tracked.read_text(encoding="utf-8") == "agent version"

            remaining = await client.get(
                f"/api/v1/projects/{project_id}/conflicts",
                headers=AUTHORIZATION,
            )
            assert remaining.status_code == 200
            assert remaining.json()["conflicts"] == []


@pytest.mark.asyncio
async def test_project_routes_require_auth_and_reject_duplicate_workspace(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _migrate(data_root)
    app = create_app(_settings(data_root))
    request = {
        "name": "Project",
        "goal": "Reject duplicate roots",
        "local_working_directory": str(workspace),
        "workspace_mode": "direct",
        "correlation_id": "create_duplicate_1",
    }

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            unauthorized = await client.get("/api/v1/projects")
            assert unauthorized.status_code == 401

            first = await client.post(
                "/api/v1/projects",
                headers=AUTHORIZATION,
                json=request,
            )
            assert first.status_code == 201, first.text
            request["correlation_id"] = "create_duplicate_2"
            duplicate = await client.post(
                "/api/v1/projects",
                headers=AUTHORIZATION,
                json=request,
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["error"]["code"] == "project.workspace_already_registered"


def _exists(path: Path) -> bool:
    return path.exists()
