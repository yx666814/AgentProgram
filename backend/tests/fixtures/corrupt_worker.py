import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.parse_args()
    if not os.read(sys.stdin.buffer.fileno(), 1):
        return 0
    sys.stdout.buffer.write(b"Content-Length: 2\r\nProtocol-Version: 1\r\nX-Invalid: 1\r\n\r\n{}")
    sys.stdout.buffer.flush()
    while os.read(sys.stdin.buffer.fileno(), 65536):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
