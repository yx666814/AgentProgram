from __future__ import annotations

from agent_platform.domain.contracts import StagePathScope
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.tooling import ToolDefinition, ToolOperation


def _tool(
    name: str,
    operation: ToolOperation,
    *,
    scopes: tuple[StagePathScope, ...] = (),
    mutating: bool = False,
    max_timeout_seconds: int = 900,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        capability=name,
        operation=operation,
        allowed_scopes=scopes,
        mutating=mutating,
        max_timeout_seconds=max_timeout_seconds,
    )


_TOOLS = (
    _tool("filesystem.read_project", ToolOperation.READ),
    _tool(
        "filesystem.read_planner_artifact",
        ToolOperation.READ,
        scopes=(StagePathScope.PLANNER_ARTIFACT,),
    ),
    _tool(
        "filesystem.read_all_approved_artifacts",
        ToolOperation.READ,
        scopes=(
            StagePathScope.PLANNER_ARTIFACT,
            StagePathScope.DESIGNER_ARTIFACT,
            StagePathScope.BUILDER_ARTIFACT,
            StagePathScope.REVIEWER_ARTIFACT,
            StagePathScope.DEPLOYER_ARTIFACT,
        ),
    ),
    _tool(
        "filesystem.write_planner_artifact",
        ToolOperation.WRITE,
        scopes=(StagePathScope.PLANNER_ARTIFACT,),
        mutating=True,
    ),
    _tool(
        "filesystem.write_designer_artifact",
        ToolOperation.WRITE,
        scopes=(StagePathScope.DESIGNER_ARTIFACT,),
        mutating=True,
    ),
    _tool(
        "filesystem.write_builder_artifact",
        ToolOperation.WRITE,
        scopes=(StagePathScope.BUILDER_ARTIFACT,),
        mutating=True,
    ),
    _tool(
        "filesystem.write_reviewer_artifact",
        ToolOperation.WRITE,
        scopes=(StagePathScope.REVIEWER_ARTIFACT,),
        mutating=True,
    ),
    _tool(
        "filesystem.write_deployment_document",
        ToolOperation.WRITE,
        scopes=(StagePathScope.DEPLOYER_ARTIFACT,),
        mutating=True,
    ),
    _tool(
        "filesystem.write_deployment_config",
        ToolOperation.WRITE,
        scopes=(StagePathScope.DEPLOYMENT_CONFIG,),
        mutating=True,
    ),
    _tool(
        "filesystem.write_deployment_script",
        ToolOperation.WRITE,
        scopes=(StagePathScope.DEPLOYMENT_SCRIPT,),
        mutating=True,
    ),
    _tool(
        "filesystem.write_source",
        ToolOperation.WRITE,
        scopes=(StagePathScope.PROJECT_SOURCE,),
        mutating=True,
    ),
    _tool(
        "filesystem.write_test",
        ToolOperation.WRITE,
        scopes=(StagePathScope.PROJECT_TEST,),
        mutating=True,
    ),
    _tool(
        "filesystem.write_build_config",
        ToolOperation.WRITE,
        scopes=(StagePathScope.PROJECT_BUILD_CONFIG,),
        mutating=True,
    ),
    _tool("filesystem.create_directory", ToolOperation.CREATE_DIRECTORY, mutating=True),
    _tool(
        "filesystem.delete_generated_or_builder_owned",
        ToolOperation.DELETE,
        scopes=(
            StagePathScope.GENERATED,
            StagePathScope.BUILDER_ARTIFACT,
            StagePathScope.STAGE_DRAFT,
        ),
        mutating=True,
    ),
    _tool("shell.run", ToolOperation.COMMAND, max_timeout_seconds=900),
    _tool("shell.run_project_command", ToolOperation.COMMAND, max_timeout_seconds=1800),
    _tool("shell.build", ToolOperation.COMMAND, max_timeout_seconds=3600),
    _tool("shell.test", ToolOperation.COMMAND, max_timeout_seconds=3600),
    _tool("shell.lint", ToolOperation.COMMAND, max_timeout_seconds=1800),
    _tool("shell.format", ToolOperation.COMMAND, max_timeout_seconds=1800, mutating=True),
    _tool("shell.typecheck", ToolOperation.COMMAND, max_timeout_seconds=1800),
    _tool("shell.security_scan", ToolOperation.COMMAND, max_timeout_seconds=3600),
)


class ToolCatalog:
    def __init__(self) -> None:
        self._tools = {tool.name: tool for tool in _TOOLS}

    def list(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._tools[name] for name in sorted(self._tools))

    def get(self, name: str) -> ToolDefinition:
        tool = self._tools.get(name)
        if tool is None:
            raise DomainError(
                code="tool.not_registered",
                message="Tool is not registered",
                category=ErrorCategory.PERMISSION,
            )
        return tool
