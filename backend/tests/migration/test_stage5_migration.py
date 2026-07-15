import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from agent_platform.infrastructure.database.schema import (
    MODEL_RUNTIME_DATABASE_REVISION,
    STAGE5_DATABASE_REVISION,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
STAGE5_TABLES = {
    "capability_requests",
    "approvals",
    "tool_calls",
    "artifacts",
    "artifact_versions",
    "quality_gate_runs",
    "quality_gate_issues",
    "quality_gate_artifacts",
    "handoff_packets",
    "change_requests",
    "recovery_records",
}


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


def _tables(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


def test_stage5_upgrade_and_downgrade(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    database_path = data_root / "data" / "agent.db"
    _alembic(data_root, "upgrade", MODEL_RUNTIME_DATABASE_REVISION)
    _alembic(data_root, "upgrade", STAGE5_DATABASE_REVISION)

    assert STAGE5_TABLES.issubset(_tables(database_path))
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        workflow_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(workflows)")
        }
    assert revision == (STAGE5_DATABASE_REVISION,)
    assert "execution_mode" in workflow_columns

    _alembic(data_root, "downgrade", MODEL_RUNTIME_DATABASE_REVISION)

    assert not STAGE5_TABLES.intersection(_tables(database_path))
    with sqlite3.connect(database_path) as connection:
        workflow_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(workflows)")
        }
    assert "execution_mode" not in workflow_columns
