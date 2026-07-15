from typing import cast

import uvicorn

from agent_platform.application.system_control import ShutdownCoordinator
from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.infrastructure.logging.configure import prepare_uvicorn_logging


def run(settings: Settings) -> None:
    prepare_uvicorn_logging(settings.log_level)
    app = create_app(settings)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=settings.host,
            port=settings.port,
            log_config=None,
        )
    )
    coordinator = cast(ShutdownCoordinator, app.state.shutdown_coordinator)
    coordinator.bind(lambda: setattr(server, "should_exit", True))
    server.run()


def main() -> None:
    run(Settings())
