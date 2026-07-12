from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _table_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }


def _run_alembic(*arguments: str, data_root: Path) -> None:
    environment = os.environ.copy()
    environment["AGENT_PLATFORM_DATA_ROOT"] = str(data_root)
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_foundation_migration_upgrades_and_downgrades_cleanly(tmp_path: Path) -> None:
    data_root = tmp_path / "isolated-data-root"
    database_path = data_root / "data" / "agent.db"

    _run_alembic("upgrade", "head", data_root=data_root)

    upgraded_tables = _table_names(database_path)
    assert {name for name in upgraded_tables if not name.startswith("sqlite_")} == {
        "alembic_version",
        "event_log",
        "outbox_events",
    }

    _run_alembic("downgrade", "base", data_root=data_root)

    downgraded_tables = _table_names(database_path)
    downgraded_application_tables = {
        name for name in downgraded_tables if not name.startswith("sqlite_")
    }
    assert downgraded_application_tables == set()
