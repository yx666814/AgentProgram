from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.domain.projects import (
    Project,
    ProjectRegistration,
    ProjectStatus,
    Workspace,
    WorkspaceMode,
)
from agent_platform.infrastructure.database.models import ProjectRow, WorkspaceRow


class SqlAlchemyProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, registration: ProjectRegistration) -> None:
        project = registration.project
        workspace = registration.workspace
        self._session.add(
            ProjectRow(
                id=project.id,
                name=project.name,
                goal=project.goal,
                status=project.status.value,
                version=project.version,
                created_at=project.created_at,
                updated_at=project.updated_at,
            )
        )
        self._session.add(
            WorkspaceRow(
                id=workspace.id,
                project_id=workspace.project_id,
                mode=workspace.mode.value,
                root_path=workspace.root_path,
                canonical_root_path=workspace.canonical_root_path,
                created_at=workspace.created_at,
            )
        )
        await self._session.flush()

    async def get(self, project_id: str) -> ProjectRegistration | None:
        statement = (
            select(ProjectRow, WorkspaceRow)
            .join(WorkspaceRow, WorkspaceRow.project_id == ProjectRow.id)
            .where(ProjectRow.id == project_id)
        )
        result = (await self._session.execute(statement)).one_or_none()
        if result is None:
            return None
        return _registration_from_rows(*result)

    async def list(self) -> tuple[ProjectRegistration, ...]:
        statement = (
            select(ProjectRow, WorkspaceRow)
            .join(WorkspaceRow, WorkspaceRow.project_id == ProjectRow.id)
            .order_by(ProjectRow.updated_at.desc(), ProjectRow.id)
        )
        rows = (await self._session.execute(statement)).all()
        return tuple(_registration_from_rows(project, workspace) for project, workspace in rows)

    async def find_by_canonical_root(
        self,
        canonical_root_path: str,
    ) -> ProjectRegistration | None:
        statement = (
            select(ProjectRow, WorkspaceRow)
            .join(WorkspaceRow, WorkspaceRow.project_id == ProjectRow.id)
            .where(WorkspaceRow.canonical_root_path == canonical_root_path)
        )
        result = (await self._session.execute(statement)).one_or_none()
        if result is None:
            return None
        return _registration_from_rows(*result)


def _registration_from_rows(
    project: ProjectRow,
    workspace: WorkspaceRow,
) -> ProjectRegistration:
    return ProjectRegistration(
        schema_version=1,
        project=Project(
            schema_version=1,
            id=project.id,
            name=project.name,
            goal=project.goal,
            status=ProjectStatus(project.status),
            version=project.version,
            created_at=project.created_at,
            updated_at=project.updated_at,
        ),
        workspace=Workspace(
            schema_version=1,
            id=workspace.id,
            project_id=workspace.project_id,
            mode=WorkspaceMode(workspace.mode),
            root_path=workspace.root_path,
            canonical_root_path=workspace.canonical_root_path,
            created_at=workspace.created_at,
        ),
    )
