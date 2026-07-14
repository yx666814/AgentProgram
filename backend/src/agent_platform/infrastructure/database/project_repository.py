from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.domain.projects import (
    CheckpointFile,
    CheckpointReason,
    PersistedProjectManifest,
    Project,
    ProjectCheckpoint,
    ProjectManifest,
    ProjectPreflightResult,
    ProjectRegistration,
    ProjectStatus,
    Workspace,
    WorkspaceMode,
)
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.infrastructure.database.models import (
    CheckpointFileRow,
    ProjectCheckpointRow,
    ProjectManifestRow,
    ProjectPreflightRow,
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


class ProjectVersionConflictError(DomainError):
    def __init__(self, current_version: int) -> None:
        super().__init__(
            code="project.version_conflict",
            message="Project version has changed",
            details={"current_version": current_version},
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

    async def record_preflight(
        self,
        result: ProjectPreflightResult,
        *,
        expected_project_version: int,
    ) -> Project:
        project = await self._session.get(ProjectRow, result.project_id)
        if project is None:
            raise DomainError(
                code="project.not_found",
                message="Project was not found",
                category=ErrorCategory.NOT_FOUND,
            )
        if project.version != expected_project_version:
            raise ProjectVersionConflictError(project.version)
        self._session.add(
            ProjectPreflightRow(
                id=result.id,
                project_id=result.project_id,
                schema_version=result.schema_version,
                manifest_version=result.manifest_version,
                status=result.status.value,
                checks=[check.model_dump(mode="json") for check in result.checks],
                started_at=result.started_at,
                completed_at=result.completed_at,
            )
        )
        project.status = (
            ProjectStatus.READY.value
            if result.status.value in {"pass", "warning"}
            else ProjectStatus.PREFLIGHT_REQUIRED.value
        )
        project.version += 1
        project.updated_at = result.completed_at
        await self._session.flush()
        return _project_from_row(project)

    async def get_latest_preflight(self, project_id: str) -> ProjectPreflightResult | None:
        statement = (
            select(ProjectPreflightRow)
            .where(ProjectPreflightRow.project_id == project_id)
            .order_by(ProjectPreflightRow.completed_at.desc(), ProjectPreflightRow.id.desc())
            .limit(1)
        )
        row = await self._session.scalar(statement)
        if row is None:
            return None
        document = {
            "schema_version": row.schema_version,
            "id": row.id,
            "project_id": row.project_id,
            "manifest_version": row.manifest_version,
            "status": row.status,
            "checks": row.checks,
            "started_at": row.started_at.isoformat(),
            "completed_at": row.completed_at.isoformat(),
        }
        return ProjectPreflightResult.model_validate_json(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")),
            strict=True,
        )

    async def record_checkpoint(self, checkpoint: ProjectCheckpoint) -> None:
        row = ProjectCheckpointRow(
            id=checkpoint.id,
            project_id=checkpoint.project_id,
            schema_version=checkpoint.schema_version,
            manifest_version=checkpoint.manifest_version,
            reason=checkpoint.reason.value,
            content_hash=checkpoint.content_hash,
            file_count=len(checkpoint.files),
            total_bytes=checkpoint.total_bytes,
            created_at=checkpoint.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        self._session.add_all(
            CheckpointFileRow(
                checkpoint_id=checkpoint.id,
                relative_path=file.relative_path,
                content_hash=file.content_hash,
                byte_size=file.byte_size,
            )
            for file in checkpoint.files
        )
        await self._session.flush()

    async def get_checkpoint(self, checkpoint_id: str) -> ProjectCheckpoint | None:
        row = await self._session.get(ProjectCheckpointRow, checkpoint_id)
        if row is None:
            return None
        return await self._checkpoint_from_row(row)

    async def list_checkpoints(
        self,
        project_id: str,
        *,
        limit: int = 100,
    ) -> tuple[ProjectCheckpoint, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("checkpoint list limit is invalid")
        statement = (
            select(ProjectCheckpointRow)
            .where(ProjectCheckpointRow.project_id == project_id)
            .order_by(ProjectCheckpointRow.created_at.desc(), ProjectCheckpointRow.id.desc())
            .limit(limit)
        )
        rows = (await self._session.scalars(statement)).all()
        return tuple([await self._checkpoint_from_row(row) for row in rows])

    async def list_referenced_checkpoint_hashes(self) -> frozenset[str]:
        statement = select(CheckpointFileRow.content_hash).distinct()
        return frozenset((await self._session.scalars(statement)).all())

    async def _checkpoint_from_row(self, row: ProjectCheckpointRow) -> ProjectCheckpoint:
        if row.schema_version != 1:
            raise ValueError("persisted checkpoint schema version is invalid")
        statement = (
            select(CheckpointFileRow)
            .where(CheckpointFileRow.checkpoint_id == row.id)
            .order_by(CheckpointFileRow.relative_path)
        )
        file_rows = (await self._session.scalars(statement)).all()
        if len(file_rows) != row.file_count:
            raise ValueError("persisted checkpoint file count is inconsistent")
        files = tuple(
            CheckpointFile(
                relative_path=file.relative_path,
                content_hash=file.content_hash,
                byte_size=file.byte_size,
            )
            for file in file_rows
        )
        return ProjectCheckpoint(
            schema_version=1,
            id=row.id,
            project_id=row.project_id,
            manifest_version=row.manifest_version,
            reason=CheckpointReason(row.reason),
            content_hash=row.content_hash,
            files=files,
            total_bytes=row.total_bytes,
            created_at=row.created_at,
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


def _project_from_row(project: ProjectRow) -> Project:
    return Project(
        schema_version=1,
        id=project.id,
        name=project.name,
        goal=project.goal,
        status=ProjectStatus(project.status),
        version=project.version,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
