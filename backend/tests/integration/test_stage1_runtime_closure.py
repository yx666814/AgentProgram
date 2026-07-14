from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import structlog
from sqlalchemy import select

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.infrastructure.database.backup import verify_backup
from agent_platform.infrastructure.database.models import LocalAuditEventRow
from agent_platform.infrastructure.database.session import Database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


def _upgrade_to_head(data_root: Path) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["AGENT_PLATFORM_DATA_ROOT"] = str(data_root)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


async def _wait_for_audit(database: Database, event_id: int) -> LocalAuditEventRow:
    for _ in range(200):
        async with database.sessions() as session:
            row = await session.scalar(
                select(LocalAuditEventRow).where(LocalAuditEventRow.event_log_id == event_id)
            )
        if row is not None:
            return row
        await asyncio.sleep(0.01)
    raise AssertionError("local audit delivery did not complete")


@pytest.mark.asyncio
async def test_stage1_runtime_persists_audits_backups_logs_and_restarts(
    tmp_path: Path,
) -> None:
    session_token = "stage1-closure-secret"
    settings = Settings(
        data_root=tmp_path,
        session_token=session_token,
        worker_heartbeat_timeout_seconds=1.0,
        worker_watchdog_interval_seconds=0.1,
        database_maintenance_interval_seconds=60.0,
        database_integrity_check_interval_seconds=60.0,
        database_backup_interval_seconds=60.0,
        outbox_poll_interval_seconds=0.01,
        outbox_lease_seconds=1.0,
        outbox_publish_timeout_seconds=0.5,
        outbox_shutdown_drain_seconds=1.0,
        outbox_cleanup_interval_seconds=60.0,
    )
    _upgrade_to_head(settings.data_root)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        database = app.state.database
        await app.state.database_maintenance.run_once(force_backup=True)
        envelope = EventEnvelope(
            schema_version=1,
            event_type="system.stage1_closure",
            correlation_id="stage1_closure_1",
            actor=ActorRef(type=ActorType.SYSTEM),
            source=EventSource.BACKEND,
            occurred_at=datetime.now(UTC),
            payload={"status": "verified"},
        )
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            event_id = await uow.events.append(
                envelope=envelope,
                aggregate_type="system",
                aggregate_id="system_stage1",
            )
            await uow.commit()

        audit = await _wait_for_audit(database, event_id)
        assert audit.event_type == envelope.event_type
        structlog.get_logger("stage1-closure").info(
            "closure log",
            embedded_secret=f"Bearer {session_token}",
            event_id=event_id,
        )

    for attribute in (
        "outbox_dispatcher",
        "outbox_dispatcher_task",
        "database_maintenance",
        "database_maintenance_task",
        "worker_watchdog_task",
        "worker_supervisor",
        "database",
        "logging_runtime",
        "instance_lock",
    ):
        assert not hasattr(app.state, attribute)

    manifests = sorted(settings.backup_root.glob("*.manifest.json"))
    assert manifests
    assert verify_backup(manifests[-1]).manifest.schema_revision is not None
    log_text = (settings.log_root / "backend.jsonl").read_text(encoding="utf-8")
    assert session_token not in log_text
    assert "***" in log_text

    restarted_app = create_app(settings)
    async with restarted_app.router.lifespan_context(restarted_app):
        assert hasattr(restarted_app.state, "instance_lock")
