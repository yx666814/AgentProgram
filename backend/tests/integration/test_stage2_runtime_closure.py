import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.infrastructure.projects.metadata import ProjectMetadataStore

AUTHORIZATION = {"Authorization": "Bearer stage2-secret"}
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
        session_token="stage2-secret",
        worker_heartbeat_timeout_seconds=1.0,
        worker_watchdog_interval_seconds=0.1,
        outbox_poll_interval_seconds=0.01,
        outbox_lease_seconds=1.0,
        outbox_publish_timeout_seconds=0.5,
    )


@pytest.mark.asyncio
async def test_stage2_project_state_checkpoints_and_metadata_survive_restart(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data-root"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "main.py").write_text("print('ready')\n", encoding="utf-8")
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
                    "goal": "Prove Stage 2 runtime closure",
                    "local_working_directory": str(workspace),
                    "workspace_mode": "direct",
                    "correlation_id": "stage2_create_1",
                },
            )
            assert created.status_code == 201, created.text
            project_id = created.json()["registration"]["project"]["id"]
            checkpoint = await client.post(
                f"/api/v1/projects/{project_id}/checkpoints",
                headers=AUTHORIZATION,
                json={"reason": "manual", "correlation_id": "stage2_checkpoint_1"},
            )
            assert checkpoint.status_code == 201, checkpoint.text
            checkpoint_id = checkpoint.json()["id"]

    for attribute in (
        "outbox_dispatcher",
        "outbox_dispatcher_task",
        "database_maintenance",
        "database_maintenance_task",
        "worker_watchdog_task",
        "database",
        "instance_lock",
    ):
        assert not hasattr(app.state, attribute)

    metadata = ProjectMetadataStore(workspace).read_metadata()
    manifest = ProjectMetadataStore(workspace).read_manifest()
    assert metadata.project_id == project_id
    assert manifest.project_id == project_id

    restarted = create_app(settings)
    async with restarted.router.lifespan_context(restarted):
        async with AsyncClient(
            transport=ASGITransport(app=restarted),
            base_url="http://test",
        ) as client:
            projects = await client.get("/api/v1/projects", headers=AUTHORIZATION)
            checkpoints = await client.get(
                f"/api/v1/projects/{project_id}/checkpoints",
                headers=AUTHORIZATION,
            )

    assert projects.status_code == 200
    assert [item["project"]["id"] for item in projects.json()["projects"]] == [project_id]
    assert checkpoints.status_code == 200
    assert [item["id"] for item in checkpoints.json()["checkpoints"]] == [checkpoint_id]
