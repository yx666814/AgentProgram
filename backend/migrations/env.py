from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, inspect, pool, text
from sqlalchemy.engine import Connection

MIGRATIONS_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = MIGRATIONS_ROOT.parent
SRC_ROOT = BACKEND_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_platform.infrastructure.database import models  # noqa: E402
from agent_platform.infrastructure.database.backup import (  # noqa: E402
    BackupReason,
    create_verified_backup,
)
from agent_platform.infrastructure.database.base import Base  # noqa: E402
from agent_platform.infrastructure.database.instance_lock import (  # noqa: E402
    ApplicationInstanceLock,
)
from agent_platform.infrastructure.database.migration_rendering import render_item  # noqa: E402

_MODEL_TABLES = (
    models.EventLogRow.__table__,
    models.OutboxEventRow.__table__,
    models.OutboxDeliveryRow.__table__,
    models.LocalAuditEventRow.__table__,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _data_root() -> Path:
    configured_root = os.getenv("AGENT_PLATFORM_DATA_ROOT")
    if configured_root:
        return Path(configured_root)

    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "AgentProgram"

    return Path.home() / ".agent-program"


database_path = _data_root() / "data" / "agent.db"
database_url = f"sqlite:///{database_path.as_posix()}"
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def _drop_empty_sqlite_version_table(connection: Connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    inspector = inspect(connection)
    if not inspector.has_table("alembic_version"):
        return

    version_count = connection.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar_one()
    if version_count == 0:
        connection.exec_driver_sql("DROP TABLE alembic_version")


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    data_root = _data_root()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    instance_lock = ApplicationInstanceLock.acquire(data_root / "runtime")
    try:
        if database_path.exists() and database_path.stat().st_size > 0:
            create_verified_backup(
                database_path,
                data_root / "backups",
                reason=BackupReason.PRE_MIGRATION,
            )
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_item=render_item,
            )

            with context.begin_transaction():
                context.run_migrations()
                _drop_empty_sqlite_version_table(connection)
    finally:
        connectable.dispose()
        instance_lock.release()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
