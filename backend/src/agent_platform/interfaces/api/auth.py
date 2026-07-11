import secrets
from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agent_platform.config.settings import Settings

_bearer = HTTPBearer(auto_error=False)


def _invalid_session() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "auth.invalid_session",
            "message": "Invalid local session",
            "retryable": False,
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_session(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> None:
    settings: Settings = request.app.state.settings
    if credentials is None or credentials.scheme.lower() != "bearer":
        _invalid_session()
    if not secrets.compare_digest(credentials.credentials, settings.session_token):
        _invalid_session()
