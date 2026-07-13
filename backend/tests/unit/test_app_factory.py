from pathlib import Path

import agent_platform.bootstrap.app_factory as app_factory


def test_dev_app_builds_settings_from_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "environment-data-root"
    monkeypatch.setenv("AGENT_PLATFORM_SESSION_TOKEN", "development-token")
    monkeypatch.setenv("AGENT_PLATFORM_DATA_ROOT", str(data_root))

    factory = getattr(app_factory, "dev_app", None)
    assert callable(factory), "dev_app must be available as a zero-argument factory"

    app = factory()

    assert app.state.settings.session_token == "development-token"
    assert app.state.settings.data_root == data_root
