import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from agent_platform.infrastructure.database.schema import CURRENT_DATABASE_REVISION

BACKEND_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_TABLES = {"workflows", "stage_runs", "rooms", "messages", "tasks"}


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


def test_workflow_upgrade_and_downgrade(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    database_path = data_root / "data" / "agent.db"
    _alembic(data_root, "upgrade", "0006_project_conflicts")
    _alembic(data_root, "upgrade", "head")

    assert WORKFLOW_TABLES.issubset(_tables(database_path))
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert revision == (CURRENT_DATABASE_REVISION,)

    _alembic(data_root, "downgrade", "0006_project_conflicts")

    assert not WORKFLOW_TABLES.intersection(_tables(database_path))
    assert "projects" in _tables(database_path)
