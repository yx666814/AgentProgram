from typing import Protocol

from agent_platform.domain.projects import ProjectRegistration


class ProjectRepository(Protocol):
    async def add(self, registration: ProjectRegistration) -> None: ...

    async def get(self, project_id: str) -> ProjectRegistration | None: ...

    async def list(self) -> tuple[ProjectRegistration, ...]: ...

    async def find_by_canonical_root(
        self,
        canonical_root_path: str,
    ) -> ProjectRegistration | None: ...
