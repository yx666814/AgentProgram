import asyncio
from collections.abc import Awaitable

import pytest

from agent_platform.infrastructure.async_cleanup import await_cancellation_resistant

_CLEANUP_FAILURE_NOTE = "Additional cleanup failure occurred."
_CLEANUP_SECRET = "SECRET_CLEANUP_DETAIL"


def _inject_cancellation_once(
    monkeypatch: pytest.MonkeyPatch,
    cancellation: asyncio.CancelledError,
) -> None:
    shield = asyncio.shield
    injected = False

    def injecting_shield(awaitable: Awaitable[object]) -> Awaitable[object]:
        nonlocal injected
        if not injected:
            injected = True

            async def raise_cancellation() -> object:
                raise cancellation

            return raise_cancellation()
        return shield(awaitable)

    monkeypatch.setattr(asyncio, "shield", injecting_shield)


def _exposed_error_text(error: BaseException) -> str:
    return "\n".join(
        (
            str(error),
            repr(error),
            repr(error.__cause__),
            repr(error.__context__),
            repr(getattr(error, "__notes__", None)),
        )
    )


@pytest.mark.parametrize(
    "cleanup_error_type",
    [RuntimeError, asyncio.CancelledError],
    ids=["cleanup-error", "cleanup-cancellation"],
)
@pytest.mark.asyncio
async def test_external_cancellation_redacts_cleanup_failure_after_cleanup_finishes(
    cleanup_error_type: type[BaseException],
) -> None:
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    cleanup_finished = False
    observed_cancellations: list[asyncio.CancelledError] = []

    async def cleanup() -> None:
        nonlocal cleanup_finished
        cleanup_started.set()
        await release_cleanup.wait()
        cleanup_finished = True
        raise cleanup_error_type(_CLEANUP_SECRET)

    async def run_cleanup() -> None:
        try:
            await await_cancellation_resistant(cleanup())
        except asyncio.CancelledError as error:
            observed_cancellations.append(error)
            raise

    cleanup_owner = asyncio.create_task(run_cleanup())
    await asyncio.wait_for(cleanup_started.wait(), timeout=1)

    cleanup_owner.cancel("primary cancellation")
    await asyncio.sleep(0)
    assert cleanup_finished is False
    release_cleanup.set()

    with pytest.raises(asyncio.CancelledError, match="primary cancellation") as raised:
        await cleanup_owner

    assert cleanup_finished is True
    assert observed_cancellations == [raised.value]
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert raised.value.__suppress_context__ is False
    assert raised.value.__notes__ == [_CLEANUP_FAILURE_NOTE]
    assert _CLEANUP_SECRET not in _exposed_error_text(raised.value)


@pytest.mark.asyncio
async def test_cleanup_failure_preserves_original_cancellation_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_cause = RuntimeError("original cause")
    original_context = LookupError("original context")
    cancellation = asyncio.CancelledError("primary cancellation")
    cancellation.__cause__ = original_cause
    cancellation.__context__ = original_context
    cancellation.__suppress_context__ = True
    cancellation.add_note("original cancellation note")
    _inject_cancellation_once(monkeypatch, cancellation)
    cleanup_finished = False

    async def cleanup() -> None:
        nonlocal cleanup_finished
        cleanup_finished = True
        raise RuntimeError(_CLEANUP_SECRET)

    with pytest.raises(asyncio.CancelledError) as raised:
        await await_cancellation_resistant(cleanup())

    assert cleanup_finished is True
    assert raised.value is cancellation
    assert raised.value.__cause__ is original_cause
    assert raised.value.__context__ is original_context
    assert raised.value.__suppress_context__ is True
    assert raised.value.__notes__ == ["original cancellation note", _CLEANUP_FAILURE_NOTE]
    assert _CLEANUP_SECRET not in _exposed_error_text(raised.value)


@pytest.mark.asyncio
async def test_cleanup_note_bypasses_cancelled_error_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class OverridingCancelledError(asyncio.CancelledError):
        def add_note(self, note: str) -> None:
            del note
            raise RuntimeError("SECRET_NOTE_OVERRIDE")

    cancellation = OverridingCancelledError("primary cancellation")
    _inject_cancellation_once(monkeypatch, cancellation)

    async def cleanup() -> None:
        raise RuntimeError(_CLEANUP_SECRET)

    with pytest.raises(OverridingCancelledError) as raised:
        await await_cancellation_resistant(cleanup())

    assert raised.value is cancellation
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert raised.value.__suppress_context__ is False
    assert raised.value.__notes__ == [_CLEANUP_FAILURE_NOTE]
    assert "SECRET_NOTE_OVERRIDE" not in _exposed_error_text(raised.value)
    assert _CLEANUP_SECRET not in _exposed_error_text(raised.value)


@pytest.mark.asyncio
async def test_invalid_cancellation_notes_do_not_replace_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_cause = RuntimeError("original cause")
    original_context = LookupError("original context")
    cancellation = asyncio.CancelledError("primary cancellation")
    cancellation.__cause__ = original_cause
    cancellation.__context__ = original_context
    cancellation.__suppress_context__ = True
    cancellation.__dict__["__notes__"] = "invalid notes"
    _inject_cancellation_once(monkeypatch, cancellation)

    async def cleanup() -> None:
        raise RuntimeError(_CLEANUP_SECRET)

    with pytest.raises(asyncio.CancelledError) as raised:
        await await_cancellation_resistant(cleanup())

    assert raised.value is cancellation
    assert raised.value.__cause__ is original_cause
    assert raised.value.__context__ is original_context
    assert raised.value.__suppress_context__ is True
    assert raised.value.__dict__["__notes__"] == "invalid notes"
    assert _CLEANUP_SECRET not in _exposed_error_text(raised.value)


@pytest.mark.asyncio
async def test_cleanup_failure_propagates_without_external_cancellation() -> None:
    cleanup_error = RuntimeError(_CLEANUP_SECRET)

    async def cleanup() -> None:
        raise cleanup_error

    with pytest.raises(RuntimeError, match=_CLEANUP_SECRET) as raised:
        await await_cancellation_resistant(cleanup())

    assert raised.value is cleanup_error
