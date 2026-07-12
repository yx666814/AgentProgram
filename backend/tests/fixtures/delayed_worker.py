import argparse
import os
import sys
import time

from agent_platform.domain.shared.ids import new_id
from agent_platform.interfaces.ipc.framing import FrameDecoder, encode_frame
from agent_platform.interfaces.ipc.messages import IpcMessage


def _write(message: IpcMessage) -> None:
    sys.stdout.buffer.write(encode_frame(message))
    sys.stdout.buffer.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()
    decoder = FrameDecoder()
    sequence = 0

    while chunk := os.read(sys.stdin.buffer.fileno(), 65536):
        for message in decoder.feed(chunk):
            sequence += 1
            if message.type == "shutdown":
                _write(
                    IpcMessage(
                        message_id=new_id("msg"),
                        correlation_id=message.message_id,
                        sequence=sequence,
                        project_id=args.project_id,
                        type="response",
                        payload={"status": "shutdown_complete"},
                    )
                )
                return 0
            time.sleep(0.2)
            _write(
                IpcMessage(
                    message_id=new_id("msg"),
                    correlation_id=message.message_id,
                    sequence=sequence,
                    project_id=args.project_id,
                    type="ack",
                    payload={"status": "late"},
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
