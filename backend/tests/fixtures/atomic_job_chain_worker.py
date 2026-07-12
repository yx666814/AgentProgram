import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def atomic_job_chain_paths(project_id: str) -> tuple[Path, Path]:
    base = Path(tempfile.gettempdir()) / f"agent-platform-{project_id}"
    return (
        base.with_suffix(".atomic-target-chain.pid"),
        base.with_suffix(".atomic-child-interpreter.pid"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--worker-id", required=True)
    args = parser.parse_args()
    target_path, child_interpreter_path = atomic_job_chain_paths(args.project_id)
    child = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-c",
            (
                "import os, pathlib, sys, time; "
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii'); "
                "time.sleep(60)"
            ),
            str(child_interpreter_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    target_path.write_text(f"{os.getpid()}|{child.pid}", encoding="ascii")
    while os.read(sys.stdin.buffer.fileno(), 65536):
        pass
