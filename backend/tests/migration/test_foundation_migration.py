from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

import agent_platform.infrastructure.database.schema as database_schema
from agent_platform.infrastructure.database.schema import (
    CURRENT_DATABASE_REVISION,
    FOUNDATION_DATABASE_REVISION,
    PROJECT_PREFLIGHT_DATABASE_REVISION,
    REQUIRED_DATABASE_TABLES,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_foundation_module() -> ModuleType:
    path = BACKEND_ROOT / "migrations/versions/0001_foundation.py"
    spec = importlib.util.spec_from_file_location("foundation_0001", path)
    if spec is None or spec.loader is None:
        raise AssertionError("foundation migration could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_foundation_migration_uses_immutable_foundation_revision() -> None:
    assert _load_foundation_module().revision == FOUNDATION_DATABASE_REVISION


def test_foundation_revision_does_not_change_when_current_revision_advances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        database_schema,
        "CURRENT_DATABASE_REVISION",
        "0002_next_revision",
    )

    assert _load_foundation_module().revision == FOUNDATION_DATABASE_REVISION


def test_current_database_revision_advances_to_project_preflight() -> None:
    assert CURRENT_DATABASE_REVISION == PROJECT_PREFLIGHT_DATABASE_REVISION


def test_required_database_tables_are_shared() -> None:
    assert REQUIRED_DATABASE_TABLES == frozenset(
        {
            "alembic_version",
            "event_log",
            "outbox_events",
            "outbox_deliveries",
            "local_audit_events",
            "projects",
            "workspaces",
            "project_manifests",
            "project_instructions",
            "project_preflight_runs",
        }
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
        "outbox_deliveries",
        "local_audit_events",
        "projects",
        "workspaces",
        "project_manifests",
        "project_instructions",
        "project_preflight_runs",
    }

    _run_alembic("downgrade", "base", data_root=data_root)

    downgraded_tables = _table_names(database_path)
    downgraded_application_tables = {
        name for name in downgraded_tables if not name.startswith("sqlite_")
    }
    assert downgraded_application_tables == set()
