from typing import Any

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

from agent_platform.interfaces.api.errors import error_response

logger = structlog.get_logger(__name__)


class UnexpectedErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        try:
            await self._app(scope, receive, send)
        except Exception as exc:
            logger.error(
                "unhandled_request_error",
                exception_type=type(exc).__name__,
                method=_scope_text(scope, "method"),
                path=_scope_text(scope, "path"),
            )
            response = error_response(
                status_code=500,
                code="internal.error",
                message="Internal server error",
            )
            await response(scope, receive, send)


def _scope_text(scope: Scope, key: str) -> str | None:
    value: Any = scope.get(key)
    return value if isinstance(value, str) else None
