from datetime import datetime
from typing import Protocol

from agent_platform.domain.projects import (
    ConflictResolution,
    ExternalChange,
    FileConflict,
    PersistedProjectManifest,
    Project,
    ProjectCheckpoint,
    ProjectPreflightResult,
    ProjectRegistration,
    ProjectStatus,
)


class ProjectRepository(Protocol):
    async def add(self, registration: ProjectRegistration) -> None: ...

    async def get(self, project_id: str) -> ProjectRegistration | None: ...

    async def list(self) -> tuple[ProjectRegistration, ...]: ...

    async def find_by_canonical_root(
        self,
        canonical_root_path: str,
    ) -> ProjectRegistration | None: ...

    async def set_project_status(
        self,
        project_id: str,
        status: ProjectStatus,
        *,
        expected_version: int,
        updated_at: datetime,
    ) -> Project: ...

    async def save_manifest(
        self,
        persisted: PersistedProjectManifest,
        *,
        expected_version: int | None,
    ) -> None: ...

    async def get_manifest(self, project_id: str) -> PersistedProjectManifest | None: ...

    async def record_preflight(
        self,
        result: ProjectPreflightResult,
        *,
        expected_project_version: int,
    ) -> Project: ...

    async def get_latest_preflight(self, project_id: str) -> ProjectPreflightResult | None: ...

    async def record_checkpoint(self, checkpoint: ProjectCheckpoint) -> None: ...

    async def get_checkpoint(self, checkpoint_id: str) -> ProjectCheckpoint | None: ...

    async def list_checkpoints(
        self,
        project_id: str,
        *,
        limit: int = 100,
    ) -> tuple[ProjectCheckpoint, ...]: ...

    async def list_referenced_checkpoint_hashes(self) -> frozenset[str]: ...

    async def record_external_changes(
        self,
        changes: tuple[ExternalChange, ...],
    ) -> None: ...

    async def list_open_external_changes(
        self,
        project_id: str,
    ) -> tuple[ExternalChange, ...]: ...

    async def acknowledge_external_change(self, change_id: str) -> ExternalChange: ...

    async def record_file_conflicts(self, conflicts: tuple[FileConflict, ...]) -> None: ...

    async def list_open_file_conflicts(
        self,
        project_id: str,
    ) -> tuple[FileConflict, ...]: ...

    async def get_file_conflict(self, conflict_id: str) -> FileConflict | None: ...

    async def resolve_file_conflict(
        self,
        conflict_id: str,
        resolution: ConflictResolution,
        *,
        expected_version: int,
        resolved_at: datetime,
    ) -> FileConflict: ...
