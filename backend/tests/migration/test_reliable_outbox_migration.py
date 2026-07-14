import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _alembic(data_root: Path, *args: str) -> None:
    environment = os.environ.copy()
    environment["AGENT_PLATFORM_DATA_ROOT"] = str(data_root)
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_legacy_event_without_outbox_is_upgraded_with_required_target(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    database_path = data_root / "data" / "agent.db"
    _alembic(data_root, "upgrade", "0001_foundation")
    occurred_at = datetime.now(UTC).replace(tzinfo=None).isoformat(sep=" ")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO event_log (
                event_type, project_id, workflow_id, room_id, task_id,
                aggregate_type, aggregate_id, payload, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "workflow.started",
                "project_1",
                "wf_1",
                None,
                None,
                "workflow",
                "wf_1",
                "{}",
                occurred_at,
            ),
        )
    _alembic(data_root, "upgrade", "head")

    with sqlite3.connect(database_path) as connection:
        event = connection.execute(
            "SELECT schema_version, correlation_id, actor_type, source FROM event_log"
        ).fetchone()
        aggregate = connection.execute("SELECT id, delivery_state FROM outbox_events").fetchone()
        delivery = connection.execute(
            "SELECT consumer_name, delivery_state FROM outbox_deliveries"
        ).fetchone()
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert event == (1, "legacy:event:1", "system", "backend")
    assert aggregate == ("out_legacy_1", "pending")
    assert delivery == ("local_audit_v1", "pending")
    assert revision == ("0002_reliable_outbox",)
