import asyncio
import hashlib
import sys
from pathlib import Path

import psutil
import pytest

from agent_platform.domain.contracts import Stage
from agent_platform.domain.projects import ProjectCommand, ProjectManifest
from agent_platform.domain.shared.errors import DomainError
from agent_platform.infrastructure.tooling import (
    AtomicFileTools,
    ControlledProcessRunner,
    PathGuard,
    ToolCatalog,
    ToolProcessRegistry,
)

TOOL_PROCESS_TREE_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "tool_process_tree.py"
)


def _manifest(project_id: str = "project_test") -> ProjectManifest:
    return ProjectManifest(
        schema_version=1,
        project_id=project_id,
        manifest_version=1,
        source_paths=("src",),
        excluded_paths=(".env",),
    )


def test_path_guard_enforces_stage_scope_and_exclusions() -> None:
    catalog = ToolCatalog()
    guard = PathGuard()
    manifest = _manifest()

    guard.authorize_capability(Stage.BUILDER, catalog.get("filesystem.write_source"))
    assert (
        guard.authorize_path(
            Stage.BUILDER,
            catalog.get("filesystem.write_source"),
            "src/app.py",
            manifest,
        ).value
        == "project_source"
    )

    with pytest.raises(DomainError) as planner_error:
        guard.authorize_capability(Stage.PLANNER, catalog.get("filesystem.write_source"))
    assert planner_error.value.code == "tool.capability_forbidden"

    with pytest.raises(DomainError) as excluded_error:
        guard.authorize_path(
            Stage.BUILDER,
            catalog.get("filesystem.write_source"),
            ".env/token",
            manifest,
        )
    assert excluded_error.value.code == "tool.path_excluded"


def test_atomic_file_tools_require_expected_hash_for_overwrite(tmp_path: Path) -> None:
    tools = AtomicFileTools(max_file_bytes=1024)
    first = tools.write(tmp_path, "src/app.py", b"first", expected_hash=None)
    assert first.content_hash == hashlib.sha256(b"first").hexdigest()

    with pytest.raises(DomainError) as conflict:
        tools.write(tmp_path, "src/app.py", b"second", expected_hash=None)
    assert conflict.value.code == "tool.file_version_conflict"

    second = tools.write(
        tmp_path,
        "src/app.py",
        b"second",
        expected_hash=first.content_hash,
    )
    assert second.content_hash == hashlib.sha256(b"second").hexdigest()
    read_result, payload = tools.read(tmp_path, "src/app.py")
    assert read_result == second
    assert payload == b"second"

    deleted = tools.delete(
        tmp_path,
        "src/app.py",
        expected_hash=second.content_hash,
    )
    assert deleted == second
    assert not (tmp_path / "src/app.py").exists()


@pytest.mark.asyncio
async def test_controlled_process_timeout_kills_process_tree(tmp_path: Path) -> None:
    marker = tmp_path / "child.pid"
    manifest = ProjectManifest(
        schema_version=1,
        project_id="project_process",
        manifest_version=1,
        test_commands=(
            ProjectCommand(
                schema_version=1,
                argv=(sys.executable, str(TOOL_PROCESS_TREE_FIXTURE), str(marker)),
                timeout_seconds=60,
            ),
        ),
    )
    registry = ToolProcessRegistry()
    runner = ControlledProcessRunner(registry, max_output_bytes=1024 * 1024)

    with pytest.raises(DomainError) as timeout:
        await runner.run(
            "toolcall_process_tree",
            tmp_path,
            manifest,
            tool_name="shell.test",
            command_index=0,
            timeout_seconds=1,
        )
    assert timeout.value.code == "tool.command_timed_out"
    child_pid = int(await asyncio.to_thread(marker.read_text, encoding="ascii"))
    for _ in range(100):
        if not psutil.pid_exists(child_pid):
            break
        await asyncio.sleep(0.02)
    assert not psutil.pid_exists(child_pid)
