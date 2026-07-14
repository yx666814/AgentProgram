from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.projects import (
    Project,
    ProjectRegistration,
    ProjectStatus,
    Workspace,
    WorkspaceMode,
)
from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.models import EventLogRow, ProjectRow
from agent_platform.infrastructure.database.session import create_database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


def _registration(
    tmp_path: Path,
    *,
    project_id: str = "project_1",
    workspace_id: str = "workspace_1",
    updated_at: datetime | None = None,
) -> ProjectRegistration:
    now = updated_at or datetime.now(UTC)
    root = str(tmp_path.resolve())
    return ProjectRegistration(
        schema_version=1,
        project=Project(
            schema_version=1,
            id=project_id,
            name=f"Project {project_id}",
            goal="Exercise the project registry",
            status=ProjectStatus.PREFLIGHT_REQUIRED,
            created_at=now,
            updated_at=now,
            version=1,
        ),
        workspace=Workspace(
            schema_version=1,
            id=workspace_id,
            project_id=project_id,
            mode=WorkspaceMode.DIRECT,
            root_path=root,
            canonical_root_path=root,
            created_at=now,
        ),
    )


def _created_event(project_id: str, occurred_at: datetime) -> EventEnvelope:
    return EventEnvelope(
        schema_version=1,
        event_type="project.created",
        correlation_id=f"create_{project_id}",
        actor=ActorRef(type=ActorType.USER, id="user_local"),
        source=EventSource.BACKEND,
        occurred_at=occurred_at,
        project_id=project_id,
        payload={"status": ProjectStatus.PREFLIGHT_REQUIRED.value},
    )


@pytest.mark.asyncio
async def test_project_and_created_event_commit_atomically(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    registration = _registration(tmp_path / "workspace")
    (tmp_path / "workspace").mkdir()
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            await uow.projects.add(registration)
            await uow.events.append(
                envelope=_created_event(
                    registration.project.id,
                    registration.project.created_at,
                ),
                aggregate_type="project",
                aggregate_id=registration.project.id,
            )
            await uow.commit()

        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            persisted = await uow.projects.get(registration.project.id)
            by_root = await uow.projects.find_by_canonical_root(
                registration.workspace.canonical_root_path
            )
        async with database.sessions() as session:
            event_count = await session.scalar(select(func.count()).select_from(EventLogRow))
    finally:
        await database.dispose()

    assert persisted == registration
    assert by_root == registration
    assert event_count == 1


@pytest.mark.asyncio
async def test_project_and_event_roll_back_together(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    registration = _registration(workspace_root)
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        with pytest.raises(RuntimeError, match="abort registration"):
            async with SqlAlchemyUnitOfWork(database.sessions) as uow:
                await uow.projects.add(registration)
                await uow.events.append(
                    envelope=_created_event(
                        registration.project.id,
                        registration.project.created_at,
                    ),
                    aggregate_type="project",
                    aggregate_id=registration.project.id,
                )
                raise RuntimeError("abort registration")

        async with database.sessions() as session:
            project_count = await session.scalar(select(func.count()).select_from(ProjectRow))
            event_count = await session.scalar(select(func.count()).select_from(EventLogRow))
    finally:
        await database.dispose()

    assert project_count == 0
    assert event_count == 0


@pytest.mark.asyncio
async def test_workspace_root_is_unique_and_projects_list_newest_first(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path / "agent.db")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    now = datetime.now(UTC)
    first = _registration(workspace_root, updated_at=now)
    duplicate = _registration(
        workspace_root,
        project_id="project_2",
        workspace_id="workspace_2",
        updated_at=now + timedelta(seconds=1),
    )
    other_root = tmp_path / "other"
    other_root.mkdir()
    newest = _registration(
        other_root,
        project_id="project_3",
        workspace_id="workspace_3",
        updated_at=now + timedelta(seconds=2),
    )
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            await uow.projects.add(first)
            await uow.commit()
        with pytest.raises(IntegrityError):
            async with SqlAlchemyUnitOfWork(database.sessions) as uow:
                await uow.projects.add(duplicate)
                await uow.commit()
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            await uow.projects.add(newest)
            await uow.commit()
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            projects = await uow.projects.list()
    finally:
        await database.dispose()

    assert [item.project.id for item in projects] == ["project_3", "project_1"]
