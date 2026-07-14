from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from tests.integration.test_project_repository import _registration

from agent_platform.application.projects.changes import (
    detect_external_changes,
    detect_file_conflicts,
)
from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.projects import (
    CheckpointFile,
    CheckpointReason,
    ConflictResolution,
    FileConflictStatus,
    ProjectCheckpoint,
)
from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.models import EventLogRow
from agent_platform.infrastructure.database.project_repository import (
    FileConflictVersionError,
)
from agent_platform.infrastructure.database.session import create_database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


def _checkpoint(checkpoint_id: str, content_hash: str) -> ProjectCheckpoint:
    return ProjectCheckpoint(
        schema_version=1,
        id=checkpoint_id,
        project_id="project_1",
        manifest_version=1,
        reason=CheckpointReason.MANUAL,
        content_hash="f" * 64,
        files=(
            CheckpointFile(
                relative_path="file.txt",
                content_hash=content_hash,
                byte_size=1,
            ),
        ),
        total_bytes=1,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_external_changes_and_conflicts_round_trip_and_resolve(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registration = _registration(workspace)
    baseline = _checkpoint("checkpoint_base", "a" * 64)
    user = _checkpoint("checkpoint_user", "b" * 64)
    agent = _checkpoint("checkpoint_agent", "c" * 64)
    changes = detect_external_changes(baseline, user)
    conflicts = detect_file_conflicts(baseline, user, agent)
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            await uow.projects.add(registration)
            await uow.commit()
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            await uow.projects.record_external_changes(changes)
            await uow.projects.record_file_conflicts(conflicts)
            await uow.events.append(
                envelope=EventEnvelope(
                    schema_version=1,
                    event_type="file_conflict.detected",
                    correlation_id="conflict_project_1",
                    actor=ActorRef(type=ActorType.SYSTEM),
                    source=EventSource.BACKEND,
                    occurred_at=conflicts[0].created_at,
                    project_id="project_1",
                    payload={"conflict_ids": [conflict.id for conflict in conflicts]},
                ),
                aggregate_type="project",
                aggregate_id="project_1",
            )
            await uow.commit()
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            persisted_changes = await uow.projects.list_open_external_changes("project_1")
            persisted_conflicts = await uow.projects.list_open_file_conflicts("project_1")
            acknowledged = await uow.projects.acknowledge_external_change(changes[0].id)
            await uow.commit()
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            resolved = await uow.projects.resolve_file_conflict(
                conflicts[0].id,
                ConflictResolution.KEEP_USER,
                expected_version=1,
                resolved_at=datetime.now(UTC),
            )
            await uow.commit()
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            remaining = await uow.projects.list_open_file_conflicts("project_1")
            remaining_changes = await uow.projects.list_open_external_changes("project_1")
        async with database.sessions() as session:
            event_count = await session.scalar(select(func.count()).select_from(EventLogRow))
    finally:
        await database.dispose()

    assert persisted_changes == changes
    assert persisted_conflicts == conflicts
    assert acknowledged.status.value == "acknowledged"
    assert resolved.status is FileConflictStatus.RESOLVED
    assert resolved.resolution is ConflictResolution.KEEP_USER
    assert resolved.version == 2
    assert remaining == ()
    assert remaining_changes == ()
    assert event_count == 1


@pytest.mark.asyncio
async def test_conflict_resolution_rejects_stale_version(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registration = _registration(workspace)
    conflicts = detect_file_conflicts(
        _checkpoint("checkpoint_base", "a" * 64),
        _checkpoint("checkpoint_user", "b" * 64),
        _checkpoint("checkpoint_agent", "c" * 64),
    )
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            await uow.projects.add(registration)
            await uow.projects.record_file_conflicts(conflicts)
            await uow.commit()
        with pytest.raises(FileConflictVersionError) as raised:
            async with SqlAlchemyUnitOfWork(database.sessions) as uow:
                await uow.projects.resolve_file_conflict(
                    conflicts[0].id,
                    ConflictResolution.KEEP_AGENT,
                    expected_version=2,
                    resolved_at=datetime.now(UTC),
                )
    finally:
        await database.dispose()

    assert raised.value.details == {"current_version": 1}
