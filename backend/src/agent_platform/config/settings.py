from __future__ import annotations

import math
import os
from datetime import timedelta
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
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

    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=0, ge=0, le=65535)
    data_root: Path = Field(default_factory=default_data_root)
    session_token: str = Field(repr=False, exclude=True)
    log_level: str = "INFO"
    log_file_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=64 * 1024,
        le=1024 * 1024 * 1024,
    )
    log_record_max_bytes: int = Field(default=32 * 1024, ge=1024, le=64 * 1024)
    log_file_retained_count: int = Field(default=5, ge=1, le=50)
    log_file_retention_days: int = Field(default=30, ge=1, le=3650)
    log_queue_capacity: int = Field(default=4096, ge=64, le=65_536)
    log_shutdown_drain_seconds: float = Field(default=1.0, ge=0.05, le=10.0)
    worker_heartbeat_timeout_seconds: float = 15.0
    worker_watchdog_interval_seconds: float = 1.0

    @field_validator("session_token")
    @classmethod
    def validate_session_token(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session_token must not be empty")
        if not value.isascii():
            raise ValueError("session_token must contain only ASCII characters")
        return value

    @field_validator(
        "worker_heartbeat_timeout_seconds",
        "worker_watchdog_interval_seconds",
        "log_shutdown_drain_seconds",
    )
    @classmethod
    def validate_positive_finite_interval(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("interval must be a positive finite number")
        return value

    @model_validator(mode="after")
    def watchdog_must_run_before_timeout(self) -> Self:
        if self.worker_watchdog_interval_seconds >= self.worker_heartbeat_timeout_seconds:
            raise ValueError("worker watchdog interval must be shorter than heartbeat timeout")
        return self

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

    @property
    def log_file_retention_age(self) -> timedelta:
        return timedelta(days=self.log_file_retention_days)

    @property
    def log_shutdown_drain_timeout(self) -> timedelta:
        return timedelta(seconds=self.log_shutdown_drain_seconds)

    def ensure_directories(self) -> None:
        for path in (
            self.database_path.parent,
            self.snapshot_root,
            self.log_root,
            self.backup_root,
            self.runtime_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
