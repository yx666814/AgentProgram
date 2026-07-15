from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    INVALID_INPUT = "invalid_input"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"


@dataclass(eq=False)
class DomainError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    category: ErrorCategory = ErrorCategory.CONFLICT

    def __post_init__(self) -> None:
        Exception.__init__(self, self.code, self.message, self.details, self.retryable)

    def __str__(self) -> str:
        return self.message
