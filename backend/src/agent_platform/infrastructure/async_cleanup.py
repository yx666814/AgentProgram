import asyncio
from collections.abc import Awaitable


async def await_cancellation_resistant[T](awaitable: Awaitable[T]) -> T:
    cleanup_task = asyncio.ensure_future(awaitable)
    cancellation: asyncio.CancelledError | None = None

    while not cleanup_task.done():
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError as current_cancellation:
            if cancellation is None:
                cancellation = current_cancellation
        except BaseException:
            break

    try:
        result = cleanup_task.result()
    except asyncio.CancelledError as cleanup_cancellation:
        if cancellation is not None:
            raise cancellation from cleanup_cancellation
        raise
    except BaseException as cleanup_error:
        if cancellation is not None:
            raise cancellation from cleanup_error
        raise

    if cancellation is not None:
        raise cancellation
    return result
