from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from io import TextIOWrapper
from pathlib import Path
from typing import IO, Literal, cast
from urllib.parse import urlsplit

import psutil  # type: ignore[import-untyped]
import uvicorn
from alembic import command
from alembic.config import Config
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from agent_platform.application.system_control import ShutdownCoordinator
from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.infrastructure.database.backup import (
    BackupReason,
    restore_verified_backup,
    verify_backup,
)
from agent_platform.infrastructure.database.schema import CURRENT_DATABASE_REVISION
from agent_platform.infrastructure.logging.configure import prepare_uvicorn_logging
from agent_platform.infrastructure.model_runtime import DesktopHttpSecretStore
from agent_platform.ports.secrets import SecretStore

READY_PREFIX = "AGENT_PLATFORM_READY "
MAX_STARTUP_FRAME_BYTES = 4096
BACKEND_ROOT = (
    Path(cast(str, vars(sys)["_MEIPASS"]))
    if bool(getattr(sys, "frozen", False))
    else Path(__file__).resolve().parents[2]
)


class DesktopStartupFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    protocol_version: Literal[1]
    session_token: SecretStr
    data_root: Path
    parent_pid: int = Field(ge=1)
    secret_bridge_origin: str = Field(min_length=1, max_length=200)
    secret_bridge_token: SecretStr
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=0, ge=0, le=65535)

    @field_validator("secret_bridge_origin")
    @classmethod
    def validate_secret_bridge_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("secret bridge origin must be a loopback HTTP origin")
        return value.rstrip("/")


@dataclass(frozen=True, slots=True)
class DesktopLaunch:
    settings: Settings
    parent_pid: int
    secret_store: SecretStore


class DesktopReadyServer(uvicorn.Server):
    def __init__(
        self,
        config: uvicorn.Config,
        *,
        ready_stream: IO[str],
        parent_pid: int,
    ) -> None:
        super().__init__(config)
        self._ready_stream = ready_stream
        try:
            parent = psutil.Process(parent_pid)
            self._parent_identity = (parent_pid, float(parent.create_time()))
        except (psutil.Error, OSError):
            raise RuntimeError("desktop parent process is unavailable") from None

    async def on_tick(self, counter: int) -> bool:
        if counter % 10 == 0 and not self._parent_is_running():
            self.should_exit = True
        return await super().on_tick(counter)

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.should_exit:
            return
        listeners = [listener for server in self.servers for listener in server.sockets or ()]
        if len(listeners) != 1:
            self.should_exit = True
            raise RuntimeError("desktop sidecar must expose exactly one listener")
        address = listeners[0].getsockname()
        if not isinstance(address, tuple) or len(address) < 2:
            self.should_exit = True
            raise RuntimeError("desktop sidecar listener address is invalid")
        host, port = address[0], address[1]
        if host != "127.0.0.1" or not isinstance(port, int) or not 1 <= port <= 65535:
            self.should_exit = True
            raise RuntimeError("desktop sidecar listener is not a dynamic IPv4 loopback port")
        frame = {
            "protocol_version": 1,
            "status": "ready",
            "host": host,
            "port": port,
            "pid": os.getpid(),
        }
        self._ready_stream.write(READY_PREFIX + json.dumps(frame, separators=(",", ":")) + "\n")
        self._ready_stream.flush()

    def _parent_is_running(self) -> bool:
        parent_pid, created_at = self._parent_identity
        try:
            parent = psutil.Process(parent_pid)
            return bool(parent.is_running()) and float(parent.create_time()) == created_at
        except (psutil.Error, OSError):
            return False


def read_desktop_settings(stream: IO[str]) -> DesktopLaunch:
    serialized = stream.readline(MAX_STARTUP_FRAME_BYTES + 1)
    if not serialized.endswith("\n") or len(serialized.encode("utf-8")) > MAX_STARTUP_FRAME_BYTES:
        raise RuntimeError("desktop startup frame is missing or oversized")
    try:
        frame = DesktopStartupFrame.model_validate_json(serialized)
    except ValueError:
        raise RuntimeError("desktop startup frame is invalid") from None
    return DesktopLaunch(
        settings=Settings(
            host=frame.host,
            port=frame.port,
            data_root=frame.data_root,
            session_token=frame.session_token.get_secret_value(),
        ),
        parent_pid=frame.parent_pid,
        secret_store=DesktopHttpSecretStore(
            frame.secret_bridge_origin,
            frame.secret_bridge_token,
        ),
    )


def _database_revision(database_path: Path) -> str | None:
    if not database_path.is_file() or database_path.stat().st_size == 0:
        return None
    try:
        with closing(
            sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
        ) as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            ).fetchone()
            if table is None:
                return None
            rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
    except sqlite3.DatabaseError:
        return None
    if len(rows) != 1 or not isinstance(rows[0][0], str):
        return None
    return str(rows[0][0])


def _backup_manifests(backup_root: Path) -> set[Path]:
    if not backup_root.is_dir():
        return set()
    return set(backup_root.glob("*.sqlite3.manifest.json"))


def _restore_new_migration_backup(
    settings: Settings,
    previous_manifests: set[Path],
) -> bool:
    candidates = sorted(
        _backup_manifests(settings.backup_root) - previous_manifests,
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for manifest_path in candidates:
        try:
            verified = verify_backup(manifest_path)
        except (OSError, RuntimeError):
            continue
        if verified.manifest.reason is not BackupReason.PRE_MIGRATION:
            continue
        restore_verified_backup(manifest_path, settings.database_path)
        return True
    return False


def ensure_desktop_database(settings: Settings, *, backend_root: Path = BACKEND_ROOT) -> None:
    if _database_revision(settings.database_path) == CURRENT_DATABASE_REVISION:
        return
    settings.ensure_directories()
    os.environ["AGENT_PLATFORM_DATA_ROOT"] = str(settings.data_root)
    configuration = Config(str(backend_root / "alembic.ini"))
    configuration.set_main_option("script_location", str(backend_root / "migrations"))
    previous_manifests = _backup_manifests(settings.backup_root)
    try:
        command.upgrade(configuration, "head")
        if _database_revision(settings.database_path) != CURRENT_DATABASE_REVISION:
            raise RuntimeError("desktop database migration did not reach the required revision")
    except Exception:
        try:
            restored = _restore_new_migration_backup(settings, previous_manifests)
        except Exception:
            raise RuntimeError("desktop database migration and backup recovery failed") from None
        if restored:
            raise RuntimeError(
                "desktop database migration failed and the previous backup was restored"
            ) from None
        raise RuntimeError(
            "desktop database migration failed without a restorable backup"
        ) from None


async def serve_desktop(
    settings: Settings,
    *,
    ready_stream: IO[str],
    parent_pid: int,
    secret_store: SecretStore,
) -> None:
    prepare_uvicorn_logging(settings.log_level)
    app = create_app(settings, secret_store=secret_store)
    server = DesktopReadyServer(
        uvicorn.Config(
            app,
            host=settings.host,
            port=settings.port,
            log_config=None,
        ),
        ready_stream=ready_stream,
        parent_pid=parent_pid,
    )
    coordinator = cast(ShutdownCoordinator, app.state.shutdown_coordinator)
    coordinator.bind(lambda: setattr(server, "should_exit", True))
    await server.serve()


def main() -> None:
    cast(TextIOWrapper, sys.stdin).reconfigure(encoding="utf-8", errors="strict")
    cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8", errors="strict")
    cast(TextIOWrapper, sys.stderr).reconfigure(encoding="utf-8", errors="backslashreplace")
    launch = read_desktop_settings(sys.stdin)
    ensure_desktop_database(launch.settings)
    asyncio.run(
        serve_desktop(
            launch.settings,
            ready_stream=sys.stdout,
            parent_pid=launch.parent_pid,
            secret_store=launch.secret_store,
        )
    )
