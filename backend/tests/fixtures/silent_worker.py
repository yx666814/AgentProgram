import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.parse_args()
    while sys.stdin.buffer.read(65536):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
