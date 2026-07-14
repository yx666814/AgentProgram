from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_platform.domain.projects import (
    Project,
    ProjectRegistration,
    ProjectStatus,
    Workspace,
    WorkspaceMode,
)


def _project(now: datetime) -> Project:
    return Project(
        schema_version=1,
        id="project_1",
        name="Agent Program",
        goal="Build a reliable local agent workspace",
        status=ProjectStatus.PREFLIGHT_REQUIRED,
        created_at=now,
        updated_at=now,
        version=1,
    )


def _workspace(tmp_path: Path, now: datetime) -> Workspace:
    root = str(tmp_path.resolve())
    return Workspace(
        schema_version=1,
        id="workspace_1",
        project_id="project_1",
        mode=WorkspaceMode.DIRECT,
        root_path=root,
        canonical_root_path=root,
        created_at=now,
    )


def test_project_registration_is_versioned_and_consistent(tmp_path: Path) -> None:
    now = datetime.now(UTC)

    registration = ProjectRegistration(
        schema_version=1,
        project=_project(now),
        workspace=_workspace(tmp_path, now),
    )

    assert registration.project.status is ProjectStatus.PREFLIGHT_REQUIRED
    assert registration.workspace.mode is WorkspaceMode.DIRECT


def test_project_rejects_untrimmed_text_and_invalid_timestamp_order() -> None:
    now = datetime.now(UTC)

    with pytest.raises(ValidationError):
        Project(
            schema_version=1,
            id="project_1",
            name=" Agent Program",
            goal="Build it",
            status=ProjectStatus.PREFLIGHT_REQUIRED,
            created_at=now,
            updated_at=now,
            version=1,
        )

    with pytest.raises(ValidationError):
        Project(
            schema_version=1,
            id="project_1",
            name="Agent Program",
            goal="Build it",
            status=ProjectStatus.PREFLIGHT_REQUIRED,
            created_at=now,
            updated_at=now - timedelta(seconds=1),
            version=1,
        )


def test_registration_rejects_workspace_for_another_project(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    workspace = _workspace(tmp_path, now).model_copy(update={"project_id": "project_2"})

    with pytest.raises(ValidationError):
        ProjectRegistration(
            schema_version=1,
            project=_project(now),
            workspace=workspace,
        )
