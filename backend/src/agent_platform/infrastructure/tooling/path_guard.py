from __future__ import annotations

from agent_platform.domain.contracts import (
    CapabilityAccess,
    Stage,
    StagePathScope,
    get_stage_contract,
    require_project_relative_path,
)
from agent_platform.domain.projects import ProjectManifest
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.tooling import ToolDefinition, ToolOperation

_BUILD_FILES = frozenset(
    {
        "pyproject.toml",
        "uv.lock",
        "requirements.txt",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "tsconfig.json",
        "vite.config.ts",
        "vite.config.js",
        "Cargo.toml",
        "Cargo.lock",
        "go.mod",
        "go.sum",
        "Dockerfile",
    }
)
_SOURCE_EXTENSIONS = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".css",
        ".go",
        ".h",
        ".html",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".scss",
        ".swift",
        ".ts",
        ".tsx",
        ".vue",
    }
)


class PathGuard:
    def authorize_capability(
        self,
        stage: Stage,
        tool: ToolDefinition,
        *,
        approved_capabilities: tuple[str, ...] = (),
    ) -> None:
        contract = get_stage_contract(stage)
        access = contract.capability_access(tool.capability)
        if access is CapabilityAccess.FORBIDDEN:
            raise _permission("tool.capability_forbidden", "Tool capability is forbidden")
        if (
            access is CapabilityAccess.REQUIRES_APPROVAL
            and tool.capability not in approved_capabilities
        ):
            raise _permission("tool.approval_required", "Tool capability requires approval")

    def authorize_path(
        self,
        stage: Stage,
        tool: ToolDefinition,
        relative_path: str,
        manifest: ProjectManifest,
    ) -> StagePathScope:
        path = require_project_relative_path(relative_path)
        if _matches_any(path, manifest.excluded_paths):
            raise _permission("tool.path_excluded", "Project path is excluded")
        if path == ".agent" or path.startswith(".agent/"):
            raise _permission("tool.metadata_protected", "Project metadata is protected")
        scope = _classify(path, stage, manifest)
        contract = get_stage_contract(stage)
        allowed = {
            ToolOperation.READ: contract.path_policy.read_scopes,
            ToolOperation.WRITE: contract.path_policy.write_scopes,
            ToolOperation.CREATE_DIRECTORY: contract.path_policy.write_scopes,
            ToolOperation.DELETE: contract.path_policy.delete_scopes,
        }.get(tool.operation)
        if allowed is None or scope not in allowed:
            raise _permission("tool.path_out_of_scope", "Project path is outside stage scope")
        if tool.allowed_scopes and scope not in tool.allowed_scopes:
            raise _permission("tool.path_wrong_kind", "Project path does not match tool scope")
        return scope


def _classify(path: str, stage: Stage, manifest: ProjectManifest) -> StagePathScope:
    artifact_prefixes = {
        "artifacts/planner": StagePathScope.PLANNER_ARTIFACT,
        "artifacts/designer": StagePathScope.DESIGNER_ARTIFACT,
        "artifacts/builder": StagePathScope.BUILDER_ARTIFACT,
        "artifacts/reviewer": StagePathScope.REVIEWER_ARTIFACT,
        "artifacts/deployer": StagePathScope.DEPLOYER_ARTIFACT,
    }
    for prefix, scope in artifact_prefixes.items():
        if _matches(path, prefix):
            return scope
    if _matches(path, f"drafts/{stage.value}"):
        return StagePathScope.STAGE_DRAFT
    if _matches_any(path, manifest.source_paths) or _is_conventional_source_path(path):
        if _is_test_path(path):
            return StagePathScope.PROJECT_TEST
        return StagePathScope.PROJECT_SOURCE
    if _is_test_path(path):
        return StagePathScope.PROJECT_TEST
    if path.rsplit("/", maxsplit=1)[-1] in _BUILD_FILES:
        return StagePathScope.PROJECT_BUILD_CONFIG
    if _matches_any(path, ("build", "dist", "coverage", ".coverage", ".cache")):
        return StagePathScope.GENERATED
    if _matches_any(path, ("deploy/config", "deployment/config", "config/deploy")):
        return StagePathScope.DEPLOYMENT_CONFIG
    if _matches_any(path, ("deploy/scripts", "deployment/scripts", "scripts/deploy")):
        return StagePathScope.DEPLOYMENT_SCRIPT
    return StagePathScope.PROJECT_NON_SENSITIVE


def _is_test_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (
        any(part in {"test", "tests", "spec", "specs", "__tests__"} for part in parts[:-1])
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def _is_conventional_source_path(path: str) -> bool:
    name = path.rsplit("/", maxsplit=1)[-1]
    suffix = f".{name.rsplit('.', maxsplit=1)[-1]}" if "." in name else ""
    return suffix.casefold() in _SOURCE_EXTENSIONS


def _matches(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f"{prefix}/")


def _matches_any(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(_matches(path, prefix) for prefix in prefixes)


def _permission(code: str, message: str) -> DomainError:
    return DomainError(code=code, message=message, category=ErrorCategory.PERMISSION)
