from typing import Final

FOUNDATION_DATABASE_REVISION: Final[str] = "0001_foundation"
RELIABLE_OUTBOX_DATABASE_REVISION: Final[str] = "0002_reliable_outbox"
PROJECT_REGISTRY_DATABASE_REVISION: Final[str] = "0003_project_registry"
PROJECT_PREFLIGHT_DATABASE_REVISION: Final[str] = "0004_project_preflight"
PROJECT_CHECKPOINT_DATABASE_REVISION: Final[str] = "0005_project_checkpoints"
PROJECT_CONFLICT_DATABASE_REVISION: Final[str] = "0006_project_conflicts"
WORKFLOW_DATABASE_REVISION: Final[str] = "0007_workflows"
MODEL_RUNTIME_DATABASE_REVISION: Final[str] = "0008_model_runtime"
CURRENT_DATABASE_REVISION: Final[str] = MODEL_RUNTIME_DATABASE_REVISION
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
        "project_checkpoints",
        "checkpoint_files",
        "external_changes",
        "file_conflicts",
        "workflows",
        "stage_runs",
        "rooms",
        "messages",
        "tasks",
        "model_profiles",
        "room_model_assignments",
        "agent_runs",
        "model_calls",
        "usage_records",
        "conversation_summaries",
    }
)
