from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_platform.domain.projects import (
    ProjectManifest,
    ProjectMetadata,
    WorkspaceMode,
)
from agent_platform.infrastructure.projects.metadata import (
    ProjectMetadataError,
    ProjectMetadataStore,
)


def _metadata(project_id: str = "project_1") -> ProjectMetadata:
    return ProjectMetadata(
        schema_version=1,
        project_id=project_id,
        workspace_id="workspace_1",
        workspace_mode=WorkspaceMode.DIRECT,
        created_at=datetime.now(UTC),
    )


def _manifest(version: int, source: str) -> ProjectManifest:
    return ProjectManifest(
        schema_version=1,
        project_id="project_1",
        manifest_version=version,
        source_paths=(source,),
    )


def test_project_metadata_and_manifest_are_atomically_published(tmp_path: Path) -> None:
    store = ProjectMetadataStore(tmp_path)

    metadata_hash = store.initialize(_metadata())
    manifest_hash = store.write_manifest(_manifest(1, "src"), expected_version=None)

    assert len(metadata_hash) == 64
    assert len(manifest_hash) == 64
    assert store.read_metadata().project_id == "project_1"
    assert store.read_manifest() == _manifest(1, "src")
    assert not list((tmp_path / ".agent").glob("*.tmp"))


def test_project_metadata_initialization_is_idempotent_but_not_reassignable(
    tmp_path: Path,
) -> None:
    store = ProjectMetadataStore(tmp_path)
    metadata = _metadata()

    assert store.initialize(metadata) == store.initialize(metadata)
    with pytest.raises(ProjectMetadataError) as raised:
        store.initialize(_metadata("project_2"))

    assert raised.value.code == "project.metadata_conflict"


def test_manifest_optimistic_version_allows_only_one_concurrent_writer(
    tmp_path: Path,
) -> None:
    store = ProjectMetadataStore(tmp_path)
    store.initialize(_metadata())
    store.write_manifest(_manifest(1, "src"), expected_version=None)

    def update(source: str) -> str:
        try:
            return store.write_manifest(_manifest(2, source), expected_version=1)
        except ProjectMetadataError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update, ("backend", "frontend")))

    assert sum(result == "project.manifest_version_conflict" for result in results) == 1
    assert sum(len(result) == 64 for result in results) == 1
    assert store.read_manifest().manifest_version == 2
    assert store.read_manifest().source_paths in {("backend",), ("frontend",)}


def test_manifest_requires_matching_initialized_project(tmp_path: Path) -> None:
    store = ProjectMetadataStore(tmp_path)
    store.initialize(_metadata("project_2"))

    with pytest.raises(ProjectMetadataError) as raised:
        store.write_manifest(_manifest(1, "src"), expected_version=None)

    assert raised.value.code == "project.manifest_project_mismatch"


def test_agent_metadata_directory_rejects_links(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-metadata"
    outside.mkdir()
    agent_root = tmp_path / ".agent"
    try:
        agent_root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create directory links")

    with pytest.raises(ProjectMetadataError) as raised:
        ProjectMetadataStore(tmp_path).initialize(_metadata())

    assert raised.value.code == "project.metadata_path_unsafe"
