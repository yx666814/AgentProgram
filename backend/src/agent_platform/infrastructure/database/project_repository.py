from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.domain.projects import (
    CheckpointFile,
    CheckpointReason,
    ConflictResolution,
    ExternalChange,
    ExternalChangeStatus,
    ExternalChangeType,
    FileConflict,
    FileConflictStatus,
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
    ExternalChangeRow,
    FileConflictRow,
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


class FileConflictVersionError(DomainError):
    def __init__(self, current_version: int) -> None:
        super().__init__(
            code="file_conflict.version_conflict",
            message="File conflict version has changed",
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

    async def set_project_status(
        self,
        project_id: str,
        status: ProjectStatus,
        *,
        expected_version: int,
        updated_at: datetime,
    ) -> Project:
        row = await self._session.get(ProjectRow, project_id)
        if row is None:
            raise DomainError(
                code="project.not_found",
                message="Project was not found",
                category=ErrorCategory.NOT_FOUND,
            )
        if row.version != expected_version:
            raise ProjectVersionConflictError(row.version)
        row.status = status.value
        row.version += 1
        row.updated_at = updated_at
        await self._session.flush()
        return _project_from_row(row)

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

    async def record_external_changes(
        self,
        changes: tuple[ExternalChange, ...],
    ) -> None:
        self._session.add_all(
            ExternalChangeRow(
                id=change.id,
                project_id=change.project_id,
                schema_version=change.schema_version,
                relative_path=change.relative_path,
                change_type=change.change_type.value,
                baseline_content_hash=change.baseline_content_hash,
                current_content_hash=change.current_content_hash,
                status=change.status.value,
                detected_at=change.detected_at,
            )
            for change in changes
        )
        await self._session.flush()

    async def list_open_external_changes(
        self,
        project_id: str,
    ) -> tuple[ExternalChange, ...]:
        statement = (
            select(ExternalChangeRow)
            .where(
                ExternalChangeRow.project_id == project_id,
                ExternalChangeRow.status == ExternalChangeStatus.OPEN.value,
            )
            .order_by(ExternalChangeRow.detected_at, ExternalChangeRow.relative_path)
        )
        rows = (await self._session.scalars(statement)).all()
        return tuple(_external_change_from_row(row) for row in rows)

    async def acknowledge_external_change(self, change_id: str) -> ExternalChange:
        row = await self._session.get(ExternalChangeRow, change_id)
        if row is None:
            raise DomainError(
                code="external_change.not_found",
                message="External change was not found",
                category=ErrorCategory.NOT_FOUND,
            )
        row.status = ExternalChangeStatus.ACKNOWLEDGED.value
        await self._session.flush()
        return _external_change_from_row(row)

    async def record_file_conflicts(self, conflicts: tuple[FileConflict, ...]) -> None:
        self._session.add_all(
            FileConflictRow(
                id=conflict.id,
                project_id=conflict.project_id,
                schema_version=conflict.schema_version,
                relative_path=conflict.relative_path,
                baseline_content_hash=conflict.baseline_content_hash,
                user_content_hash=conflict.user_content_hash,
                agent_content_hash=conflict.agent_content_hash,
                status=conflict.status.value,
                resolution=conflict.resolution.value if conflict.resolution else None,
                version=conflict.version,
                created_at=conflict.created_at,
                resolved_at=conflict.resolved_at,
            )
            for conflict in conflicts
        )
        await self._session.flush()

    async def list_open_file_conflicts(
        self,
        project_id: str,
    ) -> tuple[FileConflict, ...]:
        statement = (
            select(FileConflictRow)
            .where(
                FileConflictRow.project_id == project_id,
                FileConflictRow.status == FileConflictStatus.OPEN.value,
            )
            .order_by(FileConflictRow.created_at, FileConflictRow.relative_path)
        )
        rows = (await self._session.scalars(statement)).all()
        return tuple(_file_conflict_from_row(row) for row in rows)

    async def get_file_conflict(self, conflict_id: str) -> FileConflict | None:
        row = await self._session.get(FileConflictRow, conflict_id)
        return _file_conflict_from_row(row) if row is not None else None

    async def resolve_file_conflict(
        self,
        conflict_id: str,
        resolution: ConflictResolution,
        *,
        expected_version: int,
        resolved_at: datetime,
    ) -> FileConflict:
        row = await self._session.get(FileConflictRow, conflict_id)
        if row is None:
            raise DomainError(
                code="file_conflict.not_found",
                message="File conflict was not found",
                category=ErrorCategory.NOT_FOUND,
            )
        if row.version != expected_version:
            raise FileConflictVersionError(row.version)
        if row.status != FileConflictStatus.OPEN.value:
            raise DomainError(
                code="file_conflict.already_resolved",
                message="File conflict is already resolved",
                category=ErrorCategory.CONFLICT,
            )
        row.status = FileConflictStatus.RESOLVED.value
        row.resolution = resolution.value
        row.version += 1
        row.resolved_at = resolved_at
        await self._session.flush()
        return _file_conflict_from_row(row)

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


def _external_change_from_row(row: ExternalChangeRow) -> ExternalChange:
    if row.schema_version != 1:
        raise ValueError("persisted external change schema version is invalid")
    return ExternalChange(
        schema_version=1,
        id=row.id,
        project_id=row.project_id,
        relative_path=row.relative_path,
        change_type=ExternalChangeType(row.change_type),
        baseline_content_hash=row.baseline_content_hash,
        current_content_hash=row.current_content_hash,
        status=ExternalChangeStatus(row.status),
        detected_at=row.detected_at,
    )


def _file_conflict_from_row(row: FileConflictRow) -> FileConflict:
    if row.schema_version != 1:
        raise ValueError("persisted file conflict schema version is invalid")
    return FileConflict(
        schema_version=1,
        id=row.id,
        project_id=row.project_id,
        relative_path=row.relative_path,
        baseline_content_hash=row.baseline_content_hash,
        user_content_hash=row.user_content_hash,
        agent_content_hash=row.agent_content_hash,
        status=FileConflictStatus(row.status),
        resolution=ConflictResolution(row.resolution) if row.resolution else None,
        version=row.version,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )
