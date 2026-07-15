from pathlib import Path
from tomllib import load

import pytest

import agent_platform.main as main_module
from agent_platform.config.settings import Settings


def test_run_consumes_validated_host_and_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        host="127.0.0.1",
        port=43210,
        data_root=tmp_path,
        session_token="local-secret",
    )
    configs: list[object] = []
    servers: list[object] = []
    prepared: list[str] = []

    class FakeConfig:
        def __init__(
            self,
            app: object,
            *,
            host: str,
            port: int,
            log_config: object,
        ) -> None:
            self.app = app
            self.host = host
            self.port = port
            self.log_config = log_config
            configs.append(self)

    class FakeServer:
        def __init__(self, config: object) -> None:
            self.config = config
            self.should_exit = False
            self.ran = False
            servers.append(self)

        def run(self) -> None:
            self.ran = True

    monkeypatch.setattr(main_module, "prepare_uvicorn_logging", prepared.append)
    monkeypatch.setattr(main_module.uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(main_module.uvicorn, "Server", FakeServer)

    main_module.run(settings)

    config = configs[0]
    server = servers[0]
    assert config.app.state.settings is settings
    assert (config.host, config.port, config.log_config) == ("127.0.0.1", 43210, None)
    assert server.ran is True
    assert config.app.state.shutdown_coordinator.request() is True
    assert server.should_exit is True
    assert prepared == ["INFO"]


def test_main_builds_settings_from_environment_and_delegates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "environment-data-root"
    session_token = "environment-secret"
    captured: list[Settings] = []
    monkeypatch.setenv("AGENT_PLATFORM_DATA_ROOT", str(data_root))
    monkeypatch.setenv("AGENT_PLATFORM_SESSION_TOKEN", session_token)
    monkeypatch.setenv("AGENT_PLATFORM_HOST", "127.0.0.1")
    monkeypatch.setenv("AGENT_PLATFORM_PORT", "43123")
    monkeypatch.setattr(main_module, "run", captured.append)

    main_module.main()

    assert len(captured) == 1
    settings = captured[0]
    assert settings.data_root == data_root
    assert settings.host == "127.0.0.1"
    assert settings.port == 43123
    assert settings.session_token == session_token
    assert session_token not in repr(settings)
    assert session_token not in str(settings.model_dump())


def test_project_exposes_backend_console_script() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    with pyproject_path.open("rb") as pyproject_file:
        pyproject = load(pyproject_file)

    assert pyproject["project"]["scripts"] == {"agent-platform-backend": "agent_platform.main:main"}
