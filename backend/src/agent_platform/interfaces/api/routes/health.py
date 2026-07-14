from typing import Literal

from fastapi import APIRouter, Request, status
from pydantic import BaseModel
from sqlalchemy import inspect, text

from agent_platform import __version__
from agent_platform.infrastructure.database.schema import (
    CURRENT_DATABASE_REVISION,
    REQUIRED_DATABASE_TABLES,
)
from agent_platform.infrastructure.database.session import Database
from agent_platform.interfaces.api.errors import PublicHttpError

router = APIRouter()


class SystemInfoResponse(BaseModel):
    backend_version: str
    protocol_version: Literal[1]


@router.get("/health")
async def health() -> dict[str, Literal["ok"]]:
    return {"status": "ok"}


@router.get("/system/info", response_model=SystemInfoResponse)
async def system_info() -> SystemInfoResponse:
    return SystemInfoResponse(backend_version=__version__, protocol_version=1)


@router.get("/readiness")
async def readiness(request: Request) -> dict[str, Literal["ready"]]:
    database: Database = request.app.state.database
    try:
        async with database.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            table_names = await connection.run_sync(
                lambda sync_connection: set(inspect(sync_connection).get_table_names())
            )
            if not REQUIRED_DATABASE_TABLES.issubset(table_names):
                raise RuntimeError("foundation database tables are unavailable")
            revision = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            if revision != CURRENT_DATABASE_REVISION:
                raise RuntimeError("foundation database revision is unavailable")
    except Exception:
        raise PublicHttpError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="readiness.unavailable",
            message="Service not ready",
            retryable=True,
        ) from None
    return {"status": "ready", "database": "ready"}
