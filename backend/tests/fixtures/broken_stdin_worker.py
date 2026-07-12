import argparse
import os
import sys
import time

from agent_platform.domain.shared.ids import new_id
from agent_platform.interfaces.ipc.framing import encode_frame
from agent_platform.interfaces.ipc.messages import IpcMessage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--worker-id", required=True)
    args = parser.parse_args()
    os.close(sys.stdin.buffer.fileno())
    sys.stdout.buffer.write(
        encode_frame(
            IpcMessage(
                message_id=new_id("msg"),
                sequence=1,
                project_id=args.project_id,
                type="heartbeat",
                payload={
                    "worker_id": args.worker_id,
                    "active_task": None,
                    "last_sequence": 0,
                },
            )
        )
    )
    sys.stdout.buffer.flush()
    time.sleep(60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
