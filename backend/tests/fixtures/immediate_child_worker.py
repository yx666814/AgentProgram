import argparse
import os
import subprocess
import sys

from tests.fixtures.child_worker import child_pid_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--worker-id", required=True)
    args = parser.parse_args()
    child = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    child_pid_path(args.project_id).write_text(str(child.pid), encoding="ascii")
    while os.read(sys.stdin.buffer.fileno(), 65536):
        pass
