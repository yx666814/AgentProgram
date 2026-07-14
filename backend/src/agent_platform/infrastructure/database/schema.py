from typing import Final

FOUNDATION_DATABASE_REVISION: Final[str] = "0001_foundation"
RELIABLE_OUTBOX_DATABASE_REVISION: Final[str] = "0002_reliable_outbox"
CURRENT_DATABASE_REVISION: Final[str] = RELIABLE_OUTBOX_DATABASE_REVISION
REQUIRED_DATABASE_TABLES: Final[frozenset[str]] = frozenset(
    {
        "alembic_version",
        "event_log",
        "outbox_events",
        "outbox_deliveries",
        "local_audit_events",
    }
)
