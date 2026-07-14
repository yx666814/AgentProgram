import uvicorn

from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings


def run(settings: Settings) -> None:
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
    )


def main() -> None:
    run(Settings())
