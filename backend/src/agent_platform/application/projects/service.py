from __future__ import annotations

import asyncio
import json
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from agent_platform.application.projects.changes import (
    build_restore_plan,
    detect_external_changes,
    detect_file_conflicts,
)
from agent_platform.application.projects.preflight import run_project_preflight
from agent_platform.config.settings import Settings
from agent_platform.domain.events import ActorRef, ActorType, EventEnvelope, EventSource
from agent_platform.domain.projects import (
    CheckpointReason,
    CheckpointRestorePlan,
    CheckpointRestoreResult,
    ConflictResolution,
    ExternalChange,
    FileConflict,
    PersistedProjectManifest,
    Project,
    ProjectCheckpoint,
    ProjectCommand,
    ProjectManifest,
    ProjectMetadata,
    ProjectPreflightResult,
    ProjectRegistration,
    ProjectStatus,
    Workspace,
    WorkspaceMode,
)
from agent_platform.domain.shared.errors import DomainError, ErrorCategory
from agent_platform.domain.shared.ids import new_id
from agent_platform.infrastructure.async_cleanup import await_cancellation_resistant
from agent_platform.infrastructure.database.session import Database
from agent_platform.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agent_platform.infrastructure.projects.checkpoints import CheckpointStore
from agent_platform.infrastructure.projects.metadata import (
    ProjectMetadataStore,
)
from agent_platform.infrastructure.projects.paths import (
    create_managed_workspace_root,
    validate_direct_workspace_root,
)


@dataclass(frozen=True, slots=True)
class ProjectCreation:
    registration: ProjectRegistration
    manifest: ProjectManifest


@dataclass(frozen=True, slots=True)
class PreflightExecution:
    project: Project
    result: ProjectPreflightResult


@dataclass(frozen=True, slots=True)
class RestorePlanning:
    plan: CheckpointRestorePlan
    protection_checkpoint: ProjectCheckpoint


@dataclass(frozen=True, slots=True)
class RestoreExecution:
    result: CheckpointRestoreResult
    project: Project


@dataclass(frozen=True, slots=True)
class ExternalChangeScan:
    current_checkpoint: ProjectCheckpoint
    changes: tuple[ExternalChange, ...]
    conflicts: tuple[FileConflict, ...]


@dataclass(frozen=True, slots=True)
class ConflictResolutionExecution:
    conflict: FileConflict
    project: Project
    protection_checkpoint_id: str | None


class ProjectApplicationService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self._database = database
        self._settings = settings

    async def list_projects(self) -> tuple[ProjectRegistration, ...]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            return await uow.projects.list()

    async def create_project(
        self,
        *,
        name: str,
        goal: str,
        local_working_directory: str,
        workspace_mode: WorkspaceMode,
        correlation_id: str,
    ) -> ProjectCreation:
        source_root, _ = await _run_sync(
            validate_direct_workspace_root,
            Path(local_working_directory),
        )
        project_id = new_id("project")
        workspace_id = new_id("workspace")
        now = datetime.now(UTC)
        managed = workspace_mode is WorkspaceMode.MANAGED
        workspace_root = source_root
        imported_checkpoint: ProjectCheckpoint | None = None
        if managed:
            workspace_root, canonical_root = await _run_sync(
                create_managed_workspace_root,
                self._settings.data_root,
                project_id,
            )
        else:
            _, canonical_root = await _run_sync(
                validate_direct_workspace_root,
                workspace_root,
            )

        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            duplicate = await uow.projects.find_by_canonical_root(canonical_root)
        if duplicate is not None:
            if managed:
                await _run_sync(
                    _remove_managed_workspace,
                    self._settings.data_root,
                    workspace_root,
                )
            raise DomainError(
                code="project.workspace_already_registered",
                message="Workspace is already registered",
                category=ErrorCategory.CONFLICT,
            )

        manifest = _default_manifest(project_id, source_root)
        store = self._checkpoint_store()
        metadata_created = False
        try:
            if managed:
                imported_checkpoint = await _run_sync(
                    store.create,
                    source_root,
                    manifest,
                    reason=CheckpointReason.PRE_MUTATION,
                )
                await _run_sync(
                    store.materialize_empty_workspace,
                    workspace_root,
                    imported_checkpoint,
                )
            if (workspace_root / ".agent").exists() or (workspace_root / ".agent").is_symlink():
                raise DomainError(
                    code="project.workspace_already_initialized",
                    message="Workspace already contains AgentProgram metadata",
                    category=ErrorCategory.CONFLICT,
                )
            metadata_store = ProjectMetadataStore(workspace_root)
            metadata = ProjectMetadata(
                schema_version=1,
                project_id=project_id,
                workspace_id=workspace_id,
                workspace_mode=workspace_mode,
                created_at=now,
            )
            await _run_sync(metadata_store.initialize, metadata)
            metadata_created = True
            content_hash = await _run_sync(
                metadata_store.write_manifest,
                manifest,
                expected_version=None,
            )
            registration = ProjectRegistration(
                schema_version=1,
                project=Project(
                    schema_version=1,
                    id=project_id,
                    name=name.strip(),
                    goal=goal.strip(),
                    status=ProjectStatus.PREFLIGHT_REQUIRED,
                    created_at=now,
                    updated_at=now,
                    version=1,
                ),
                workspace=Workspace(
                    schema_version=1,
                    id=workspace_id,
                    project_id=project_id,
                    mode=workspace_mode,
                    root_path=str(workspace_root),
                    canonical_root_path=canonical_root,
                    created_at=now,
                ),
            )
            persisted_manifest = PersistedProjectManifest(
                schema_version=1,
                manifest=manifest,
                content_hash=content_hash,
                updated_at=now,
            )
            async with self._write_uow() as uow:
                await uow.projects.add(registration)
                await uow.projects.save_manifest(persisted_manifest, expected_version=None)
                if imported_checkpoint is not None:
                    await uow.projects.record_checkpoint(imported_checkpoint)
                await _append_event(
                    uow,
                    event_type="project.created",
                    correlation_id=correlation_id,
                    project_id=project_id,
                    occurred_at=now,
                    payload={"workspace_mode": workspace_mode.value},
                )
                await uow.commit()
        except BaseException:
            if managed:
                await _run_sync(
                    _remove_managed_workspace,
                    self._settings.data_root,
                    workspace_root,
                )
            elif metadata_created:
                await _run_sync(_remove_created_metadata, workspace_root, project_id)
            raise
        return ProjectCreation(registration=registration, manifest=manifest)

    async def get_project(self, project_id: str) -> ProjectRegistration:
        registration, _ = await self._project_context(project_id)
        return registration

    async def open_project(
        self,
        project_id: str,
        *,
        expected_version: int,
        correlation_id: str,
    ) -> ProjectRegistration:
        registration, _ = await self._project_context(project_id)
        await _run_sync(
            validate_direct_workspace_root,
            Path(registration.workspace.root_path),
        )
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            if registration.project.status is ProjectStatus.CLOSED:
                project = await uow.projects.set_project_status(
                    project_id,
                    ProjectStatus.PREFLIGHT_REQUIRED,
                    expected_version=expected_version,
                    updated_at=now,
                )
            else:
                if registration.project.version != expected_version:
                    raise _project_version_error(registration.project.version)
                project = registration.project
            await _append_event(
                uow,
                event_type="project.opened",
                correlation_id=correlation_id,
                project_id=project_id,
                occurred_at=now,
                payload={"status": project.status.value},
            )
            await uow.commit()
        return registration.model_copy(update={"project": project})

    async def close_project(
        self,
        project_id: str,
        *,
        expected_version: int,
        correlation_id: str,
    ) -> Project:
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            project = await uow.projects.set_project_status(
                project_id,
                ProjectStatus.CLOSED,
                expected_version=expected_version,
                updated_at=now,
            )
            await _append_event(
                uow,
                event_type="project.closed",
                correlation_id=correlation_id,
                project_id=project_id,
                occurred_at=now,
                payload={},
            )
            await uow.commit()
        return project

    async def run_preflight(
        self,
        project_id: str,
        *,
        expected_version: int,
        correlation_id: str,
    ) -> PreflightExecution:
        registration, persisted_manifest = await self._project_context(project_id)
        _require_open(registration.project)
        if registration.project.version != expected_version:
            raise _project_version_error(registration.project.version)
        result = await _run_sync(
            run_project_preflight,
            registration,
            persisted_manifest,
            ProjectMetadataStore(Path(registration.workspace.root_path)),
        )
        async with self._write_uow() as uow:
            project = await uow.projects.record_preflight(
                result,
                expected_project_version=expected_version,
            )
            await _append_event(
                uow,
                event_type="project.preflight_completed",
                correlation_id=correlation_id,
                project_id=project_id,
                occurred_at=result.completed_at,
                payload={"status": result.status.value},
            )
            await uow.commit()
        return PreflightExecution(project=project, result=result)

    async def get_preflight(self, project_id: str) -> ProjectPreflightResult:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            result = await uow.projects.get_latest_preflight(project_id)
        if result is None:
            raise DomainError(
                code="project.preflight_not_found",
                message="Project preflight has not been run",
                category=ErrorCategory.NOT_FOUND,
            )
        return result

    async def create_checkpoint(
        self,
        project_id: str,
        *,
        reason: CheckpointReason,
        correlation_id: str,
    ) -> ProjectCheckpoint:
        registration, persisted_manifest = await self._project_context(project_id)
        _require_open(registration.project)
        checkpoint = await _run_sync(
            self._checkpoint_store().create,
            Path(registration.workspace.root_path),
            persisted_manifest.manifest,
            reason=reason,
        )
        async with self._write_uow() as uow:
            await uow.projects.record_checkpoint(checkpoint)
            await _append_event(
                uow,
                event_type="project.checkpoint_created",
                correlation_id=correlation_id,
                project_id=project_id,
                occurred_at=checkpoint.created_at,
                payload={"checkpoint_id": checkpoint.id, "reason": checkpoint.reason.value},
            )
            await uow.commit()
        return checkpoint

    async def list_checkpoints(self, project_id: str) -> tuple[ProjectCheckpoint, ...]:
        await self.get_project(project_id)
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            return await uow.projects.list_checkpoints(project_id)

    async def plan_restore(
        self,
        project_id: str,
        checkpoint_id: str,
        *,
        correlation_id: str,
    ) -> RestorePlanning:
        registration, manifest = await self._project_context(project_id)
        _require_open(registration.project)
        target = await self._checkpoint(checkpoint_id, project_id)
        protection = await _run_sync(
            self._checkpoint_store().create,
            Path(registration.workspace.root_path),
            manifest.manifest,
            reason=CheckpointReason.PRE_RESTORE,
        )
        plan = build_restore_plan(protection, target)
        async with self._write_uow() as uow:
            await uow.projects.record_checkpoint(protection)
            await _append_event(
                uow,
                event_type="project.restore_planned",
                correlation_id=correlation_id,
                project_id=project_id,
                occurred_at=protection.created_at,
                payload={
                    "target_checkpoint_id": target.id,
                    "protection_checkpoint_id": protection.id,
                },
            )
            await uow.commit()
        return RestorePlanning(plan=plan, protection_checkpoint=protection)

    async def restore_checkpoint(
        self,
        project_id: str,
        checkpoint_id: str,
        *,
        protection_checkpoint_id: str,
        expected_project_version: int,
        correlation_id: str,
    ) -> RestoreExecution:
        registration, _ = await self._project_context(project_id)
        _require_open(registration.project)
        target = await self._checkpoint(checkpoint_id, project_id)
        protection = await self._checkpoint(protection_checkpoint_id, project_id)
        result = await _run_sync(
            self._checkpoint_store().restore_prepared,
            Path(registration.workspace.root_path),
            target,
            protection,
        )
        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            project = await uow.projects.set_project_status(
                project_id,
                ProjectStatus.PREFLIGHT_REQUIRED,
                expected_version=expected_project_version,
                updated_at=now,
            )
            await _append_event(
                uow,
                event_type="project.checkpoint_restored",
                correlation_id=correlation_id,
                project_id=project_id,
                occurred_at=now,
                payload={
                    "checkpoint_id": target.id,
                    "protection_checkpoint_id": protection.id,
                },
            )
            await uow.commit()
        return RestoreExecution(result=result, project=project)

    async def scan_external_changes(
        self,
        project_id: str,
        *,
        baseline_checkpoint_id: str,
        agent_checkpoint_id: str | None,
        correlation_id: str,
    ) -> ExternalChangeScan:
        registration, manifest = await self._project_context(project_id)
        _require_open(registration.project)
        baseline = await self._checkpoint(baseline_checkpoint_id, project_id)
        agent = (
            await self._checkpoint(agent_checkpoint_id, project_id) if agent_checkpoint_id else None
        )
        current = await _run_sync(
            self._checkpoint_store().create,
            Path(registration.workspace.root_path),
            manifest.manifest,
            reason=CheckpointReason.PRE_MUTATION,
        )
        changes = detect_external_changes(baseline, current)
        conflicts = detect_file_conflicts(baseline, current, agent) if agent else ()
        async with self._write_uow() as uow:
            await uow.projects.record_checkpoint(current)
            await uow.projects.record_external_changes(changes)
            await uow.projects.record_file_conflicts(conflicts)
            await _append_event(
                uow,
                event_type="external_change.scanned",
                correlation_id=correlation_id,
                project_id=project_id,
                occurred_at=current.created_at,
                payload={"change_count": len(changes), "conflict_count": len(conflicts)},
            )
            await uow.commit()
        return ExternalChangeScan(
            current_checkpoint=current,
            changes=changes,
            conflicts=conflicts,
        )

    async def list_external_changes(self, project_id: str) -> tuple[ExternalChange, ...]:
        await self.get_project(project_id)
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            return await uow.projects.list_open_external_changes(project_id)

    async def list_conflicts(self, project_id: str) -> tuple[FileConflict, ...]:
        await self.get_project(project_id)
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            return await uow.projects.list_open_file_conflicts(project_id)

    async def resolve_conflict(
        self,
        project_id: str,
        conflict_id: str,
        *,
        resolution: ConflictResolution,
        expected_conflict_version: int,
        expected_project_version: int,
        agent_checkpoint_id: str | None,
        merged_content_hash: str | None,
        correlation_id: str,
    ) -> ConflictResolutionExecution:
        registration, manifest = await self._project_context(project_id)
        _require_open(registration.project)
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            conflict = await uow.projects.get_file_conflict(conflict_id)
        if conflict is None or conflict.project_id != project_id:
            raise DomainError(
                code="file_conflict.not_found",
                message="File conflict was not found",
                category=ErrorCategory.NOT_FOUND,
            )
        if conflict.version != expected_conflict_version:
            raise DomainError(
                code="file_conflict.version_conflict",
                message="File conflict version has changed",
                details={"current_version": conflict.version},
            )
        store = self._checkpoint_store()
        workspace_root = Path(registration.workspace.root_path)
        protection: ProjectCheckpoint | None = None
        if resolution is ConflictResolution.KEEP_USER:
            current_hash = await _run_sync(
                store.file_hash,
                workspace_root,
                conflict.relative_path,
            )
            if current_hash != conflict.user_content_hash:
                raise DomainError(
                    code="file_conflict.user_version_changed",
                    message="User version changed after conflict detection",
                    category=ErrorCategory.CONFLICT,
                )
        elif resolution is ConflictResolution.MANUAL_MERGE:
            if merged_content_hash is None:
                raise DomainError(
                    code="file_conflict.merged_hash_required",
                    message="Manual merge requires the merged file hash",
                    category=ErrorCategory.INVALID_INPUT,
                )
            current_hash = await _run_sync(
                store.file_hash,
                workspace_root,
                conflict.relative_path,
            )
            if current_hash != merged_content_hash:
                raise DomainError(
                    code="file_conflict.merged_version_changed",
                    message="Merged file does not match the submitted hash",
                    category=ErrorCategory.CONFLICT,
                )
        else:
            if agent_checkpoint_id is None:
                raise DomainError(
                    code="file_conflict.agent_checkpoint_required",
                    message="Agent resolution requires its checkpoint",
                    category=ErrorCategory.INVALID_INPUT,
                )
            agent_checkpoint = await self._checkpoint(agent_checkpoint_id, project_id)
            agent_file = next(
                (
                    file
                    for file in agent_checkpoint.files
                    if file.relative_path == conflict.relative_path
                ),
                None,
            )
            if (agent_file.content_hash if agent_file else None) != conflict.agent_content_hash:
                raise DomainError(
                    code="file_conflict.agent_version_mismatch",
                    message="Agent checkpoint does not match the conflict",
                    category=ErrorCategory.CONFLICT,
                )
            protection = await _run_sync(
                store.create,
                workspace_root,
                manifest.manifest,
                reason=CheckpointReason.PRE_MUTATION,
            )
            if agent_file is None:
                await _run_sync(store.delete_file, workspace_root, conflict.relative_path)
            else:
                await _run_sync(store.restore_file, workspace_root, agent_file)

        now = datetime.now(UTC)
        async with self._write_uow() as uow:
            if protection is not None:
                await uow.projects.record_checkpoint(protection)
            resolved = await uow.projects.resolve_file_conflict(
                conflict_id,
                resolution,
                expected_version=expected_conflict_version,
                resolved_at=now,
            )
            project = await uow.projects.set_project_status(
                project_id,
                ProjectStatus.PREFLIGHT_REQUIRED,
                expected_version=expected_project_version,
                updated_at=now,
            )
            await _append_event(
                uow,
                event_type="file_conflict.resolved",
                correlation_id=correlation_id,
                project_id=project_id,
                occurred_at=now,
                payload={
                    "conflict_id": conflict_id,
                    "resolution": resolution.value,
                    "protection_checkpoint_id": protection.id if protection else None,
                },
            )
            await uow.commit()
        return ConflictResolutionExecution(
            conflict=resolved,
            project=project,
            protection_checkpoint_id=protection.id if protection else None,
        )

    def _checkpoint_store(self) -> CheckpointStore:
        return CheckpointStore(
            self._settings.snapshot_root,
            max_files=self._settings.checkpoint_max_files,
            max_file_bytes=self._settings.checkpoint_max_file_bytes,
            max_total_bytes=self._settings.checkpoint_max_total_bytes,
        )

    def _write_uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(
            self._database.sessions,
            write=True,
            write_lock=self._database.write_lock,
        )

    async def _project_context(
        self,
        project_id: str,
    ) -> tuple[ProjectRegistration, PersistedProjectManifest]:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            registration = await uow.projects.get(project_id)
            manifest = await uow.projects.get_manifest(project_id)
        if registration is None:
            raise DomainError(
                code="project.not_found",
                message="Project was not found",
                category=ErrorCategory.NOT_FOUND,
            )
        if manifest is None:
            raise DomainError(
                code="project.manifest_not_found",
                message="Project manifest was not found",
                category=ErrorCategory.NOT_FOUND,
            )
        return registration, manifest

    async def _checkpoint(
        self,
        checkpoint_id: str,
        project_id: str,
    ) -> ProjectCheckpoint:
        async with SqlAlchemyUnitOfWork(self._database.sessions) as uow:
            checkpoint = await uow.projects.get_checkpoint(checkpoint_id)
        if checkpoint is None or checkpoint.project_id != project_id:
            raise DomainError(
                code="checkpoint.not_found",
                message="Checkpoint was not found",
                category=ErrorCategory.NOT_FOUND,
            )
        return checkpoint


async def _append_event(
    uow: SqlAlchemyUnitOfWork,
    *,
    event_type: str,
    correlation_id: str,
    project_id: str,
    occurred_at: datetime,
    payload: dict[str, object],
) -> None:
    await uow.events.append(
        envelope=EventEnvelope(
            schema_version=1,
            event_type=event_type,
            correlation_id=correlation_id,
            actor=ActorRef(type=ActorType.USER, id="user_local"),
            source=EventSource.BACKEND,
            occurred_at=occurred_at,
            project_id=project_id,
            payload=payload,
        ),
        aggregate_type="project",
        aggregate_id=project_id,
    )


def _require_open(project: Project) -> None:
    if project.status is ProjectStatus.CLOSED:
        raise DomainError(
            code="project.closed",
            message="Project is closed",
            category=ErrorCategory.CONFLICT,
        )


def _project_version_error(current_version: int) -> DomainError:
    return DomainError(
        code="project.version_conflict",
        message="Project version has changed",
        details={"current_version": current_version},
    )


async def _run_sync[ResultT](
    function: Callable[..., ResultT],
    *args: object,
    **kwargs: object,
) -> ResultT:
    operation: Callable[[], ResultT] = partial(function, *args, **kwargs)
    return await await_cancellation_resistant(asyncio.to_thread(operation))


def _default_manifest(project_id: str, source_root: Path) -> ProjectManifest:
    instruction_paths = ("AGENTS.md",) if (source_root / "AGENTS.md").is_file() else ()
    build_commands: list[ProjectCommand] = []
    test_commands: list[ProjectCommand] = []
    typecheck_commands: list[ProjectCommand] = []
    package_json = source_root / "package.json"
    if package_json.is_file():
        try:
            document = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            document = None
        scripts = document.get("scripts") if isinstance(document, dict) else None
        if isinstance(scripts, dict):
            for name, target in (
                ("build", build_commands),
                ("test", test_commands),
                ("typecheck", typecheck_commands),
            ):
                if isinstance(scripts.get(name), str):
                    target.append(
                        ProjectCommand(
                            schema_version=1,
                            argv=("npm", "run", name),
                        )
                    )
    if (source_root / "pyproject.toml").is_file() and (source_root / "tests").is_dir():
        test_commands.append(ProjectCommand(schema_version=1, argv=("python", "-m", "pytest")))
    return ProjectManifest(
        schema_version=1,
        project_id=project_id,
        manifest_version=1,
        excluded_paths=(".git", ".venv", "node_modules", "dist", "build", ".env"),
        instruction_paths=instruction_paths,
        build_commands=tuple(build_commands),
        test_commands=tuple(test_commands),
        typecheck_commands=tuple(typecheck_commands),
    )


def _remove_created_metadata(workspace_root: Path, project_id: str) -> None:
    root, _ = validate_direct_workspace_root(workspace_root)
    agent_root = root / ".agent"
    if not agent_root.is_dir() or agent_root.is_symlink():
        return
    try:
        metadata = ProjectMetadataStore(root).read_metadata()
    except DomainError:
        return
    if metadata.project_id != project_id:
        return
    for name in ("manifest.json", "project.json"):
        path = agent_root / name
        if path.is_file() and not path.is_symlink():
            path.unlink()
    try:
        agent_root.rmdir()
    except OSError:
        pass


def _remove_managed_workspace(data_root: Path, workspace_root: Path) -> None:
    resolved_data = data_root.resolve(strict=True)
    resolved_workspace = workspace_root.resolve(strict=True)
    expected_parent = resolved_data / "workspaces"
    metadata = resolved_workspace.lstat()
    is_reparse = bool(getattr(metadata, "st_file_attributes", 0) & 0x400)
    if resolved_workspace.parent != expected_parent or stat.S_ISLNK(metadata.st_mode) or is_reparse:
        raise RuntimeError("managed workspace cleanup path is unsafe")
    shutil.rmtree(resolved_workspace)
