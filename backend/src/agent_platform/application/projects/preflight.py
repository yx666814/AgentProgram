from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent_platform.domain.projects import (
    PersistedProjectManifest,
    PreflightCheck,
    PreflightStatus,
    ProjectManifest,
    ProjectPreflightResult,
    ProjectRegistration,
    worst_preflight_status,
)
from agent_platform.domain.shared.ids import new_id
from agent_platform.infrastructure.projects.metadata import (
    ProjectMetadataError,
    ProjectMetadataStore,
    project_document_hash,
)
from agent_platform.infrastructure.projects.paths import (
    UnsafeWorkspacePathError,
    resolve_project_path,
    validate_direct_workspace_root,
)


def run_project_preflight(
    registration: ProjectRegistration,
    persisted_manifest: PersistedProjectManifest,
    metadata_store: ProjectMetadataStore,
    *,
    now: datetime | None = None,
) -> ProjectPreflightResult:
    started_at = now or datetime.now(UTC)
    checks: list[PreflightCheck] = []
    root = Path(registration.workspace.root_path)

    try:
        resolved_root, canonical_root = validate_direct_workspace_root(root)
        if canonical_root != registration.workspace.canonical_root_path:
            raise UnsafeWorkspacePathError(
                "workspace.canonical_root_changed",
                "Workspace canonical root has changed",
            )
    except UnsafeWorkspacePathError as error:
        checks.append(
            _check(
                "workspace.boundary",
                PreflightStatus.FAIL,
                "Workspace boundary validation failed",
                error_code=error.code,
            )
        )
        return _result(registration, persisted_manifest, checks, started_at)
    checks.append(_check("workspace.boundary", PreflightStatus.PASS, "Workspace root is safe"))

    try:
        metadata = metadata_store.read_metadata()
        if (
            metadata.project_id != registration.project.id
            or metadata.workspace_id != registration.workspace.id
            or metadata.workspace_mode is not registration.workspace.mode
        ):
            raise ProjectMetadataError(
                "project.metadata_mismatch",
                "Project metadata does not match the registry",
            )
    except ProjectMetadataError as error:
        checks.append(
            _check(
                "project.metadata",
                PreflightStatus.FAIL,
                "Project metadata validation failed",
                error_code=error.code,
            )
        )
        return _result(registration, persisted_manifest, checks, started_at)
    checks.append(_check("project.metadata", PreflightStatus.PASS, "Project metadata is valid"))

    try:
        manifest = metadata_store.read_manifest()
    except ProjectMetadataError as error:
        checks.append(
            _check(
                "project.manifest",
                PreflightStatus.NEEDS_FIX,
                "Project manifest is unavailable",
                error_code=error.code,
            )
        )
        return _result(registration, persisted_manifest, checks, started_at)
    if (
        manifest != persisted_manifest.manifest
        or project_document_hash(manifest) != persisted_manifest.content_hash
    ):
        checks.append(
            _check(
                "project.manifest",
                PreflightStatus.FAIL,
                "Filesystem and database manifests do not match",
            )
        )
        return _result(registration, persisted_manifest, checks, started_at)
    checks.append(_check("project.manifest", PreflightStatus.PASS, "Project manifest is valid"))

    checks.append(_paths_check(resolved_root, manifest, "source_paths"))
    checks.append(_paths_check(resolved_root, manifest, "instruction_paths"))
    checks.append(_command_directories_check(resolved_root, manifest))
    checks.extend(_command_presence_checks(manifest))
    return _result(registration, persisted_manifest, checks, started_at)


def _paths_check(root: Path, manifest: ProjectManifest, field_name: str) -> PreflightCheck:
    paths: tuple[str, ...] = getattr(manifest, field_name)
    missing: list[str] = []
    unsafe: list[str] = []
    for relative_path in paths:
        try:
            resolve_project_path(root, relative_path)
        except UnsafeWorkspacePathError as error:
            if error.code == "workspace.path_escape":
                unsafe.append(relative_path)
            else:
                missing.append(relative_path)
    code = f"manifest.{field_name}"
    if unsafe:
        return _check(
            code,
            PreflightStatus.FAIL,
            "Manifest paths cross an unsafe boundary",
            paths=unsafe,
        )
    if missing:
        return _check(
            code,
            PreflightStatus.NEEDS_FIX,
            "Manifest paths are missing",
            paths=missing,
        )
    return _check(code, PreflightStatus.PASS, "Manifest paths are available", count=len(paths))


def _command_directories_check(root: Path, manifest: ProjectManifest) -> PreflightCheck:
    missing: list[str] = []
    commands = (
        *manifest.build_commands,
        *manifest.test_commands,
        *manifest.typecheck_commands,
    )
    for command in commands:
        if command.working_directory is None:
            continue
        try:
            directory = resolve_project_path(root, command.working_directory)
            if not directory.is_dir():
                missing.append(command.working_directory)
        except UnsafeWorkspacePathError:
            missing.append(command.working_directory)
    if missing:
        return _check(
            "manifest.command_directories",
            PreflightStatus.NEEDS_FIX,
            "Command working directories are unavailable",
            paths=sorted(set(missing)),
        )
    return _check(
        "manifest.command_directories",
        PreflightStatus.PASS,
        "Command working directories are available",
    )


def _command_presence_checks(manifest: ProjectManifest) -> tuple[PreflightCheck, ...]:
    return tuple(
        _check(
            f"manifest.{name}_commands",
            PreflightStatus.PASS if commands else PreflightStatus.WARNING,
            f"{name.title()} commands are configured"
            if commands
            else f"No {name} command is configured",
            count=len(commands),
        )
        for name, commands in (
            ("build", manifest.build_commands),
            ("test", manifest.test_commands),
            ("typecheck", manifest.typecheck_commands),
        )
    )


def _check(
    code: str,
    status: PreflightStatus,
    message: str,
    **evidence: object,
) -> PreflightCheck:
    return PreflightCheck(code=code, status=status, message=message, evidence=evidence)


def _result(
    registration: ProjectRegistration,
    persisted_manifest: PersistedProjectManifest,
    checks: list[PreflightCheck],
    started_at: datetime,
) -> ProjectPreflightResult:
    frozen_checks = tuple(checks)
    return ProjectPreflightResult(
        schema_version=1,
        id=new_id("preflight"),
        project_id=registration.project.id,
        manifest_version=persisted_manifest.manifest.manifest_version,
        status=worst_preflight_status(frozen_checks),
        checks=frozen_checks,
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )
