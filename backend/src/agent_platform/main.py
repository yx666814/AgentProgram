import uvicorn

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.infrastructure.logging.configure import prepare_uvicorn_logging


def run(settings: Settings) -> None:
    prepare_uvicorn_logging(settings.log_level)
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


def main() -> None:
    run(Settings())
