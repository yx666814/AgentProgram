import argparse
import os
import subprocess
import sys

from agent_platform.domain.shared.ids import new_id
from agent_platform.interfaces.ipc.framing import FrameDecoder, encode_frame
from agent_platform.interfaces.ipc.messages import IpcMessage
from tests.fixtures.child_worker import child_pid_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--worker-id")
    args = parser.parse_args()
    decoder = FrameDecoder()
    heartbeat = IpcMessage(
        message_id=new_id("msg"),
        sequence=1,
        project_id=args.project_id,
        type="heartbeat",
        payload={
            "worker_id": args.worker_id or "fixture_worker",
            "active_task": None,
            "last_sequence": 0,
        },
    )
    sys.stdout.buffer.write(encode_frame(heartbeat))
    sys.stdout.buffer.flush()

    while chunk := os.read(sys.stdin.buffer.fileno(), 65536):
        for message in decoder.feed(chunk):
            if message.type != "shutdown":
                continue
            child = subprocess.Popen(  # noqa: S603
                [sys.executable, "-c", "import time; time.sleep(60)"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            child_pid_path(args.project_id).write_text(str(child.pid), encoding="ascii")
            response = IpcMessage(
                message_id=new_id("msg"),
                correlation_id=message.message_id,
                sequence=2,
                project_id=args.project_id,
                type="response",
                payload={"status": "shutdown_complete"},
            )
            sys.stdout.buffer.write(encode_frame(response))
            sys.stdout.buffer.flush()
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
