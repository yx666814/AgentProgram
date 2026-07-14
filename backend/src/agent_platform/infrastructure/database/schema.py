from typing import Final

FOUNDATION_DATABASE_REVISION: Final[str] = "0001_foundation"
RELIABLE_OUTBOX_DATABASE_REVISION: Final[str] = "0002_reliable_outbox"
PROJECT_REGISTRY_DATABASE_REVISION: Final[str] = "0003_project_registry"
PROJECT_PREFLIGHT_DATABASE_REVISION: Final[str] = "0004_project_preflight"
CURRENT_DATABASE_REVISION: Final[str] = PROJECT_PREFLIGHT_DATABASE_REVISION
REQUIRED_DATABASE_TABLES: Final[frozenset[str]] = frozenset(
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
