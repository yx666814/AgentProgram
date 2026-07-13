import asyncio
from collections.abc import Awaitable

_CLEANUP_FAILURE_NOTE = "Additional cleanup failure occurred."


def _add_cleanup_failure_note(cancellation: asyncio.CancelledError) -> None:
    original_cause = cancellation.__cause__
    original_context = cancellation.__context__
    original_suppress_context = cancellation.__suppress_context__
    try:
        BaseException.add_note(cancellation, _CLEANUP_FAILURE_NOTE)
    except BaseException:
        pass
    cancellation.__cause__ = original_cause
    cancellation.__context__ = original_context
    cancellation.__suppress_context__ = original_suppress_context


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

    cleanup_failed = False
    try:
        result = cleanup_task.result()
    except BaseException:
        if cancellation is None:
            raise
        cleanup_failed = True
    else:
        if cancellation is None:
            return result

    assert cancellation is not None
    if cleanup_failed:
        _add_cleanup_failure_note(cancellation)
    raise cancellation
