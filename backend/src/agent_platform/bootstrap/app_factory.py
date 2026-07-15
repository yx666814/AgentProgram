from typing import cast

from fastapi import Depends, FastAPI
from starlette.types import ASGIApp

from agent_platform import __version__
from agent_platform.bootstrap.lifespan import build_lifespan
from agent_platform.config.settings import Settings
from agent_platform.interfaces.api.auth import require_session
from agent_platform.interfaces.api.errors import register_error_handlers
from agent_platform.interfaces.api.middleware import UnexpectedErrorMiddleware
from agent_platform.interfaces.api.routes.events import ticket_router, websocket_router
from agent_platform.interfaces.api.routes.health import router as health_router
from agent_platform.interfaces.api.routes.model_runtime import router as model_runtime_router
from agent_platform.interfaces.api.routes.projects import router as projects_router
from agent_platform.interfaces.api.routes.workflows import router as workflows_router


class AgentPlatformFastAPI(FastAPI):
    def build_middleware_stack(self) -> ASGIApp:
        sanitizers = [
            middleware
            for middleware in self.user_middleware
            if cast(object, middleware.cls) is UnexpectedErrorMiddleware
        ]
        other_middleware = [
            middleware
            for middleware in self.user_middleware
            if cast(object, middleware.cls) is not UnexpectedErrorMiddleware
        ]
        self.user_middleware[:] = [*sanitizers, *other_middleware]
        return super().build_middleware_stack()


def create_app(settings: Settings) -> FastAPI:
    app = AgentPlatformFastAPI(
        title="Agent Platform Backend",
        version=__version__,
        lifespan=build_lifespan(settings),
    )
    app.state.settings = settings
    app.add_middleware(UnexpectedErrorMiddleware)
    app.include_router(
        health_router,
        prefix="/api/v1",
        dependencies=[Depends(require_session)],
    )
    app.include_router(
        projects_router,
        prefix="/api/v1",
        dependencies=[Depends(require_session)],
    )
    app.include_router(
        workflows_router,
        prefix="/api/v1",
        dependencies=[Depends(require_session)],
    )
    app.include_router(
        ticket_router,
        prefix="/api/v1",
        dependencies=[Depends(require_session)],
    )
    app.include_router(
        model_runtime_router,
        prefix="/api/v1",
        dependencies=[Depends(require_session)],
    )
    app.include_router(websocket_router, prefix="/api/v1")
    register_error_handlers(app)
    return app


def dev_app() -> FastAPI:
    return create_app(Settings())
