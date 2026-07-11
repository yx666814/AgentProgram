from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

from agent_platform.infrastructure.database.session import Database

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, Literal["ok"]]:
    return {"status": "ok"}


@router.get("/readiness")
async def readiness(request: Request) -> dict[str, Literal["ready"]]:
    database: Database = request.app.state.database
    try:
        async with database.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "readiness.unavailable",
                "message": "Service not ready",
                "retryable": True,
            },
        ) from None
    return {"status": "ready", "database": "ready"}
