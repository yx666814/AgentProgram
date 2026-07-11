from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from agent_platform.domain.shared.errors import DomainError

logger = structlog.get_logger(__name__)


def _error_response(
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

    detail = exc.detail
    if isinstance(detail, Mapping):
        code = str(detail.get("code", "http.error"))
        message = str(detail.get("message", HTTPStatus(exc.status_code).phrase))
        raw_details = detail.get("details")
        details = dict(raw_details) if isinstance(raw_details, Mapping) else {}
        retryable = detail.get("retryable") is True
    else:
        code = "http.error"
        message = HTTPStatus(exc.status_code).phrase
        details = {}
        retryable = False

    return _error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        details=details,
        retryable=retryable,
        headers=exc.headers,
    )


async def _domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise TypeError("Domain error handler received an unexpected exception")
    return _error_response(
        status_code=409,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        retryable=exc.retryable,
    )


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise TypeError("Validation error handler received an unexpected exception")
    sanitized_errors = [
        {
            "type": str(error.get("type", "validation_error")),
            "location": [str(part) for part in error.get("loc", ())],
            "message": str(error.get("msg", "Invalid value")),
        }
        for error in exc.errors()
    ]
    return _error_response(
        status_code=422,
        code="request.validation_failed",
        message="Request validation failed",
        details={"errors": sanitized_errors},
    )


async def _unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_request_error",
        exception_type=type(exc).__name__,
    )
    return _error_response(
        status_code=500,
        code="internal.error",
        message="Internal server error",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unexpected_error_handler)
