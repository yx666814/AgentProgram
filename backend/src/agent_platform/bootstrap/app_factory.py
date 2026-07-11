from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from agent_platform.config.settings import Settings
from agent_platform.infrastructure.async_cleanup import await_cancellation_resistant
from agent_platform.infrastructure.database.session import create_database
from agent_platform.interfaces.api.auth import require_session
from agent_platform.interfaces.api.errors import register_error_handlers
from agent_platform.interfaces.api.middleware import UnexpectedErrorMiddleware
from agent_platform.interfaces.api.routes.health import router as health_router


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_directories()
        database = create_database(settings.database_path)
        app.state.database = database
        try:
            yield
        finally:
            try:
                await await_cancellation_resistant(database.dispose())
            finally:
                del app.state.database

    app = FastAPI(
        title="Agent Platform Backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(UnexpectedErrorMiddleware)
    app.include_router(
        health_router,
        prefix="/api/v1",
        dependencies=[Depends(require_session)],
    )
    register_error_handlers(app)
    return app
