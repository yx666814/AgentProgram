from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_platform.application.projects.preflight import run_project_preflight
from agent_platform.domain.projects import (
    PersistedProjectManifest,
    PreflightStatus,
    Project,
    ProjectCommand,
    ProjectManifest,
    ProjectMetadata,
    ProjectRegistration,
    ProjectStatus,
    Workspace,
    WorkspaceMode,
)
from agent_platform.infrastructure.projects.metadata import (
    ProjectMetadataStore,
    project_document_hash,
)
from agent_platform.infrastructure.projects.paths import validate_direct_workspace_root


def _registration(root: Path) -> ProjectRegistration:
    now = datetime.now(UTC)
    resolved, canonical = validate_direct_workspace_root(root)
    return ProjectRegistration(
        schema_version=1,
        project=Project(
            schema_version=1,
            id="project_1",
            name="Project One",
            goal="Validate the workspace before execution",
            status=ProjectStatus.PREFLIGHT_REQUIRED,
            created_at=now,
            updated_at=now,
            version=1,
        ),
        workspace=Workspace(
            schema_version=1,
            id="workspace_1",
            project_id="project_1",
            mode=WorkspaceMode.DIRECT,
            root_path=str(resolved),
            canonical_root_path=canonical,
            created_at=now,
        ),
    )


def _prepare(
    root: Path,
    manifest: ProjectManifest,
) -> tuple[ProjectRegistration, PersistedProjectManifest, ProjectMetadataStore]:
    registration = _registration(root)
    store = ProjectMetadataStore(root)
    store.initialize(
        ProjectMetadata(
            schema_version=1,
            project_id="project_1",
            workspace_id="workspace_1",
            workspace_mode=WorkspaceMode.DIRECT,
            created_at=datetime.now(UTC),
        )
    )
    content_hash = store.write_manifest(manifest, expected_version=None)
    persisted = PersistedProjectManifest(
        schema_version=1,
        manifest=manifest,
        content_hash=content_hash,
        updated_at=datetime.now(UTC),
    )
    return registration, persisted, store


def test_preflight_passes_when_paths_and_commands_are_available(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "backend").mkdir()
    (tmp_path / "AGENTS.md").write_text("instructions\n", encoding="utf-8")
    command = ProjectCommand(
        schema_version=1,
        argv=("python", "-m", "pytest"),
        working_directory="backend",
    )
    manifest = ProjectManifest(
        schema_version=1,
        project_id="project_1",
        manifest_version=1,
        source_paths=("src",),
        instruction_paths=("AGENTS.md",),
        build_commands=(command,),
        test_commands=(command,),
        typecheck_commands=(command,),
    )
    registration, persisted, store = _prepare(tmp_path, manifest)

    result = run_project_preflight(registration, persisted, store)

    assert result.status is PreflightStatus.PASS
    assert all(check.status is PreflightStatus.PASS for check in result.checks)


def test_preflight_warns_when_commands_are_not_configured(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    manifest = ProjectManifest(
        schema_version=1,
        project_id="project_1",
        manifest_version=1,
        source_paths=("src",),
    )
    registration, persisted, store = _prepare(tmp_path, manifest)

    result = run_project_preflight(registration, persisted, store)

    assert result.status is PreflightStatus.WARNING
    assert {check.code for check in result.checks if check.status is PreflightStatus.WARNING} == {
        "manifest.build_commands",
        "manifest.test_commands",
        "manifest.typecheck_commands",
    }


def test_preflight_requires_fix_for_missing_manifest_paths(tmp_path: Path) -> None:
    manifest = ProjectManifest(
        schema_version=1,
        project_id="project_1",
        manifest_version=1,
        source_paths=("missing",),
    )
    registration, persisted, store = _prepare(tmp_path, manifest)

    result = run_project_preflight(registration, persisted, store)

    assert result.status is PreflightStatus.NEEDS_FIX
    source_check = next(check for check in result.checks if check.code == "manifest.source_paths")
    assert source_check.evidence == {"paths": ["missing"]}


def test_preflight_fails_for_manifest_path_through_link(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-preflight"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create directory links")
    manifest = ProjectManifest(
        schema_version=1,
        project_id="project_1",
        manifest_version=1,
        source_paths=("linked",),
    )
    registration, persisted, store = _prepare(tmp_path, manifest)

    result = run_project_preflight(registration, persisted, store)

    assert result.status is PreflightStatus.FAIL
    assert any(check.code == "manifest.source_paths" for check in result.checks)


def test_preflight_fails_when_database_manifest_hash_differs(tmp_path: Path) -> None:
    manifest = ProjectManifest(
        schema_version=1,
        project_id="project_1",
        manifest_version=1,
    )
    registration, persisted, store = _prepare(tmp_path, manifest)
    persisted = persisted.model_copy(update={"content_hash": "f" * 64})
    assert persisted.content_hash != project_document_hash(manifest)

    result = run_project_preflight(registration, persisted, store)

    assert result.status is PreflightStatus.FAIL
    assert result.checks[-1].code == "project.manifest"
