import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from agent_platform.infrastructure.database.schema import (
    PROJECT_CHECKPOINT_DATABASE_REVISION,
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


def _tables(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


def test_project_checkpoint_upgrade_and_downgrade(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    database_path = data_root / "data" / "agent.db"
    _alembic(data_root, "upgrade", "0004_project_preflight")
    _alembic(data_root, "upgrade", "head")

    assert {"project_checkpoints", "checkpoint_files"}.issubset(_tables(database_path))
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert revision == (PROJECT_CHECKPOINT_DATABASE_REVISION,)

    _alembic(data_root, "downgrade", "0004_project_preflight")

    assert not {"project_checkpoints", "checkpoint_files"}.intersection(_tables(database_path))
    assert "project_preflight_runs" in _tables(database_path)
