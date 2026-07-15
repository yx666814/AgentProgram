from pathlib import Path

import pytest
from sqlalchemy import func, select
from tests.integration.test_project_repository import _registration

from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.projects import CheckpointReason, ProjectManifest
from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.models import (
    CheckpointFileRow,
    EventLogRow,
    ProjectCheckpointRow,
)
from agent_platform.infrastructure.database.session import create_database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agent_platform.infrastructure.projects.checkpoints import CheckpointStore


@pytest.mark.asyncio
async def test_checkpoint_index_and_event_commit_atomically(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "file.txt").write_text("checkpoint", encoding="utf-8")
    registration = _registration(workspace)
    checkpoint = CheckpointStore(tmp_path / "snapshots").create(
        workspace,
        ProjectManifest(
            schema_version=1,
            project_id="project_1",
            manifest_version=1,
        ),
        reason=CheckpointReason.MANUAL,
        checkpoint_id="checkpoint_one",
    )
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            await uow.projects.add(registration)
            await uow.commit()
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            await uow.projects.record_checkpoint(checkpoint)
            await uow.events.append(
                envelope=EventEnvelope(
                    schema_version=1,
                    event_type="project.checkpoint_created",
                    correlation_id="checkpoint_project_1",
                    actor=ActorRef(type=ActorType.SYSTEM),
                    source=EventSource.BACKEND,
                    occurred_at=checkpoint.created_at,
                    project_id="project_1",
                    payload={
                        "checkpoint_id": checkpoint.id,
                        "content_hash": checkpoint.content_hash,
                    },
                ),
                aggregate_type="project",
                aggregate_id="project_1",
            )
            await uow.commit()
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            persisted = await uow.projects.get_checkpoint(checkpoint.id)
            listed = await uow.projects.list_checkpoints("project_1")
            referenced = await uow.projects.list_referenced_checkpoint_hashes()
        async with database.sessions() as session:
            event_count = await session.scalar(select(func.count()).select_from(EventLogRow))
    finally:
        await database.dispose()

    assert persisted == checkpoint
    assert listed == (checkpoint,)
    assert referenced == frozenset(file.content_hash for file in checkpoint.files)
    assert event_count == 1


@pytest.mark.asyncio
async def test_checkpoint_index_rolls_back_without_event(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "file.txt").write_text("checkpoint", encoding="utf-8")
    registration = _registration(workspace)
    checkpoint = CheckpointStore(tmp_path / "snapshots").create(
        workspace,
        ProjectManifest(
            schema_version=1,
            project_id="project_1",
            manifest_version=1,
        ),
        reason=CheckpointReason.MANUAL,
    )
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            await uow.projects.add(registration)
            await uow.commit()
        with pytest.raises(RuntimeError, match="abort checkpoint"):
            async with SqlAlchemyUnitOfWork(database.sessions) as uow:
                await uow.projects.record_checkpoint(checkpoint)
                await uow.events.append(
                    envelope=EventEnvelope(
                        schema_version=1,
                        event_type="project.checkpoint_created",
                        correlation_id="checkpoint_project_1",
                        actor=ActorRef(type=ActorType.SYSTEM),
                        source=EventSource.BACKEND,
                        occurred_at=checkpoint.created_at,
                        project_id="project_1",
                        payload={"checkpoint_id": checkpoint.id},
                    ),
                    aggregate_type="project",
                    aggregate_id="project_1",
                )
                raise RuntimeError("abort checkpoint")
        async with database.sessions() as session:
            checkpoint_count = await session.scalar(
                select(func.count()).select_from(ProjectCheckpointRow)
            )
            file_count = await session.scalar(select(func.count()).select_from(CheckpointFileRow))
            event_count = await session.scalar(select(func.count()).select_from(EventLogRow))
    finally:
        await database.dispose()

    assert (checkpoint_count, file_count, event_count) == (0, 0, 0)
