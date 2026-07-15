from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

_BACKUP_NAME = re.compile(
    r"agent-backup-(?P<timestamp>[0-9]{8}T[0-9]{12}Z)-(?P<nonce>[0-9a-f]{32})\.sqlite3\Z"
)


class BackupReason(StrEnum):
    SCHEDULED = "scheduled"
    PRE_MIGRATION = "pre_migration"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class BackupManifest:
    format_version: int
    database_filename: str
    schema_revision: str | None
    created_at: datetime
    byte_size: int
    sha256: str
    reason: BackupReason


@dataclass(frozen=True, slots=True)
class VerifiedBackup:
    database_path: Path
    manifest_path: Path
    manifest: BackupManifest


class BackupVerificationError(RuntimeError):
    pass


def _timestamp_name(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_revision(connection: sqlite3.Connection) -> str | None:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
    ).fetchone()
    if table is None:
        return None
    rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
    if len(rows) != 1 or not isinstance(rows[0][0], str) or not rows[0][0]:
        raise BackupVerificationError("backup schema revision is invalid")
    return str(rows[0][0])


def _quick_check(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
        raise BackupVerificationError("backup integrity validation failed")


def _manifest_payload(manifest: BackupManifest) -> dict[str, object]:
    payload = asdict(manifest)
    payload["created_at"] = manifest.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    payload["reason"] = manifest.reason.value
    return payload


def create_verified_backup(
    database_path: Path,
    backup_root: Path,
    *,
    reason: BackupReason,
    now: datetime | None = None,
) -> VerifiedBackup:
    created_at = (now or datetime.now(UTC)).astimezone(UTC)
    backup_root.mkdir(parents=True, exist_ok=True)
    base_name = f"agent-backup-{_timestamp_name(created_at)}-{uuid4().hex}.sqlite3"
    database_final = backup_root / base_name
    manifest_final = backup_root / f"{base_name}.manifest.json"
    database_temp = backup_root / f".{base_name}.{uuid4().hex}.tmp"
    manifest_temp = backup_root / f".{base_name}.{uuid4().hex}.manifest.tmp"
    try:
        with (
            closing(sqlite3.connect(database_path, timeout=30)) as source,
            closing(sqlite3.connect(database_temp, timeout=30)) as destination,
        ):
            source.backup(destination)
            _quick_check(destination)
            revision = _schema_revision(destination)
        with database_temp.open("r+b") as backup_file:
            os.fsync(backup_file.fileno())
        manifest = BackupManifest(
            format_version=1,
            database_filename=base_name,
            schema_revision=revision,
            created_at=created_at,
            byte_size=database_temp.stat().st_size,
            sha256=_sha256(database_temp),
            reason=reason,
        )
        manifest_temp.write_text(
            json.dumps(_manifest_payload(manifest), separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        with manifest_temp.open("r+b") as manifest_file:
            os.fsync(manifest_file.fileno())
        os.replace(database_temp, database_final)
        os.replace(manifest_temp, manifest_final)
        return verify_backup(manifest_final)
    finally:
        database_temp.unlink(missing_ok=True)
        manifest_temp.unlink(missing_ok=True)


def verify_backup(manifest_path: Path) -> VerifiedBackup:
    if not manifest_path.name.endswith(".sqlite3.manifest.json"):
        raise BackupVerificationError("backup manifest name is invalid")
    database_name = manifest_path.name.removesuffix(".manifest.json")
    if _BACKUP_NAME.fullmatch(database_name) is None:
        raise BackupVerificationError("backup database name is invalid")
    database_path = manifest_path.with_name(database_name)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if set(raw) != {
            "format_version",
            "database_filename",
            "schema_revision",
            "created_at",
            "byte_size",
            "sha256",
            "reason",
        }:
            raise BackupVerificationError("backup manifest schema is invalid")
        manifest = BackupManifest(
            format_version=int(raw["format_version"]),
            database_filename=str(raw["database_filename"]),
            schema_revision=(
                None if raw["schema_revision"] is None else str(raw["schema_revision"])
            ),
            created_at=datetime.fromisoformat(str(raw["created_at"]).replace("Z", "+00:00")),
            byte_size=int(raw["byte_size"]),
            sha256=str(raw["sha256"]),
            reason=BackupReason(str(raw["reason"])),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise BackupVerificationError("backup manifest is invalid") from None
    if manifest.format_version != 1 or manifest.database_filename != database_name:
        raise BackupVerificationError("backup manifest is invalid")
    if not database_path.is_file() or database_path.stat().st_size != manifest.byte_size:
        raise BackupVerificationError("backup size validation failed")
    if _sha256(database_path) != manifest.sha256:
        raise BackupVerificationError("backup hash validation failed")
    try:
        with closing(
            sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
        ) as connection:
            _quick_check(connection)
            revision = _schema_revision(connection)
    except sqlite3.DatabaseError:
        raise BackupVerificationError("backup database is invalid") from None
    if revision != manifest.schema_revision:
        raise BackupVerificationError("backup schema revision mismatch")
    return VerifiedBackup(database_path, manifest_path, manifest)


def restore_verified_backup(manifest_path: Path, destination_path: Path) -> None:
    verified = verify_backup(manifest_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination_path.with_name(f".{destination_path.name}.{uuid4().hex}.restore.tmp")
    try:
        with (
            closing(sqlite3.connect(verified.database_path)) as source,
            closing(sqlite3.connect(temporary)) as destination,
        ):
            source.backup(destination)
            _quick_check(destination)
        with temporary.open("r+b") as restored:
            os.fsync(restored.fileno())
        if destination_path.exists():
            with closing(
                sqlite3.connect(destination_path, timeout=5, isolation_level=None)
            ) as current:
                busy, _, _ = current.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() or (
                    1,
                    0,
                    0,
                )
                if busy:
                    raise BackupVerificationError("database restore is busy")
                mode = current.execute("PRAGMA journal_mode=DELETE").fetchone()
                if mode is None or str(mode[0]).lower() != "delete":
                    raise BackupVerificationError("database restore could not quiesce WAL")
        os.replace(temporary, destination_path)
        with closing(
            sqlite3.connect(destination_path, isolation_level=None)
        ) as restored_connection:
            _quick_check(restored_connection)
            restored_connection.execute("PRAGMA journal_mode=WAL")
    finally:
        temporary.unlink(missing_ok=True)


def prune_backup_root(
    backup_root: Path,
    *,
    retain_count: int,
    retention_age: timedelta,
    max_entries: int,
    now: datetime | None = None,
) -> None:
    if not backup_root.exists():
        return
    entries: list[Path] = []
    for index, entry in enumerate(backup_root.iterdir()):
        if index >= max_entries:
            return
        entries.append(entry)
    verified: list[VerifiedBackup] = []
    for manifest_path in entries:
        if not manifest_path.name.endswith(".sqlite3.manifest.json"):
            continue
        try:
            verified.append(verify_backup(manifest_path))
        except BackupVerificationError:
            continue
    verified.sort(key=lambda item: item.manifest.created_at, reverse=True)
    cutoff = (now or datetime.now(UTC)) - retention_age
    keep = {
        item.manifest_path
        for index, item in enumerate(verified)
        if index == 0 or (index < retain_count and item.manifest.created_at >= cutoff)
    }
    for item in verified:
        if item.manifest_path in keep:
            continue
        item.manifest_path.unlink(missing_ok=True)
        item.database_path.unlink(missing_ok=True)
