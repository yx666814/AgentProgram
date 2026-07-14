import asyncio
import sqlite3
from datetime import timedelta
from pathlib import Path
from types import TracebackType

import pytest

import agent_platform.bootstrap.lifespan as lifespan_module
from agent_platform.bootstrap.app_factory import create_app
from agent_platform.config.settings import Settings
from agent_platform.infrastructure.database.session import Database, create_database
from agent_platform.infrastructure.workers.supervisor import WorkerSupervisor


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_root=tmp_path, session_token="local-secret")


class _WatchdogProbeConnection:
    async def __aenter__(self) -> "_WatchdogProbeConnection":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def execute(self, statement: object) -> None:
        assert str(statement) == "SELECT 1"


class _WatchdogProbeEngine:
    def connect(self) -> _WatchdogProbeConnection:
        return _WatchdogProbeConnection()


class _TrackingWatchdogDatabase:
    engine = _WatchdogProbeEngine()

    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def dispose(self) -> None:
        self._events.append("dispose")


@pytest.mark.asyncio
async def test_application_lifespan_manages_database_and_real_worker(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path))

    async with app.router.lifespan_context(app):
        database = app.state.database
        supervisor = app.state.worker_supervisor
        handle = await supervisor.start("lifespan-project")

        assert app.state.database is database
        assert app.state.worker_supervisor is supervisor
        assert handle.process.returncode is None
        assert (await supervisor.ping(handle.worker_id)).payload == {"status": "ok"}

    assert handle.process.returncode == 0
    assert supervisor.get(handle.worker_id) is None
    assert not hasattr(app.state, "database")
    assert not hasattr(app.state, "worker_supervisor")


@pytest.mark.asyncio
async def test_database_probe_failure_disposes_database_and_leaves_no_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingConnectionContext:
        async def __aenter__(self) -> None:
            raise RuntimeError("database probe failed")

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            del exc_type, exc_value, traceback

    class FailingEngine:
        def connect(self) -> FailingConnectionContext:
            return FailingConnectionContext()

    class FailingProbeDatabase:
        engine = FailingEngine()

        def __init__(self) -> None:
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    database = FailingProbeDatabase()
    monkeypatch.setattr(lifespan_module, "create_database", lambda _: database)
    app = create_app(_settings(tmp_path))

    with pytest.raises(RuntimeError, match="database probe failed"):
        async with app.router.lifespan_context(app):
            pass

    assert database.disposed is True
    assert not hasattr(app.state, "database")
    assert not hasattr(app.state, "worker_supervisor")


@pytest.mark.asyncio
async def test_production_lifespan_does_not_create_database_schema(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        pass

    with sqlite3.connect(settings.database_path) as connection:
        application_tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    assert application_tables == set()


@pytest.mark.asyncio
async def test_supervisor_creation_failure_disposes_database_and_leaves_no_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ProbeConnection:
        async def __aenter__(self) -> "ProbeConnection":
            return self

        async def __aexit__(self, *_: object) -> None:
            pass

        async def execute(self, _: object) -> None:
            pass

    class ProbeEngine:
        def connect(self) -> ProbeConnection:
            return ProbeConnection()

    class TrackingDatabase:
        engine = ProbeEngine()

        def __init__(self) -> None:
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    def fail_supervisor_creation(**_: object) -> None:
        raise RuntimeError("worker supervisor creation failed")

    database = TrackingDatabase()
    monkeypatch.setattr(lifespan_module, "create_database", lambda _: database)
    monkeypatch.setattr(
        lifespan_module,
        "WorkerSupervisor",
        fail_supervisor_creation,
    )
    app = create_app(_settings(tmp_path))

    with pytest.raises(RuntimeError, match="worker supervisor creation failed"):
        async with app.router.lifespan_context(app):
            pass

    assert database.disposed is True
    assert not hasattr(app.state, "database")
    assert not hasattr(app.state, "worker_supervisor")


@pytest.mark.asyncio
async def test_application_lifespan_initializes_resources_in_required_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    events: list[str] = []
    real_ensure_directories = Settings.ensure_directories
    real_probe_database = lifespan_module._probe_database

    def ensure_directories(current_settings: Settings) -> None:
        events.append("ensure_directories")
        real_ensure_directories(current_settings)

    def configure_logging(log_root: Path, level: str) -> None:
        assert log_root == settings.log_root
        assert level == settings.log_level
        events.append("configure_logging")

    def tracked_create_database(path: Path) -> Database:
        assert path == settings.database_path
        events.append("create_database")
        return create_database(path)

    async def probe_database(database: Database) -> None:
        events.append("probe_database")
        await real_probe_database(database)

    def create_worker_supervisor(*, heartbeat_timeout: timedelta) -> WorkerSupervisor:
        assert heartbeat_timeout.total_seconds() == settings.worker_heartbeat_timeout_seconds
        events.append("worker_supervisor")
        return WorkerSupervisor(heartbeat_timeout=heartbeat_timeout)

    monkeypatch.setattr(Settings, "ensure_directories", ensure_directories)
    monkeypatch.setattr(
        lifespan_module,
        "configure_logging",
        configure_logging,
        raising=False,
    )
    monkeypatch.setattr(lifespan_module, "create_database", tracked_create_database)
    monkeypatch.setattr(lifespan_module, "_probe_database", probe_database)
    monkeypatch.setattr(lifespan_module, "WorkerSupervisor", create_worker_supervisor)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        assert hasattr(app.state, "database")
        assert hasattr(app.state, "worker_supervisor")

    assert events == [
        "ensure_directories",
        "configure_logging",
        "create_database",
        "probe_database",
        "worker_supervisor",
    ]


@pytest.mark.asyncio
async def test_worker_watchdog_runs_only_during_application_lifespan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watch_called = asyncio.Event()
    stopped = asyncio.Event()

    class TrackingSupervisor:
        async def watch_once(self) -> None:
            watch_called.set()

        async def stop_all(self) -> None:
            stopped.set()

    supervisor = TrackingSupervisor()
    monkeypatch.setattr(lifespan_module, "WorkerSupervisor", lambda **_: supervisor)
    settings = Settings(
        data_root=tmp_path,
        session_token="local-secret",
        worker_watchdog_interval_seconds=0.01,
    )
    app = create_app(settings)

    assert not hasattr(app.state, "worker_watchdog_task")
    async with app.router.lifespan_context(app):
        watchdog_task = app.state.worker_watchdog_task
        assert watchdog_task.done() is False
        await asyncio.wait_for(watch_called.wait(), timeout=1)

    assert watchdog_task.cancelled()
    assert stopped.is_set()
    assert not hasattr(app.state, "worker_watchdog_task")


@pytest.mark.asyncio
async def test_shutdown_awaits_watchdog_before_workers_and_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    watch_started = asyncio.Event()

    class BlockingSupervisor:
        async def watch_once(self) -> None:
            events.append("watch_once")
            watch_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                events.append("watchdog_cancelled")

        async def stop_all(self) -> None:
            events.append("stop_all")

    database = _TrackingWatchdogDatabase(events)
    supervisor = BlockingSupervisor()
    monkeypatch.setattr(lifespan_module, "create_database", lambda _: database)
    monkeypatch.setattr(lifespan_module, "WorkerSupervisor", lambda **_: supervisor)
    settings = Settings(
        data_root=tmp_path,
        session_token="local-secret",
        worker_watchdog_interval_seconds=0.01,
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(watch_started.wait(), timeout=1)

    assert events == ["watch_once", "watchdog_cancelled", "stop_all", "dispose"]


@pytest.mark.asyncio
async def test_watchdog_failure_remains_primary_and_all_cleanup_still_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watchdog_secret = "watchdog-secret"
    stop_secret = "stop-secret"
    events: list[str] = []
    watch_failed = asyncio.Event()

    class FailingSupervisor:
        async def watch_once(self) -> None:
            events.append("watch_once")
            watch_failed.set()
            raise RuntimeError(watchdog_secret)

        async def stop_all(self) -> None:
            events.append("stop_all")
            raise LookupError(stop_secret)

    database = _TrackingWatchdogDatabase(events)
    supervisor = FailingSupervisor()
    monkeypatch.setattr(lifespan_module, "create_database", lambda _: database)
    monkeypatch.setattr(lifespan_module, "WorkerSupervisor", lambda **_: supervisor)
    settings = Settings(
        data_root=tmp_path,
        session_token="local-secret",
        worker_watchdog_interval_seconds=0.01,
    )
    app = create_app(settings)

    with pytest.raises(RuntimeError, match=watchdog_secret) as raised:
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(watch_failed.wait(), timeout=1)
            await asyncio.sleep(0)

    assert events == ["watch_once", "stop_all", "dispose"]
    assert raised.value.__notes__ == ["Additional cleanup failure occurred."]
    assert stop_secret not in raised.value.__notes__[0]
    assert not hasattr(app.state, "worker_watchdog_task")
    assert not hasattr(app.state, "worker_supervisor")
    assert not hasattr(app.state, "database")
    assert watchdog_secret not in repr(app.state.__dict__)


@pytest.mark.asyncio
async def test_watchdog_startup_failure_stops_supervisor_and_disposes_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class TrackingSupervisor:
        async def stop_all(self) -> None:
            events.append("stop_all")

    def fail_watchdog_start(*_: object) -> None:
        events.append("start_watchdog")
        raise RuntimeError("watchdog startup failed")

    database = _TrackingWatchdogDatabase(events)
    supervisor = TrackingSupervisor()
    monkeypatch.setattr(lifespan_module, "create_database", lambda _: database)
    monkeypatch.setattr(lifespan_module, "WorkerSupervisor", lambda **_: supervisor)
    monkeypatch.setattr(
        lifespan_module,
        "_start_worker_watchdog",
        fail_watchdog_start,
        raising=False,
    )
    app = create_app(_settings(tmp_path))

    with pytest.raises(RuntimeError, match="watchdog startup failed"):
        async with app.router.lifespan_context(app):
            pass

    assert events == ["start_watchdog", "stop_all", "dispose"]
    assert not hasattr(app.state, "worker_watchdog_task")
    assert not hasattr(app.state, "worker_supervisor")
    assert not hasattr(app.state, "database")


@pytest.mark.asyncio
async def test_shutdown_disposes_database_when_worker_stop_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class ProbeConnection:
        async def __aenter__(self) -> "ProbeConnection":
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            del exc_type, exc_value, traceback

        async def execute(self, statement: object) -> None:
            assert str(statement) == "SELECT 1"

    class ProbeEngine:
        def connect(self) -> ProbeConnection:
            return ProbeConnection()

    class TrackingDatabase:
        engine = ProbeEngine()

        async def dispose(self) -> None:
            events.append("dispose")

    class FailingSupervisor:
        async def stop_all(self) -> None:
            events.append("stop_all")
            raise RuntimeError("worker shutdown failed")

    database = TrackingDatabase()
    supervisor = FailingSupervisor()
    monkeypatch.setattr(lifespan_module, "create_database", lambda _: database)
    monkeypatch.setattr(lifespan_module, "WorkerSupervisor", lambda **_: supervisor)
    app = create_app(_settings(tmp_path))

    with pytest.raises(RuntimeError, match="worker shutdown failed"):
        async with app.router.lifespan_context(app):
            pass

    assert events == ["stop_all", "dispose"]
    assert not hasattr(app.state, "database")
    assert not hasattr(app.state, "worker_supervisor")


@pytest.mark.asyncio
async def test_shutdown_preserves_worker_stop_error_when_database_dispose_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ProbeConnection:
        async def __aenter__(self) -> "ProbeConnection":
            return self

        async def __aexit__(self, *_: object) -> None:
            pass

        async def execute(self, _: object) -> None:
            pass

    class ProbeEngine:
        def connect(self) -> ProbeConnection:
            return ProbeConnection()

    class FailingDatabase:
        engine = ProbeEngine()

        async def dispose(self) -> None:
            raise LookupError("database dispose failed")

    class FailingSupervisor:
        async def stop_all(self) -> None:
            raise RuntimeError("worker stop failed")

    database = FailingDatabase()
    supervisor = FailingSupervisor()
    monkeypatch.setattr(lifespan_module, "create_database", lambda _: database)
    monkeypatch.setattr(lifespan_module, "WorkerSupervisor", lambda **_: supervisor)
    app = create_app(_settings(tmp_path))

    with pytest.raises(RuntimeError, match="worker stop failed") as raised:
        async with app.router.lifespan_context(app):
            pass

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert raised.value.__suppress_context__ is False
    assert raised.value.__notes__ == ["Additional cleanup failure occurred."]
    assert not hasattr(app.state, "database")
    assert not hasattr(app.state, "worker_supervisor")


@pytest.mark.asyncio
async def test_lifespan_cancellation_remains_primary_when_shutdown_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposed = False

    class ProbeConnection:
        async def __aenter__(self) -> "ProbeConnection":
            return self

        async def __aexit__(self, *_: object) -> None:
            pass

        async def execute(self, _: object) -> None:
            pass

    class ProbeEngine:
        def connect(self) -> ProbeConnection:
            return ProbeConnection()

    class TrackingDatabase:
        engine = ProbeEngine()

        async def dispose(self) -> None:
            nonlocal disposed
            disposed = True

    class FailingSupervisor:
        async def stop_all(self) -> None:
            raise RuntimeError("worker shutdown failed")

    database = TrackingDatabase()
    supervisor = FailingSupervisor()
    monkeypatch.setattr(lifespan_module, "create_database", lambda _: database)
    monkeypatch.setattr(lifespan_module, "WorkerSupervisor", lambda **_: supervisor)
    app = create_app(_settings(tmp_path))
    entered = asyncio.Event()

    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            entered.set()
            await asyncio.Event().wait()

    lifespan_task = asyncio.create_task(run_lifespan())
    await asyncio.wait_for(entered.wait(), timeout=1)

    lifespan_task.cancel()
    with pytest.raises(asyncio.CancelledError) as raised:
        await lifespan_task

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert raised.value.__suppress_context__ is False
    assert raised.value.__notes__ == ["Additional cleanup failure occurred."]
    assert disposed is True
    assert not hasattr(app.state, "database")
    assert not hasattr(app.state, "worker_supervisor")


@pytest.mark.asyncio
async def test_database_probe_failure_remains_primary_when_dispose_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingConnectionContext:
        async def __aenter__(self) -> None:
            raise LookupError("database probe failed")

        async def __aexit__(self, *_: object) -> None:
            pass

    class FailingEngine:
        def connect(self) -> FailingConnectionContext:
            return FailingConnectionContext()

    class FailingDatabase:
        engine = FailingEngine()

        async def dispose(self) -> None:
            raise RuntimeError("database dispose failed")

    database = FailingDatabase()
    monkeypatch.setattr(lifespan_module, "create_database", lambda _: database)
    app = create_app(_settings(tmp_path))

    with pytest.raises(LookupError, match="database probe failed") as raised:
        async with app.router.lifespan_context(app):
            pass

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert raised.value.__suppress_context__ is False
    assert raised.value.__notes__ == ["Additional cleanup failure occurred."]
    assert not hasattr(app.state, "database")
    assert not hasattr(app.state, "worker_supervisor")


@pytest.mark.asyncio
async def test_cleanup_failure_preserves_primary_explicit_cause_and_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_cause = RuntimeError("original cause")
    original_context = OSError("original context")
    primary_error = LookupError("database probe failed")
    primary_error.__cause__ = original_cause
    primary_error.__context__ = original_context
    primary_error.__suppress_context__ = True

    class FailingConnectionContext:
        async def __aenter__(self) -> None:
            raise primary_error

        async def __aexit__(self, *_: object) -> None:
            pass

    class FailingEngine:
        def connect(self) -> FailingConnectionContext:
            return FailingConnectionContext()

    class FailingDatabase:
        engine = FailingEngine()

        async def dispose(self) -> None:
            raise ValueError("cleanup-secret")

    database = FailingDatabase()
    monkeypatch.setattr(lifespan_module, "create_database", lambda _: database)
    app = create_app(_settings(tmp_path))

    with pytest.raises(LookupError, match="database probe failed") as raised:
        async with app.router.lifespan_context(app):
            pass

    assert raised.value is primary_error
    assert raised.value.__cause__ is original_cause
    assert raised.value.__context__ is original_context
    assert raised.value.__notes__ == ["Additional cleanup failure occurred."]
    assert "ValueError" not in raised.value.__notes__[0]
    assert "cleanup-secret" not in raised.value.__notes__[0]


@pytest.mark.asyncio
async def test_cleanup_failure_preserves_primary_implicit_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_context = OSError("original context")
    primary_error = LookupError("database probe failed")
    primary_error.__context__ = original_context
    primary_error.__suppress_context__ = False

    class FailingConnectionContext:
        async def __aenter__(self) -> None:
            raise primary_error

        async def __aexit__(self, *_: object) -> None:
            pass

    class FailingEngine:
        def connect(self) -> FailingConnectionContext:
            return FailingConnectionContext()

    class FailingDatabase:
        engine = FailingEngine()

        async def dispose(self) -> None:
            raise ValueError("cleanup-secret")

    database = FailingDatabase()
    monkeypatch.setattr(lifespan_module, "create_database", lambda _: database)
    app = create_app(_settings(tmp_path))

    with pytest.raises(LookupError, match="database probe failed") as raised:
        async with app.router.lifespan_context(app):
            pass

    assert raised.value is primary_error
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is original_context
    assert raised.value.__suppress_context__ is False
    assert raised.value.__notes__ == ["Additional cleanup failure occurred."]
    assert "ValueError" not in raised.value.__notes__[0]
    assert "cleanup-secret" not in raised.value.__notes__[0]


def test_cleanup_failure_preserves_empty_primary_chain_and_redacts_secondary() -> None:
    primary_error = RuntimeError("primary failure")
    cleanup_error = LookupError("SECRET_CLEANUP")

    with pytest.raises(RuntimeError, match="primary failure") as raised:
        lifespan_module._raise_primary_with_cleanup_failure(
            primary_error,
            cleanup_error,
        )

    assert raised.value is primary_error
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert raised.value.__suppress_context__ is False
    assert raised.value.__notes__ == ["Additional cleanup failure occurred."]
    assert "SECRET_CLEANUP" not in raised.value.__notes__[0]


def test_cleanup_note_bypasses_overridden_add_note() -> None:
    class OverridingPrimaryError(RuntimeError):
        def add_note(self, note: str) -> None:
            del note
            raise LookupError("note-secret")

    original_cause = OSError("original cause")
    original_context = ValueError("original context")
    primary_error = OverridingPrimaryError("primary failure")
    primary_error.__cause__ = original_cause
    primary_error.__context__ = original_context
    primary_error.__suppress_context__ = True

    with pytest.raises(OverridingPrimaryError, match="primary failure") as raised:
        lifespan_module._raise_primary_with_cleanup_failure(
            primary_error,
            RuntimeError("cleanup-secret"),
        )

    assert raised.value is primary_error
    assert raised.value.__cause__ is original_cause
    assert raised.value.__context__ is original_context
    assert raised.value.__suppress_context__ is True
    assert raised.value.__notes__ == ["Additional cleanup failure occurred."]
    assert "note-secret" not in raised.value.__notes__[0]
    assert "cleanup-secret" not in raised.value.__notes__[0]


def test_cleanup_note_failure_does_not_replace_primary() -> None:
    original_cause = OSError("original cause")
    original_context = ValueError("original context")
    primary_error = RuntimeError("primary failure")
    primary_error.__cause__ = original_cause
    primary_error.__context__ = original_context
    primary_error.__suppress_context__ = True
    primary_error.__dict__["__notes__"] = "invalid notes"

    with pytest.raises(RuntimeError, match="primary failure") as raised:
        lifespan_module._raise_primary_with_cleanup_failure(
            primary_error,
            LookupError("cleanup-secret"),
        )

    assert raised.value is primary_error
    assert raised.value.__cause__ is original_cause
    assert raised.value.__context__ is original_context
    assert raised.value.__suppress_context__ is True
    assert raised.value.__dict__["__notes__"] == "invalid notes"
