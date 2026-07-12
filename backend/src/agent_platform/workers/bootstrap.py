import argparse
import os
import re
import runpy
import sys
from typing import Never

from agent_platform.infrastructure.workers.windows_job import wait_for_windows_start_gate

_TARGET_MODULE_PATTERN = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
_BOOTSTRAP_ERROR = b"worker bootstrap error\n"


class _SilentArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise ValueError("invalid bootstrap arguments")


def _parse_args(argv: list[str] | None) -> tuple[str, str, list[str]]:
    parser = _SilentArgumentParser(add_help=False)
    parser.add_argument("--start-gate", required=True)
    parser.add_argument("--target-module", required=True)
    parser.add_argument("target_argv", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    target_module = str(args.target_module)
    if _TARGET_MODULE_PATTERN.fullmatch(target_module) is None:
        raise ValueError("invalid target module")
    target_argv = list(args.target_argv)
    if target_argv[:1] == ["--"]:
        target_argv = target_argv[1:]
    return str(args.start_gate), target_module, target_argv


def _write_safe_error() -> None:
    try:
        os.write(sys.stderr.fileno(), _BOOTSTRAP_ERROR)
    except OSError:
        pass


def _run_target(target_module: str, target_argv: list[str]) -> None:
    original_argv = sys.argv
    sys.argv = [target_module, *target_argv]
    try:
        runpy.run_module(target_module, run_name="__main__", alter_sys=True)
    finally:
        sys.argv = original_argv


def main(argv: list[str] | None = None) -> int:
    try:
        start_gate, target_module, target_argv = _parse_args(argv)
        wait_for_windows_start_gate(start_gate)
    except BaseException:
        _write_safe_error()
        return 1

    try:
        _run_target(target_module, target_argv)
    except SystemExit:
        raise
    except BaseException:
        _write_safe_error()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
