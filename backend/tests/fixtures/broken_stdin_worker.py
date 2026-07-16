import argparse
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
    sys.stdin.close()
    # Let Windows publish the closed read end before the readiness heartbeat.
    # The process then exits so the supervisor observes EOF rather than a
    # platform-specific buffered write into an already-closed pipe.
    time.sleep(0.25)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
