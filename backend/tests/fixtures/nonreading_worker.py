import argparse
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.parse_args()
    time.sleep(60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
