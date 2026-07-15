from importlib.metadata import version
from pathlib import Path

import pytest

import agent_platform
import agent_platform.bootstrap.app_factory as app_factory
from agent_platform.config.settings import Settings


def test_backend_version_matches_installed_package_metadata() -> None:
    assert agent_platform.__version__ == version("agent-platform-backend")


def test_fastapi_metadata_uses_backend_package_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_factory, "__version__", "9.8.7", raising=False)

    app = app_factory.create_app(Settings(data_root=tmp_path, session_token="local-secret"))

    assert app.version == "9.8.7"
