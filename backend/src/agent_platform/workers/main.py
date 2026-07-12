import argparse
import asyncio
import math
import os
import sys
import threading
from collections.abc import Sequence
from typing import Any, Never

from agent_platform.domain.shared.ids import new_id
from agent_platform.interfaces.ipc.framing import FrameDecoder, FramingError, encode_frame
from agent_platform.interfaces.ipc.messages import IpcMessage, MessageType


class _StderrArgumentParser(argparse.ArgumentParser):
    def print_help(self, file: Any = None) -> None:
        super().print_help(file=sys.stderr if file is None else file)

    def error(self, message: str) -> Never:
        del message
        self.exit(2, "worker argument error\n")


class _WorkerInputProtocolError(Exception):
    pass


def _project_id(value: str) -> str:
    if not value or not value.isascii() or not value.isprintable():
        raise argparse.ArgumentTypeError("must be nonempty printable ASCII")
    return value


def _heartbeat_interval(value: str) -> float:
    try:
        interval = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive finite number") from None
    if not math.isfinite(interval) or interval <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return interval


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _StderrArgumentParser(description="Run one isolated project worker")
    parser.add_argument("--project-id", required=True, type=_project_id)
    parser.add_argument("--worker-id", type=_project_id)
    parser.add_argument("--heartbeat-interval", type=_heartbeat_interval, default=5.0)
    return parser.parse_args(argv)


def _write_stdout(frame: bytes) -> None:
    written = sys.stdout.buffer.write(frame)
    if written != len(frame):
        raise OSError("incomplete worker protocol write")
    sys.stdout.buffer.flush()


def _safe_stderr(category: str, exception_type: type[BaseException]) -> None:
    sys.stderr.write(f"worker {category}: {exception_type.__name__}\n")
    sys.stderr.flush()


def _redirect_stdout_to_devnull() -> None:
    devnull_fd: int | None = None
    try:
        stdout_fd = sys.stdout.fileno()
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        if devnull_fd == stdout_fd:
            devnull_fd = None
        else:
            os.dup2(devnull_fd, stdout_fd)
        sys.stdout.flush()
    except Exception:
        pass
    finally:
        if devnull_fd is not None:
            try:
                os.close(devnull_fd)
            except OSError:
                pass


class _DaemonStdinReader:
    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[bytes | Exception] = asyncio.Queue()
        self._read_requests = threading.Semaphore(0)
        self._stdin_fd = sys.stdin.buffer.fileno()
        self._thread = threading.Thread(
            target=self._read_chunks,
            name="worker-stdin-reader",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    async def read(self) -> bytes:
        self._read_requests.release()
        result = await self._queue.get()
        if isinstance(result, Exception):
            raise result
        return result

    def _publish(self, result: bytes | Exception) -> None:
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, result)
        except RuntimeError:
            pass

    def _read_chunks(self) -> None:
        try:
            while True:
                self._read_requests.acquire()
                chunk = os.read(self._stdin_fd, 65536)
                self._publish(chunk)
                if not chunk:
                    return
        except Exception as error:
            self._publish(error)


class _WorkerProtocol:
    def __init__(
        self,
        project_id: str,
        heartbeat_interval: float,
        worker_id: str | None = None,
    ) -> None:
        self._project_id = project_id
        self._heartbeat_interval = heartbeat_interval
        self._worker_id = worker_id or new_id("worker")
        self._outbound_sequence = 0
        self._last_input_sequence = 0
        self._write_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def _send(
        self,
        message_type: MessageType,
        payload: dict[str, object],
        *,
        correlation_id: str | None = None,
    ) -> None:
        async with self._write_lock:
            self._outbound_sequence += 1
            message = IpcMessage(
                message_id=new_id("msg"),
                correlation_id=correlation_id,
                sequence=self._outbound_sequence,
                project_id=self._project_id,
                type=message_type,
                payload=payload,
            )
            frame = encode_frame(message)
            write_task = asyncio.create_task(asyncio.to_thread(_write_stdout, frame))
            try:
                await asyncio.shield(write_task)
            except asyncio.CancelledError:
                while not write_task.done():
                    try:
                        await asyncio.shield(write_task)
                    except asyncio.CancelledError:
                        continue
                try:
                    write_task.result()
                except Exception:
                    pass
                raise

    async def _send_heartbeats(self) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            await self._send(
                "heartbeat",
                {
                    "worker_id": self._worker_id,
                    "active_task": None,
                    "last_sequence": self._last_input_sequence,
                },
            )

    async def _stop_heartbeat(self) -> None:
        task = self._heartbeat_task
        if task is None:
            return
        self._heartbeat_task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _handle_message(self, message: IpcMessage) -> bool:
        if message.project_id != self._project_id:
            await self._send(
                "response",
                {"status": "project_mismatch"},
                correlation_id=message.message_id,
            )
            return False

        self._last_input_sequence = message.sequence
        if message.type == "shutdown":
            await self._stop_heartbeat()
            await self._send(
                "response",
                {"status": "shutdown_complete"},
                correlation_id=message.message_id,
            )
            return True
        if message.type == "cancel":
            await self._send(
                "ack",
                {"status": "cancelled"},
                correlation_id=message.message_id,
            )
            return False
        if message.type == "command" and message.payload.get("name") == "ping":
            await self._send(
                "ack",
                {"status": "ok"},
                correlation_id=message.message_id,
            )
            return False
        if message.type == "command":
            await self._send(
                "ack",
                {"status": "unsupported"},
                correlation_id=message.message_id,
            )
            return False

        await self._send(
            "response",
            {"status": "unsupported"},
            correlation_id=message.message_id,
        )
        return False

    async def _read_stdin_or_raise_heartbeat_failure(
        self,
        reader: _DaemonStdinReader,
    ) -> bytes:
        heartbeat_task = self._heartbeat_task
        if heartbeat_task is None:
            raise RuntimeError("heartbeat task is unavailable")
        read_task = asyncio.create_task(reader.read())
        try:
            done, _ = await asyncio.wait(
                (read_task, heartbeat_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                await heartbeat_task
                raise RuntimeError("heartbeat task stopped unexpectedly")
            return read_task.result()
        finally:
            if not read_task.done():
                read_task.cancel()
                try:
                    await read_task
                except asyncio.CancelledError:
                    pass

    async def run(self) -> int:
        decoder = FrameDecoder()
        reader = _DaemonStdinReader()
        self._heartbeat_task = asyncio.create_task(self._send_heartbeats())
        try:
            reader.start()
            while True:
                chunk = await self._read_stdin_or_raise_heartbeat_failure(reader)
                if not chunk:
                    if decoder._buffer or decoder._expected_body_length is not None:
                        raise _WorkerInputProtocolError
                    return 0
                try:
                    messages = decoder.feed(chunk)
                except FramingError:
                    raise _WorkerInputProtocolError from None
                for message in messages:
                    if await self._handle_message(message):
                        return 0
        finally:
            await self._stop_heartbeat()


async def _run(
    project_id: str,
    heartbeat_interval: float,
    worker_id: str | None = None,
) -> int:
    try:
        return await _WorkerProtocol(project_id, heartbeat_interval, worker_id).run()
    except _WorkerInputProtocolError:
        _safe_stderr("protocol error", FramingError)
        return 2
    except asyncio.CancelledError:
        raise
    except Exception as error:
        _redirect_stdout_to_devnull()
        _safe_stderr("internal error", type(error))
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_run(args.project_id, args.heartbeat_interval, args.worker_id))


if __name__ == "__main__":
    raise SystemExit(main())
