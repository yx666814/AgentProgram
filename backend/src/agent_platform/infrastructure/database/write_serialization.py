import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


@asynccontextmanager
async def serialized_write(lock: asyncio.Lock | None) -> AsyncIterator[None]:
    if lock is None:
        yield
        return
    await lock.acquire()
    try:
        yield
    finally:
        lock.release()
