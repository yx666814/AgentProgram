from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

MIGRATIONS_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = MIGRATIONS_ROOT.parent
SRC_ROOT = BACKEND_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_platform.infrastructure.database import models  # noqa: E402
from agent_platform.infrastructure.database.base import Base  # noqa: E402

_MODEL_TABLES = (models.EventLogRow.__table__, models.OutboxEventRow.__table__)

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
database_path.parent.mkdir(parents=True, exist_ok=True)
database_url = f"sqlite:///{database_path.as_posix()}"
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
