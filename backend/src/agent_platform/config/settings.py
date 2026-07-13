from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_root() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "AgentProgram"
    return Path.home() / ".agent-program"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_PLATFORM_",
        env_file=None,
        extra="forbid",
        hide_input_in_errors=True,
    )

    host: str = "127.0.0.1"
    port: int = 0
    data_root: Path = Field(default_factory=default_data_root)
    session_token: str = Field(repr=False, exclude=True)
    log_level: str = "INFO"
    worker_heartbeat_timeout_seconds: float = 15.0

    @field_validator("session_token")
    @classmethod
    def validate_session_token(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session_token must not be empty")
        if not value.isascii():
            raise ValueError("session_token must contain only ASCII characters")
        return value

    @property
    def database_path(self) -> Path:
        return self.data_root / "data" / "agent.db"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path.as_posix()}"

    @property
    def snapshot_root(self) -> Path:
        return self.data_root / "snapshots"

    @property
    def log_root(self) -> Path:
        return self.data_root / "logs"

    @property
    def backup_root(self) -> Path:
        return self.data_root / "backups"

    @property
    def runtime_root(self) -> Path:
        return self.data_root / "runtime"

    def ensure_directories(self) -> None:
        for path in (
            self.database_path.parent,
            self.snapshot_root,
            self.log_root,
            self.backup_root,
            self.runtime_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
