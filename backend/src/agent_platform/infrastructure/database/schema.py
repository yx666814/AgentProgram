from typing import Final

CURRENT_DATABASE_REVISION: Final[str] = "0001_foundation"
REQUIRED_DATABASE_TABLES: Final[frozenset[str]] = frozenset(
    {"alembic_version", "event_log", "outbox_events"}
)
