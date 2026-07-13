import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from agent_platform.interfaces.api.errors import error_response

logger = structlog.get_logger(__name__)
SAFE_HTTP_METHODS = {
    "CONNECT",
    "DELETE",
    "GET",
    "HEAD",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
    "TRACE",
}


class UnexpectedErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        response_started = False
        response_completed = False

        async def track_response(message: Message) -> None:
            nonlocal response_completed, response_started
            if message["type"] == "http.response.start":
                response_started = True
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                response_completed = True
            await send(message)

        try:
            await self._app(scope, receive, track_response)
        except Exception as exc:
            logger.error(
                "unhandled_request_error",
                exception_type=type(exc).__name__,
                method=_safe_http_method(scope),
            )
            if not response_started:
                response = error_response(
                    status_code=500,
                    code="internal.error",
                    message="Internal server error",
                )
                await response(scope, receive, track_response)
            elif not response_completed:
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                        "more_body": False,
                    }
                )


def _safe_http_method(scope: Scope) -> str:
    method = scope.get("method")
    return method if isinstance(method, str) and method in SAFE_HTTP_METHODS else "UNKNOWN"
