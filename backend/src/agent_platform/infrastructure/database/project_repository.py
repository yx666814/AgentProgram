from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.domain.projects import (
    PersistedProjectManifest,
    Project,
    ProjectManifest,
    ProjectRegistration,
    ProjectStatus,
    Workspace,
    WorkspaceMode,
)
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.infrastructure.database.models import (
    ProjectManifestRow,
    ProjectRow,
    WorkspaceRow,
)


class ProjectManifestConflictError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            code="project.manifest_version_conflict",
            message="Manifest version has changed",
            category=ErrorCategory.CONFLICT,
        )


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

    async def save_manifest(
        self,
        persisted: PersistedProjectManifest,
        *,
        expected_version: int | None,
    ) -> None:
        manifest = persisted.manifest
        row = await self._session.get(ProjectManifestRow, manifest.project_id)
        if row is None:
            if expected_version is not None or manifest.manifest_version != 1:
                raise ProjectManifestConflictError()
            self._session.add(
                ProjectManifestRow(
                    project_id=manifest.project_id,
                    schema_version=manifest.schema_version,
                    manifest_version=manifest.manifest_version,
                    content_hash=persisted.content_hash,
                    document=manifest.model_dump(mode="json"),
                    updated_at=persisted.updated_at,
                )
            )
        else:
            if (
                expected_version is None
                or row.manifest_version != expected_version
                or manifest.manifest_version != expected_version + 1
            ):
                raise ProjectManifestConflictError()
            row.schema_version = manifest.schema_version
            row.manifest_version = manifest.manifest_version
            row.content_hash = persisted.content_hash
            row.document = manifest.model_dump(mode="json")
            row.updated_at = persisted.updated_at
        await self._session.flush()

    async def get_manifest(self, project_id: str) -> PersistedProjectManifest | None:
        row = await self._session.get(ProjectManifestRow, project_id)
        if row is None:
            return None
        manifest = ProjectManifest.model_validate_json(
            json.dumps(row.document, ensure_ascii=False, separators=(",", ":")),
            strict=True,
        )
        if (
            manifest.project_id != row.project_id
            or manifest.schema_version != row.schema_version
            or manifest.manifest_version != row.manifest_version
        ):
            raise ValueError("persisted manifest metadata is inconsistent")
        return PersistedProjectManifest(
            schema_version=1,
            manifest=manifest,
            content_hash=row.content_hash,
            updated_at=row.updated_at,
        )


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
