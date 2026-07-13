import asyncio
import sys
import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from agent_platform.interfaces.ipc.framing import MAX_BODY_BYTES, FrameDecoder, encode_frame
from agent_platform.interfaces.ipc.messages import IpcMessage
from agent_platform.workers import main as worker_main


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=1)
    except TimeoutError:
        process.kill()
        await process.wait()


async def _start_worker(*extra_args: str) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "agent_platform.workers.main",
        "--project-id",
        "project_1",
        *extra_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def _write_messages(
    process: asyncio.subprocess.Process,
    messages: Sequence[IpcMessage],
) -> None:
    assert process.stdin is not None
    process.stdin.write(b"".join(encode_frame(message) for message in messages))
    await process.stdin.drain()


async def _read_next_message(
    process: asyncio.subprocess.Process,
    decoder: FrameDecoder,
    pending: list[IpcMessage],
) -> IpcMessage:
    assert process.stdout is not None
    while not pending:
        chunk = await asyncio.wait_for(process.stdout.read(65536), timeout=5)
        assert chunk, "worker stdout closed before the next protocol message"
        pending.extend(decoder.feed(chunk))
    return pending.pop(0)


def _decode_complete_output(output: bytes) -> list[IpcMessage]:
    messages = FrameDecoder().feed(output)
    assert output == b"".join(encode_frame(message) for message in messages)
    return messages


async def test_worker_acknowledges_ping_and_completes_shutdown() -> None:
    process = await _start_worker()
    assert process.stdout is not None
    assert process.stderr is not None

    ping = IpcMessage(
        message_id="cmd_1",
        sequence=1,
        project_id="project_1",
        type="command",
        payload={"name": "ping"},
    )
    shutdown = IpcMessage(
        message_id="cmd_2",
        sequence=2,
        project_id="project_1",
        type="shutdown",
    )

    output = bytearray()
    decoder = FrameDecoder()
    messages: list[IpcMessage] = []
    try:
        await _write_messages(process, [ping, shutdown])

        while not (
            any(message.type == "ack" and message.correlation_id == "cmd_1" for message in messages)
            and any(
                message.type == "response" and message.correlation_id == "cmd_2"
                for message in messages
            )
        ):
            chunk = await asyncio.wait_for(process.stdout.read(65536), timeout=5)
            assert chunk, "worker stdout closed before required protocol responses"
            output.extend(chunk)
            messages.extend(decoder.feed(chunk))

        assert await asyncio.wait_for(process.wait(), timeout=5) == 0
        trailing_output = await process.stdout.read()
        output.extend(trailing_output)
        messages.extend(decoder.feed(trailing_output))
        stderr = await process.stderr.read()
    finally:
        await _terminate_process(process)

    ping_ack = next(
        message
        for message in messages
        if message.type == "ack" and message.correlation_id == "cmd_1"
    )
    shutdown_response = next(
        message
        for message in messages
        if message.type == "response" and message.correlation_id == "cmd_2"
    )
    assert ping_ack.project_id == "project_1"
    assert ping_ack.payload == {"status": "ok"}
    assert shutdown_response.project_id == "project_1"
    assert shutdown_response.payload == {"status": "shutdown_complete"}
    assert bytes(output) == b"".join(encode_frame(message) for message in messages)
    assert b"Content-Length" not in stderr
    assert b'"message_id":"cmd_1"' not in stderr


async def test_worker_sends_heartbeat_after_interval_with_first_sequence() -> None:
    process = await _start_worker("--heartbeat-interval", "0.25")
    assert process.stdout is not None
    decoder = FrameDecoder()
    pending: list[IpcMessage] = []
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(process.stdout.read(1), timeout=0.05)
        heartbeat = await _read_next_message(process, decoder, pending)
        await _write_messages(
            process,
            [
                IpcMessage(
                    message_id="shutdown_heartbeat",
                    sequence=1,
                    project_id="project_1",
                    type="shutdown",
                )
            ],
        )
        shutdown_response = await _read_next_message(process, decoder, pending)
        assert await asyncio.wait_for(process.wait(), timeout=5) == 0
    finally:
        await _terminate_process(process)

    assert heartbeat.type == "heartbeat"
    assert heartbeat.sequence == 1
    assert heartbeat.message_id.startswith("msg_")
    assert heartbeat.payload["worker_id"].startswith("worker_")
    assert heartbeat.payload["active_task"] is None
    assert heartbeat.payload["last_sequence"] == 0
    assert shutdown_response.type == "response"
    assert shutdown_response.sequence == 2


async def test_worker_heartbeat_uses_injected_worker_id() -> None:
    process = await _start_worker(
        "--worker-id",
        "worker_canonical",
        "--heartbeat-interval",
        "0.05",
    )
    decoder = FrameDecoder()
    pending: list[IpcMessage] = []
    try:
        heartbeat = await _read_next_message(process, decoder, pending)
    finally:
        await _terminate_process(process)

    assert heartbeat.type == "heartbeat"
    assert heartbeat.payload["worker_id"] == "worker_canonical"


async def test_worker_acknowledges_cancel_as_cancelled() -> None:
    process = await _start_worker("--heartbeat-interval", "60")
    decoder = FrameDecoder()
    pending: list[IpcMessage] = []
    try:
        await _write_messages(
            process,
            [
                IpcMessage(
                    message_id="cancel_1",
                    sequence=1,
                    project_id="project_1",
                    type="cancel",
                ),
                IpcMessage(
                    message_id="shutdown_cancel",
                    sequence=2,
                    project_id="project_1",
                    type="shutdown",
                ),
            ],
        )
        cancel_ack = await _read_next_message(process, decoder, pending)
        await asyncio.wait_for(process.wait(), timeout=5)
    finally:
        await _terminate_process(process)

    assert cancel_ack.type == "ack"
    assert cancel_ack.correlation_id == "cancel_1"
    assert cancel_ack.payload == {"status": "cancelled"}


async def test_worker_rejects_project_mismatch_without_processing_message() -> None:
    process = await _start_worker("--heartbeat-interval", "60")
    decoder = FrameDecoder()
    pending: list[IpcMessage] = []
    try:
        await _write_messages(
            process,
            [
                IpcMessage(
                    message_id="wrong_shutdown",
                    sequence=1,
                    project_id="project_2",
                    type="shutdown",
                ),
                IpcMessage(
                    message_id="ping_after_mismatch",
                    sequence=2,
                    project_id="project_1",
                    type="command",
                    payload={"name": "ping"},
                ),
                IpcMessage(
                    message_id="shutdown_after_mismatch",
                    sequence=3,
                    project_id="project_1",
                    type="shutdown",
                ),
            ],
        )
        mismatch_response = await _read_next_message(process, decoder, pending)
        ping_ack = await _read_next_message(process, decoder, pending)
        shutdown_response = await _read_next_message(process, decoder, pending)
        assert await asyncio.wait_for(process.wait(), timeout=5) == 0
    finally:
        await _terminate_process(process)

    assert mismatch_response.correlation_id == "wrong_shutdown"
    assert mismatch_response.payload == {"status": "project_mismatch"}
    assert ping_ack.correlation_id == "ping_after_mismatch"
    assert ping_ack.payload == {"status": "ok"}
    assert shutdown_response.correlation_id == "shutdown_after_mismatch"


async def test_worker_invalid_frame_exits_two_without_leaking_input() -> None:
    marker = b"SECRET_INVALID_FRAME"
    body = b'{"secret":"' + marker + b'"}'
    invalid_frame = (
        f"Content-Length: {len(body)}\r\nProtocol-Version: 1\r\n".encode()
        + b"X-Secret: "
        + marker
        + b"\r\n\r\n"
        + body
    )
    process = await _start_worker("--heartbeat-interval", "60")
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(invalid_frame), timeout=5)
    finally:
        await _terminate_process(process)

    assert process.returncode == 2
    assert _decode_complete_output(stdout) == []
    assert marker not in stderr
    assert b"Content-Length" not in stderr
    assert body not in stderr


async def test_worker_partial_frame_at_eof_exits_two_without_leaking_input() -> None:
    marker = b"SECRET_PARTIAL_FRAME"
    partial_frame = b"Content-Length: 100\r\nProtocol-Version: 1\r\n\r\n" + marker
    process = await _start_worker("--heartbeat-interval", "60")
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(partial_frame), timeout=5)
    finally:
        await _terminate_process(process)

    assert process.returncode == 2
    assert _decode_complete_output(stdout) == []
    assert marker not in stderr
    assert b"Content-Length" not in stderr


async def test_worker_oversized_outbound_ack_exits_one_as_internal_error() -> None:
    marker = "SECRET_OVERSIZED_ACK_"
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    template = IpcMessage(
        message_id=marker,
        sequence=1,
        project_id="project_1",
        type="command",
        timestamp=timestamp,
        payload={"name": "ping"},
    )
    template_body = encode_frame(template).partition(b"\r\n\r\n")[2]
    ping = IpcMessage(
        message_id=marker + ("x" * (MAX_BODY_BYTES - len(template_body))),
        sequence=1,
        project_id="project_1",
        type="command",
        timestamp=timestamp,
        payload={"name": "ping"},
    )
    frame = encode_frame(ping)
    assert len(frame.partition(b"\r\n\r\n")[2]) == MAX_BODY_BYTES

    process = await _start_worker("--heartbeat-interval", "60")
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(frame), timeout=5)
    finally:
        await _terminate_process(process)

    assert process.returncode == 1
    assert stdout == b""
    assert stderr.splitlines() == [b"worker internal error: FramingError"]
    assert marker.encode() not in stderr
    assert b"Traceback" not in stderr


async def test_worker_clean_eof_exits_zero_without_orphan_heartbeat() -> None:
    process = await _start_worker("--heartbeat-interval", "0.05")
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(b""), timeout=5)
    finally:
        await _terminate_process(process)

    assert process.returncode == 0
    assert stdout == b""
    assert stderr == b""


async def test_worker_output_sequence_is_monotonic_when_heartbeat_and_commands_interleave() -> None:
    process = await _start_worker("--heartbeat-interval", "0.02")
    decoder = FrameDecoder()
    pending: list[IpcMessage] = []
    received: list[IpcMessage] = []
    ping_ids = {f"interleaved_ping_{index}" for index in range(8)}
    try:
        received.append(await _read_next_message(process, decoder, pending))
        await _write_messages(
            process,
            [
                IpcMessage(
                    message_id=message_id,
                    sequence=index + 1,
                    project_id="project_1",
                    type="command",
                    payload={"name": "ping"},
                )
                for index, message_id in enumerate(sorted(ping_ids))
            ],
        )
        while not (
            ping_ids <= {message.correlation_id for message in received if message.type == "ack"}
            and any(
                message.type == "heartbeat" and message.payload["last_sequence"] == 8
                for message in received
            )
        ):
            received.append(await _read_next_message(process, decoder, pending))

        await _write_messages(
            process,
            [
                IpcMessage(
                    message_id="shutdown_interleaved",
                    sequence=9,
                    project_id="project_1",
                    type="shutdown",
                )
            ],
        )
        while not any(message.correlation_id == "shutdown_interleaved" for message in received):
            received.append(await _read_next_message(process, decoder, pending))
        assert await asyncio.wait_for(process.wait(), timeout=5) == 0
    finally:
        await _terminate_process(process)

    assert [message.sequence for message in received] == list(range(1, len(received) + 1))
    assert len({message.message_id for message in received}) == len(received)
    assert all(message.message_id.startswith("msg_") for message in received)


async def test_worker_keeps_newline_and_unicode_payload_inside_frames() -> None:
    payload_marker = "你好\nContent-Length: 999\r\nSECRET_PAYLOAD_MARKER"
    ping = IpcMessage(
        message_id="unicode_ping",
        sequence=1,
        project_id="project_1",
        type="command",
        payload={"name": "ping", "text": payload_marker},
    )
    shutdown = IpcMessage(
        message_id="shutdown_unicode",
        sequence=2,
        project_id="project_1",
        type="shutdown",
    )
    process = await _start_worker("--heartbeat-interval", "60")
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(encode_frame(ping) + encode_frame(shutdown)),
            timeout=5,
        )
    finally:
        await _terminate_process(process)

    messages = _decode_complete_output(stdout)
    assert process.returncode == 0
    assert [message.correlation_id for message in messages] == [
        "unicode_ping",
        "shutdown_unicode",
    ]
    assert payload_marker.encode() not in stdout
    assert stderr == b""


async def test_worker_acknowledges_unknown_command_as_unsupported() -> None:
    unknown_command = IpcMessage(
        message_id="unknown_command",
        sequence=1,
        project_id="project_1",
        type="command",
        payload={"name": "not_supported", "secret": "DO_NOT_LOG_UNKNOWN_COMMAND"},
    )
    shutdown = IpcMessage(
        message_id="shutdown_unknown_command",
        sequence=2,
        project_id="project_1",
        type="shutdown",
    )
    process = await _start_worker("--heartbeat-interval", "60")
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(encode_frame(unknown_command) + encode_frame(shutdown)),
            timeout=5,
        )
    finally:
        await _terminate_process(process)

    messages = _decode_complete_output(stdout)
    assert messages[0].type == "ack"
    assert messages[0].correlation_id == "unknown_command"
    assert messages[0].payload == {"status": "unsupported"}
    assert stderr == b""


async def test_worker_responds_to_unexpected_message_type_as_unsupported() -> None:
    unexpected = IpcMessage(
        message_id="unexpected_event",
        sequence=1,
        project_id="project_1",
        type="event",
        payload={"secret": "DO_NOT_LOG_UNEXPECTED_EVENT"},
    )
    shutdown = IpcMessage(
        message_id="shutdown_unexpected_event",
        sequence=2,
        project_id="project_1",
        type="shutdown",
    )
    process = await _start_worker("--heartbeat-interval", "60")
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(encode_frame(unexpected) + encode_frame(shutdown)),
            timeout=5,
        )
    finally:
        await _terminate_process(process)

    messages = _decode_complete_output(stdout)
    assert messages[0].type == "response"
    assert messages[0].correlation_id == "unexpected_event"
    assert messages[0].payload == {"status": "unsupported"}
    assert stderr == b""


@pytest.mark.parametrize(
    "project_id",
    ["", "project_\nSECRET_PROJECT_ID", "项目_SECRET_PROJECT_ID"],
)
async def test_worker_rejects_invalid_project_id_without_echoing_value(project_id: str) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "agent_platform.workers.main",
        "--project-id",
        project_id,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(b""), timeout=5)
    finally:
        await _terminate_process(process)

    assert process.returncode == 2
    assert stdout == b""
    if project_id:
        assert project_id.encode() not in stderr


@pytest.mark.parametrize(
    "args",
    [
        ("--project-id", "project_1", "--bogus", "SECRET_UNKNOWN_ARG"),
        (),
    ],
)
async def test_worker_argument_errors_use_fixed_safe_diagnostic(args: tuple[str, ...]) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "agent_platform.workers.main",
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(b""), timeout=5)
    finally:
        await _terminate_process(process)

    assert process.returncode == 2
    assert stdout == b""
    assert stderr.splitlines() == [b"worker argument error"]
    assert b"usage:" not in stderr
    assert b"--bogus" not in stderr
    assert b"--project-id" not in stderr
    assert b"SECRET_UNKNOWN_ARG" not in stderr


async def test_worker_help_never_writes_unframed_stdout() -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "agent_platform.workers.main",
        "--help",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(b""), timeout=5)
    finally:
        await _terminate_process(process)

    assert process.returncode == 0
    assert stdout == b""
    assert b"usage:" in stderr


async def test_worker_two_cancellations_keep_writer_lock_until_thread_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_writer_entered = threading.Event()
    second_writer_entered = threading.Event()
    release_first_writer = threading.Event()
    call_lock = threading.Lock()
    call_count = 0
    written_frames: list[bytes] = []

    def blocking_writer(frame: bytes) -> None:
        nonlocal call_count
        with call_lock:
            call_count += 1
            current_call = call_count
            written_frames.append(frame)
        if current_call == 1:
            first_writer_entered.set()
            release_first_writer.wait(timeout=5)
        else:
            second_writer_entered.set()

    monkeypatch.setattr(worker_main, "_write_stdout", blocking_writer)
    worker = worker_main._WorkerProtocol("project_1", 60)
    first_send = asyncio.create_task(worker._send("ack", {"status": "first"}))
    assert await asyncio.to_thread(first_writer_entered.wait, 1)

    first_send.cancel()
    await asyncio.sleep(0)
    second_send = asyncio.create_task(worker._send("ack", {"status": "second"}))
    first_send.cancel()
    await asyncio.sleep(0)
    assert first_send.cancelling() == 2
    try:
        assert not await asyncio.to_thread(second_writer_entered.wait, 0.1)
    finally:
        release_first_writer.set()
        results = await asyncio.gather(first_send, second_send, return_exceptions=True)

    assert isinstance(results[0], asyncio.CancelledError)
    assert results[1] is None
    assert second_writer_entered.is_set()
    messages = _decode_complete_output(b"".join(written_frames))
    assert [message.sequence for message in messages] == [1, 2]
    assert [message.payload for message in messages] == [
        {"status": "first"},
        {"status": "second"},
    ]


async def test_worker_broken_stdout_exits_one_without_shutdown_diagnostic() -> None:
    marker = b"SECRET_BROKEN_STDOUT"
    process = await _start_worker("--heartbeat-interval", "60")
    assert process.stdin is not None
    assert process.stderr is not None
    try:
        process_transport = cast(Any, process)._transport
        process_transport.get_pipe_transport(1).close()
        await asyncio.sleep(0.1)
        ping = IpcMessage(
            message_id="broken_stdout_ping",
            sequence=1,
            project_id="project_1",
            type="command",
            payload={"name": "ping", "secret": marker.decode()},
        )
        process.stdin.write(encode_frame(ping))
        try:
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        returncode = await asyncio.wait_for(process.wait(), timeout=5)
        stderr = await process.stderr.read()
    finally:
        await _terminate_process(process)

    assert returncode == 1
    assert stderr.splitlines() in [
        [b"worker internal error: BrokenPipeError"],
        [b"worker internal error: OSError"],
    ]
    assert b"Exception ignored" not in stderr
    assert b"Traceback" not in stderr
    assert b"Content-Length" not in stderr
    assert marker not in stderr


async def test_worker_heartbeat_failure_exits_one_while_stdin_remains_open() -> None:
    process = await _start_worker("--heartbeat-interval", "0.05")
    assert process.stdin is not None
    assert process.stderr is not None
    wait_task = asyncio.create_task(process.wait())
    try:
        process_transport = cast(Any, process)._transport
        process_transport.get_pipe_transport(1).close()
        returncode = await asyncio.wait_for(asyncio.shield(wait_task), timeout=2)
        stderr = await process.stderr.read()
    finally:
        await _terminate_process(process)
        await wait_task

    assert returncode == 1
    assert stderr.splitlines() in [
        [b"worker internal error: BrokenPipeError"],
        [b"worker internal error: OSError"],
    ]
    assert b"Exception ignored" not in stderr
    assert b"Traceback" not in stderr
    assert b"project_1" not in stderr
