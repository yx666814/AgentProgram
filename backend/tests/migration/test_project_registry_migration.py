import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from agent_platform.infrastructure.database.schema import (
    PROJECT_REGISTRY_DATABASE_REVISION,
)

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


def _application_tables(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not str(row[0]).startswith("sqlite_")
        }


def test_project_registry_upgrades_and_downgrades_cleanly(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    database_path = data_root / "data" / "agent.db"
    _alembic(data_root, "upgrade", "0002_reliable_outbox")
    _alembic(data_root, "upgrade", "head")

    upgraded = _application_tables(database_path)
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert {
        "projects",
        "workspaces",
        "project_manifests",
        "project_instructions",
    }.issubset(upgraded)
    assert revision == (PROJECT_REGISTRY_DATABASE_REVISION,)

    _alembic(data_root, "downgrade", "0002_reliable_outbox")

    downgraded = _application_tables(database_path)
    assert not {
        "projects",
        "workspaces",
        "project_manifests",
        "project_instructions",
    }.intersection(downgraded)
    assert "event_log" in downgraded
