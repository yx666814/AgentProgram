import argparse
import json
import os
import sys

from agent_platform.domain.shared.ids import new_id
from agent_platform.interfaces.ipc.framing import FrameDecoder, encode_frame
from agent_platform.interfaces.ipc.messages import IpcMessage


def _write(*messages: IpcMessage) -> None:
    sys.stdout.buffer.write(b"".join(encode_frame(message) for message in messages))
    sys.stdout.buffer.flush()


def _write_raw(message: dict[str, object]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode()
    header = f"Content-Length: {len(body)}\r\nProtocol-Version: 1\r\n\r\n".encode()
    sys.stdout.buffer.write(header + body)
    sys.stdout.buffer.flush()


def _heartbeat_payload(mode: str, worker_id: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "worker_id": worker_id,
        "active_task": None,
        "last_sequence": 0,
    }
    if mode == "heartbeat_forged":
        payload["worker_id"] = "worker_forged"
    elif mode == "heartbeat_bool":
        payload["last_sequence"] = True
    elif mode == "heartbeat_empty_task":
        payload["active_task"] = ""
    elif mode == "heartbeat_future":
        payload["last_sequence"] = 2
    elif mode == "heartbeat_secret":
        payload["secret"] = "SECRET_HEARTBEAT_PAYLOAD"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--worker-id", required=True)
    args = parser.parse_args()
    mode = args.project_id.removeprefix("project_")
    decoder = FrameDecoder()
    request_count = 0

    if mode == "heartbeat_repeat":
        _write(
            IpcMessage(
                message_id="heartbeat_reused",
                sequence=1,
                project_id=args.project_id,
                type="heartbeat",
                payload=_heartbeat_payload(mode, args.worker_id),
            )
        )

    while chunk := os.read(sys.stdin.buffer.fileno(), 65536):
        for message in decoder.feed(chunk):
            if message.type == "shutdown":
                shutdown_sequence = {
                    "response_replay": 2,
                    "response_skipped": 3,
                    "heartbeat_repeat": 3,
                }.get(mode, 3)
                _write(
                    IpcMessage(
                        message_id=new_id("msg"),
                        correlation_id=message.message_id,
                        sequence=shutdown_sequence,
                        project_id=args.project_id,
                        type="response",
                        payload={"status": "shutdown_complete"},
                    )
                )
                return 0

            request_count += 1
            if mode == "response_replay":
                _write(
                    IpcMessage(
                        message_id="response_reused",
                        correlation_id=message.message_id,
                        sequence=1,
                        project_id=args.project_id,
                        type="ack",
                        payload={"status": f"response_{request_count}"},
                    )
                )
                continue
            if mode == "response_skipped":
                _write(
                    IpcMessage(
                        message_id=new_id("msg"),
                        correlation_id=message.message_id,
                        sequence=2,
                        project_id=args.project_id,
                        type="ack",
                        payload={"status": "skipped"},
                    )
                )
                continue

            if mode == "heartbeat_top_level_extra":
                _write_raw(
                    {
                        "message_id": new_id("msg"),
                        "sequence": 1,
                        "project_id": args.project_id,
                        "type": "heartbeat",
                        "payload": _heartbeat_payload(mode, args.worker_id),
                        "unexpected": "SECRET_UNKNOWN_TOP_LEVEL_FIELD",
                    }
                )
                continue

            if mode == "response_top_level_extra":
                _write_raw(
                    {
                        "message_id": new_id("msg"),
                        "correlation_id": message.message_id,
                        "sequence": 1,
                        "project_id": args.project_id,
                        "type": "ack",
                        "payload": {"status": "must_not_resolve"},
                        "unexpected": "SECRET_UNKNOWN_TOP_LEVEL_FIELD",
                    }
                )
                continue

            heartbeat = IpcMessage(
                message_id="heartbeat_reused" if mode == "heartbeat_repeat" else new_id("msg"),
                sequence=1,
                project_id=args.project_id,
                type="heartbeat",
                payload=_heartbeat_payload(mode, args.worker_id),
            )
            response = IpcMessage(
                message_id=new_id("msg"),
                correlation_id=message.message_id,
                sequence=2,
                project_id=args.project_id,
                type="ack",
                payload={"status": "accepted_invalid_heartbeat"},
            )
            _write(heartbeat, response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
