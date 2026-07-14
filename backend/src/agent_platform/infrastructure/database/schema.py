from typing import Final

FOUNDATION_DATABASE_REVISION: Final[str] = "0001_foundation"
CURRENT_DATABASE_REVISION: Final[str] = FOUNDATION_DATABASE_REVISION
REQUIRED_DATABASE_TABLES: Final[frozenset[str]] = frozenset(
    {"alembic_version", "event_log", "outbox_events"}
)
