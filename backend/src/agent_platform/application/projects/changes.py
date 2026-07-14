from datetime import UTC, datetime

from agent_platform.domain.projects import (
    CheckpointRestorePlan,
    ExternalChange,
    ExternalChangeType,
    FileConflict,
    ProjectCheckpoint,
)
from agent_platform.domain.shared.ids import new_id


def detect_external_changes(
    baseline: ProjectCheckpoint,
    current: ProjectCheckpoint,
    *,
    detected_at: datetime | None = None,
) -> tuple[ExternalChange, ...]:
    _require_same_project(baseline, current)
    baseline_files = _file_hashes(baseline)
    current_files = _file_hashes(current)
    now = detected_at or datetime.now(UTC)
    changes: list[ExternalChange] = []
    for relative_path in sorted(baseline_files.keys() | current_files.keys()):
        before = baseline_files.get(relative_path)
        after = current_files.get(relative_path)
        if before == after:
            continue
        if before is None:
            change_type = ExternalChangeType.ADDED
        elif after is None:
            change_type = ExternalChangeType.DELETED
        else:
            change_type = ExternalChangeType.MODIFIED
        changes.append(
            ExternalChange(
                schema_version=1,
                id=new_id("change"),
                project_id=baseline.project_id,
                relative_path=relative_path,
                change_type=change_type,
                baseline_content_hash=before,
                current_content_hash=after,
                detected_at=now,
            )
        )
    return tuple(changes)


def detect_file_conflicts(
    baseline: ProjectCheckpoint,
    user: ProjectCheckpoint,
    agent: ProjectCheckpoint,
    *,
    created_at: datetime | None = None,
) -> tuple[FileConflict, ...]:
    _require_same_project(baseline, user, agent)
    baseline_files = _file_hashes(baseline)
    user_files = _file_hashes(user)
    agent_files = _file_hashes(agent)
    now = created_at or datetime.now(UTC)
    conflicts: list[FileConflict] = []
    paths = baseline_files.keys() | user_files.keys() | agent_files.keys()
    for relative_path in sorted(paths):
        before = baseline_files.get(relative_path)
        user_hash = user_files.get(relative_path)
        agent_hash = agent_files.get(relative_path)
        if user_hash == before or agent_hash == before or user_hash == agent_hash:
            continue
        conflicts.append(
            FileConflict(
                schema_version=1,
                id=new_id("conflict"),
                project_id=baseline.project_id,
                relative_path=relative_path,
                baseline_content_hash=before,
                user_content_hash=user_hash,
                agent_content_hash=agent_hash,
                version=1,
                created_at=now,
            )
        )
    return tuple(conflicts)


def build_restore_plan(
    current: ProjectCheckpoint,
    target: ProjectCheckpoint,
) -> CheckpointRestorePlan:
    _require_same_project(current, target)
    current_files = _file_hashes(current)
    target_files = _file_hashes(target)
    overwrite_paths = tuple(
        path for path in sorted(target_files) if current_files.get(path) != target_files[path]
    )
    preserved_extra_paths = tuple(sorted(current_files.keys() - target_files.keys()))
    return CheckpointRestorePlan(
        schema_version=1,
        current_checkpoint_id=current.id,
        target_checkpoint_id=target.id,
        overwrite_paths=overwrite_paths,
        preserved_extra_paths=preserved_extra_paths,
    )


def _file_hashes(checkpoint: ProjectCheckpoint) -> dict[str, str]:
    return {file.relative_path: file.content_hash for file in checkpoint.files}


def _require_same_project(*checkpoints: ProjectCheckpoint) -> None:
    if len({checkpoint.project_id for checkpoint in checkpoints}) != 1:
        raise ValueError("checkpoints must belong to the same project")
