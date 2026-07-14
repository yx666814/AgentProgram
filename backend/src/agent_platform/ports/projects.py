from typing import Protocol

from agent_platform.domain.projects import (
    PersistedProjectManifest,
    Project,
    ProjectCheckpoint,
    ProjectPreflightResult,
    ProjectRegistration,
)


class ProjectRepository(Protocol):
    async def add(self, registration: ProjectRegistration) -> None: ...

    async def get(self, project_id: str) -> ProjectRegistration | None: ...

    async def list(self) -> tuple[ProjectRegistration, ...]: ...

    async def find_by_canonical_root(
        self,
        canonical_root_path: str,
    ) -> ProjectRegistration | None: ...

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
