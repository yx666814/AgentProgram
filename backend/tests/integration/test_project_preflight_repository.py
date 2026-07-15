from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from tests.integration.test_project_repository import _registration

from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.projects import (
    PreflightCheck,
    PreflightStatus,
    ProjectPreflightResult,
    ProjectStatus,
)
from agent_platform.infrastructure.database.base import Base
from agent_platform.infrastructure.database.models import EventLogRow, ProjectPreflightRow
from agent_platform.infrastructure.database.project_repository import (
    ProjectVersionConflictError,
)
from agent_platform.infrastructure.database.session import create_database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


def _preflight(status: PreflightStatus, now: datetime) -> ProjectPreflightResult:
    return ProjectPreflightResult(
        schema_version=1,
        id=f"preflight_{status.value}",
        project_id="project_1",
        manifest_version=1,
        status=status,
        checks=(
            PreflightCheck(
                code="workspace.boundary",
                status=status,
                message="Workspace boundary result",
            ),
        ),
        started_at=now,
        completed_at=now,
    )


@pytest.mark.asyncio
async def test_preflight_state_and_event_commit_together(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    registration = _registration(workspace_root)
    now = datetime.now(UTC)
    result = _preflight(PreflightStatus.WARNING, now)
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            await uow.projects.add(registration)
            await uow.commit()
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            updated = await uow.projects.record_preflight(
                result,
                expected_project_version=1,
            )
            await uow.events.append(
                envelope=EventEnvelope(
                    schema_version=1,
                    event_type="project.preflight_completed",
                    correlation_id="preflight_project_1",
                    actor=ActorRef(type=ActorType.SYSTEM),
                    source=EventSource.BACKEND,
                    occurred_at=now,
                    project_id="project_1",
                    payload={"status": result.status.value},
                ),
                aggregate_type="project",
                aggregate_id="project_1",
            )
            await uow.commit()
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            persisted = await uow.projects.get("project_1")
            latest = await uow.projects.get_latest_preflight("project_1")
        async with database.sessions() as session:
            event_count = await session.scalar(select(func.count()).select_from(EventLogRow))
            preflight_count = await session.scalar(
                select(func.count()).select_from(ProjectPreflightRow)
            )
    finally:
        await database.dispose()

    assert updated.status is ProjectStatus.READY
    assert updated.version == 2
    assert persisted is not None and persisted.project == updated
    assert latest == result
    assert (event_count, preflight_count) == (1, 1)


@pytest.mark.asyncio
async def test_preflight_rejects_stale_project_version(tmp_path: Path) -> None:
    database = create_database(tmp_path / "agent.db")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    registration = _registration(workspace_root)
    try:
        async with database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with SqlAlchemyUnitOfWork(database.sessions) as uow:
            await uow.projects.add(registration)
            await uow.commit()
        with pytest.raises(ProjectVersionConflictError) as raised:
            async with SqlAlchemyUnitOfWork(database.sessions) as uow:
                await uow.projects.record_preflight(
                    _preflight(PreflightStatus.PASS, datetime.now(UTC)),
                    expected_project_version=2,
                )
                await uow.commit()
    finally:
        await database.dispose()

    assert raised.value.details == {"current_version": 1}
