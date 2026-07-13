import argparse
import tempfile
from pathlib import Path


def marker_path(project_id: str) -> Path:
    return Path(tempfile.gettempdir()) / f"agent-platform-{project_id}.import.marker"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--worker-id", required=True)
    args = parser.parse_args()
    marker_path(args.project_id).write_text(
        f"{args.project_id}|{args.worker_id}",
        encoding="ascii",
    )
