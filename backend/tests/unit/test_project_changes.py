from datetime import UTC, datetime

from agent_platform.application.projects.changes import (
    build_restore_plan,
    detect_external_changes,
    detect_file_conflicts,
)
from agent_platform.domain.projects import (
    CheckpointFile,
    CheckpointReason,
    ExternalChangeType,
    ProjectCheckpoint,
)


def _hash(character: str) -> str:
    return character * 64


def _checkpoint(checkpoint_id: str, files: dict[str, str]) -> ProjectCheckpoint:
    checkpoint_files = tuple(
        CheckpointFile(relative_path=path, content_hash=content_hash, byte_size=1)
        for path, content_hash in sorted(files.items())
    )
    return ProjectCheckpoint(
        schema_version=1,
        id=checkpoint_id,
        project_id="project_1",
        manifest_version=1,
        reason=CheckpointReason.MANUAL,
        content_hash=_hash("f"),
        files=checkpoint_files,
        total_bytes=len(checkpoint_files),
        created_at=datetime.now(UTC),
    )


def test_external_changes_classify_added_modified_and_deleted() -> None:
    baseline = _checkpoint(
        "checkpoint_base",
        {"deleted.txt": _hash("a"), "modified.txt": _hash("b")},
    )
    current = _checkpoint(
        "checkpoint_current",
        {"added.txt": _hash("c"), "modified.txt": _hash("d")},
    )

    changes = detect_external_changes(baseline, current)

    assert [(change.relative_path, change.change_type) for change in changes] == [
        ("added.txt", ExternalChangeType.ADDED),
        ("deleted.txt", ExternalChangeType.DELETED),
        ("modified.txt", ExternalChangeType.MODIFIED),
    ]


def test_three_way_conflict_requires_both_sides_to_diverge() -> None:
    baseline = _checkpoint(
        "checkpoint_base",
        {"conflict.txt": _hash("a"), "user-only.txt": _hash("b")},
    )
    user = _checkpoint(
        "checkpoint_user",
        {"conflict.txt": _hash("c"), "user-only.txt": _hash("d")},
    )
    agent = _checkpoint(
        "checkpoint_agent",
        {"conflict.txt": _hash("e"), "user-only.txt": _hash("b")},
    )

    conflicts = detect_file_conflicts(baseline, user, agent)

    assert len(conflicts) == 1
    assert conflicts[0].relative_path == "conflict.txt"
    assert conflicts[0].baseline_content_hash == _hash("a")
    assert conflicts[0].user_content_hash == _hash("c")
    assert conflicts[0].agent_content_hash == _hash("e")


def test_identical_user_and_agent_edits_do_not_conflict() -> None:
    baseline = _checkpoint("checkpoint_base", {"same.txt": _hash("a")})
    user = _checkpoint("checkpoint_user", {"same.txt": _hash("b")})
    agent = _checkpoint("checkpoint_agent", {"same.txt": _hash("b")})

    assert detect_file_conflicts(baseline, user, agent) == ()


def test_restore_plan_overwrites_target_changes_and_preserves_extra_user_files() -> None:
    current = _checkpoint(
        "checkpoint_current",
        {"changed.txt": _hash("b"), "extra.txt": _hash("c")},
    )
    target = _checkpoint(
        "checkpoint_target",
        {"changed.txt": _hash("a"), "missing.txt": _hash("d")},
    )

    plan = build_restore_plan(current, target)

    assert plan.overwrite_paths == ("changed.txt", "missing.txt")
    assert plan.preserved_extra_paths == ("extra.txt",)
