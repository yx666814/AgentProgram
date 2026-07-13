import sys

from agent_platform.workers.main import main as worker_main


def main() -> int:
    sys.stderr.buffer.write(b"x" * (2 * 1024 * 1024))
    sys.stderr.buffer.flush()
    return worker_main()


if __name__ == "__main__":
    raise SystemExit(main())
