from datetime import datetime, timedelta
from typing import Annotated

from pydantic import Field

ContractId = Annotated[
    str,
    Field(
        min_length=3,
        max_length=80,
        pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$",
    ),
]
ContractName = Annotated[
    str,
    Field(
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
    ),
]
IdempotencyKey = Annotated[
    str,
    Field(
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
PositiveVersion = Annotated[int, Field(gt=0)]
SemanticVersion = Annotated[
    str,
    Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"),
]


def require_utc(value: datetime, *, field_name: str) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return value


def require_project_relative_path(value: object) -> str:
    if type(value) is not str:
        raise ValueError("path must be a canonical project-relative path")
    path = value
    parts = path.split("/")
    if (
        not path
        or path != path.strip()
        or path.startswith("/")
        or "\\" in path
        or ":" in path
        or "\x00" in path
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("path must be a canonical project-relative path")
    return path
