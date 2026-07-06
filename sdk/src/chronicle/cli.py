"""`chronicle` CLI: start/stop/status the local server, run tests, or open the desktop app.

Registered as a console script via `sdk/pyproject.toml`'s
`[project.scripts]` (`chronicle = "chronicle.cli:main"`).
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from chronicle.server_manager import DEFAULT_HOST, DEFAULT_PORT, ServerManager
from chronicle.testing.models import SuiteResult, TestResult
from chronicle.testing.runner import ChronicleTestRunner

_OPEN_APP_CANDIDATES = [
    ["chronicle-app"],
    ["open", "-a", "Chronicle"],
    ["cmd", "/c", "start", "", "Chronicle"],
]


def _start(args: argparse.Namespace) -> int:
    manager = ServerManager(host=args.host, port=args.port)
    if manager.is_running():
        print(f"Chronicle: server already running at {manager.base_url}")
        return 0

    try:
        import uvicorn
    except ImportError:
        print(
            "Chronicle: 'chronicle-server' isn't installed in this environment. "
            "Run `pip install chronicle-server` first."
        )
        return 1

    print(f"Chronicle: starting server at {manager.base_url} (Ctrl+C to stop)")
    try:
        uvicorn.run("src.main:app", host=args.host, port=args.port)
    except KeyboardInterrupt:  # pragma: no cover - interactive-only path
        print("Chronicle: server stopped")
    return 0


def _stop(args: argparse.Namespace) -> int:
    manager = ServerManager(host=args.host, port=args.port)
    if manager.stop():
        print("Chronicle: server stopped")
    else:
        print("Chronicle: no running server found")
    return 0


def _status(args: argparse.Namespace) -> int:
    manager = ServerManager(host=args.host, port=args.port)
    if manager.is_running():
        print(f"Chronicle: server is running at {manager.base_url}")
    else:
        print(f"Chronicle: server is not running (expected at {manager.base_url})")
    return 0


def _open(args: argparse.Namespace) -> int:
    del args
    for command in _OPEN_APP_CANDIDATES:
        try:
            subprocess.Popen(command)
        except OSError:
            continue
        print("Chronicle: opening the desktop app")
        return 0
    print(
        "Chronicle: could not find the desktop app. Download it from "
        "https://github.com/chidhvilasa/chronicle/releases"
    )
    return 1


def _print_test_result(result: TestResult) -> None:
    icon = {"pass": "PASS", "fail": "FAIL", "error": "ERROR"}[result.status]
    print(f"[{icon}] {result.test_id}")
    if result.error_reason is not None:
        print(f"  {result.error_reason}")
    for assertion in result.assertion_results:
        mark = "ok" if assertion.passed else "FAILED"
        print(f"  - [{mark}] {assertion.assertion_type}: {assertion.reason}")


def _print_suite_result(suite: SuiteResult) -> None:
    for result in suite.results:
        _print_test_result(result)
    print(
        f"\n{suite.passed_count}/{suite.total} passed "
        f"({suite.failed_count} failed, {suite.errored_count} errored)"
    )


def _test_run(args: argparse.Namespace) -> int:
    with ChronicleTestRunner(server_url=f"http://{args.host}:{args.port}") as runner:
        try:
            if args.name is not None:
                tests = [runner.get_test_by_name(args.name)]
            else:
                tests = runner.list_tests()
        except Exception as exc:  # noqa: BLE001 - surfaced to the CLI user, not re-raised
            print(f"Chronicle: {exc}")
            return 1

        if not tests:
            print("Chronicle: no tests found. Create one from the desktop app first.")
            return 0

        suite = runner.run_suite(tests)
        _print_suite_result(suite)
        return 0 if suite.all_passed else 1


def _test_list(args: argparse.Namespace) -> int:
    with ChronicleTestRunner(server_url=f"http://{args.host}:{args.port}") as runner:
        try:
            tests = runner.list_tests()
        except Exception as exc:  # noqa: BLE001
            print(f"Chronicle: {exc}")
            return 1

        if not tests:
            print("Chronicle: no tests yet. Create one from the desktop app first.")
            return 0

        for test in tests:
            last = test.last_result or "never run"
            print(f"{test.name} ({test.test_id})  last: {last}")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="chronicle", description="Chronicle: the Chrome DevTools for AI agents."
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server host (default: %(default)s)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port (default: %(default)s)")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("start", help="Start the Chronicle server in the foreground").set_defaults(func=_start)
    subparsers.add_parser("stop", help="Stop any running Chronicle server").set_defaults(func=_stop)
    subparsers.add_parser("status", help="Show whether the Chronicle server is running").set_defaults(
        func=_status
    )
    subparsers.add_parser("open", help="Open the Chronicle desktop app").set_defaults(func=_open)

    test_parser = subparsers.add_parser("test", help="Run or list Chronicle regression tests")
    test_subparsers = test_parser.add_subparsers(dest="test_command", required=True)

    run_parser = test_subparsers.add_parser("run", help="Run all tests, or one by name")
    run_parser.add_argument("name", nargs="?", default=None, help="Run only the test with this name")
    run_parser.set_defaults(func=_test_run)

    list_parser = test_subparsers.add_parser("list", help="List all stored tests with their last result")
    list_parser.set_defaults(func=_test_list)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
