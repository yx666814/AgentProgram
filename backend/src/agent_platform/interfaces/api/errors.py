from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from agent_platform.domain.shared.errors import DomainError, ErrorCategory

SENSITIVE_DETAIL_KEYS = {
    "api_key",
    "authorization",
    "credential",
    "password",
    "secret",
    "session_token",
    "token",
}
DOMAIN_ERROR_STATUS_CODES: Mapping[ErrorCategory, int] = {
    ErrorCategory.INVALID_INPUT: HTTPStatus.BAD_REQUEST,
    ErrorCategory.PERMISSION: HTTPStatus.FORBIDDEN,
    ErrorCategory.NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCategory.CONFLICT: HTTPStatus.CONFLICT,
    ErrorCategory.RATE_LIMITED: HTTPStatus.TOO_MANY_REQUESTS,
    ErrorCategory.UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
}


class PublicHttpError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(code, message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable
        self.headers = dict(headers) if headers is not None else None


def _http_status_message(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP error"


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "retryable": retryable,
            }
        },
        headers=headers,
    )


async def _http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        raise TypeError("HTTP exception handler received an unexpected exception")

    return error_response(
        status_code=exc.status_code,
        code="http.error",
        message=_http_status_message(exc.status_code),
        headers=exc.headers,
    )


async def _public_http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, PublicHttpError):
        raise TypeError("Public HTTP error handler received an unexpected exception")
    return error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        retryable=exc.retryable,
        headers=exc.headers,
    )


async def _domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise TypeError("Domain error handler received an unexpected exception")
    return error_response(
        status_code=DOMAIN_ERROR_STATUS_CODES[exc.category],
        code=exc.code,
        message=exc.message,
        details=_sanitize_details(exc.details),
        retryable=exc.retryable,
    )


def _sanitize_details(details: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _sanitize_detail_value(value, key=str(key)) for key, value in details.items()}


def _sanitize_detail_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and key.lower() in SENSITIVE_DETAIL_KEYS:
        return "***"
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return _sanitize_details(value)
    if isinstance(value, list | tuple):
        return [_sanitize_detail_value(item) for item in value]
    return None


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise TypeError("Validation error handler received an unexpected exception")
    return error_response(
        status_code=422,
        code="request.validation_failed",
        message="Request validation failed",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PublicHttpError, _public_http_error_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
