"""ChronicleTestRunner: replays a stored run and evaluates assertions against it.

Talks to the Chronicle server exclusively over its REST API (`POST
/replay`, `GET /runs`, `GET /runs/{id}/events`, `GET /tests`) — it has no
direct database access, the same boundary `ChronicleTracer` respects.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from chronicle.testing.models import (
    AssertionResult,
    ChronicleAssertion,
    ChronicleTest,
    SuiteResult,
    TestResult,
)

DEFAULT_SERVER_URL = "http://127.0.0.1:7823"
DEFAULT_POLL_INTERVAL_S = 2.0
DEFAULT_MAX_WAIT_S = 300.0


class ChronicleTestRunner:
    """Replays a `ChronicleTest`'s source run and evaluates its assertions.

    `poll_interval`/`max_wait_s` default to 2s / 5 minutes per the spec, but
    are constructor parameters so tests can use much smaller values instead
    of actually waiting.
    """

    def __init__(
        self,
        server_url: str = DEFAULT_SERVER_URL,
        timeout: float = 5.0,
        poll_interval: float = DEFAULT_POLL_INTERVAL_S,
        max_wait_s: float = DEFAULT_MAX_WAIT_S,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.poll_interval = poll_interval
        self.max_wait_s = max_wait_s
        self._client = httpx.Client(timeout=timeout)

    def list_tests(self) -> list[ChronicleTest]:
        response = self._client.get(f"{self.server_url}/tests")
        response.raise_for_status()
        return [ChronicleTest.from_dict(t) for t in response.json()]

    def get_test_by_name(self, name: str) -> ChronicleTest:
        """Fetches a stored test by name — used by the pytest fixture and `chronicle test run NAME`."""
        for test in self.list_tests():
            if test.name == name:
                return test
        raise ValueError(
            f"No Chronicle test named {name!r} found. Create one from the desktop app "
            "or POST /tests first."
        )

    def run_test(self, test: ChronicleTest) -> TestResult:
        """Replays `test.source_run_id` and evaluates every assertion against the result.

        Never raises for a replay/network failure — always returns a
        `TestResult`, with `status="error"` and `error_reason` set instead.
        The source run itself is never touched: `POST /replay` always
        creates a brand-new run.
        """
        try:
            snapshot_id = test.source_snapshot_id or self._resolve_step_zero_snapshot(
                test.source_run_id
            )
        except _RunnerError as exc:
            return TestResult(
                test_id=test.test_id, replay_run_id=None, status="error", passed=False,
                error_reason=str(exc),
            )

        try:
            response = self._client.post(
                f"{self.server_url}/replay",
                json={
                    "run_id": test.source_run_id,
                    "snapshot_id": snapshot_id,
                    "modifications": {},
                    "metadata": {"triggered_by": "test", "test_id": test.test_id},
                },
            )
            response.raise_for_status()
            replay_run_id = response.json()["run_id"]
        except httpx.HTTPError as exc:
            return TestResult(
                test_id=test.test_id, replay_run_id=None, status="error", passed=False,
                error_reason=f"failed to start replay: {exc}",
            )

        final_status = self._wait_for_completion(replay_run_id)
        if final_status is None:
            return TestResult(
                test_id=test.test_id, replay_run_id=replay_run_id, status="error", passed=False,
                error_reason="replay timeout after 300s",
            )
        if final_status != "complete":
            return TestResult(
                test_id=test.test_id, replay_run_id=replay_run_id, status="error", passed=False,
                error_reason=f"replay run ended with status {final_status!r}",
            )

        events = self._fetch_events(replay_run_id)
        assertion_results = [evaluate_assertion(a, events) for a in test.assertions]
        overall_passed = not any(
            not r.passed and r.on_fail == "fail" for r in assertion_results
        )

        return TestResult(
            test_id=test.test_id,
            replay_run_id=replay_run_id,
            status="pass" if overall_passed else "fail",
            passed=overall_passed,
            assertion_results=assertion_results,
            duration_ms=total_duration_ms(events),
            token_usage=total_token_usage(events),
        )

    def run_suite(self, tests: list[ChronicleTest]) -> SuiteResult:
        """Runs every test sequentially (not in parallel — see `KNOWN_ISSUES.md`)."""
        return SuiteResult(results=[self.run_test(test) for test in tests])

    def _resolve_step_zero_snapshot(self, run_id: str) -> str:
        try:
            response = self._client.get(f"{self.server_url}/runs/{run_id}/snapshots")
            response.raise_for_status()
            summaries = response.json()
        except httpx.HTTPError as exc:
            raise _RunnerError(f"could not list snapshots for run '{run_id}': {exc}") from exc

        for summary in summaries:
            if summary["step_index"] == 0:
                return summary["snapshot_id"]
        raise _RunnerError(f"no step-0 snapshot found for run '{run_id}'")

    def _wait_for_completion(self, replay_run_id: str) -> str | None:
        deadline = time.time() + self.max_wait_s
        while time.time() < deadline:
            try:
                response = self._client.get(f"{self.server_url}/runs")
                response.raise_for_status()
                runs = response.json()
            except httpx.HTTPError:
                runs = []
            run = next((r for r in runs if r["run_id"] == replay_run_id), None)
            if run is not None and run["status"] != "running":
                return str(run["status"])
            time.sleep(self.poll_interval)
        return None

    def _fetch_events(self, run_id: str) -> list[dict[str, Any]]:
        response = self._client.get(f"{self.server_url}/runs/{run_id}/events")
        response.raise_for_status()
        return list(response.json())

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ChronicleTestRunner:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


class _RunnerError(Exception):
    """Internal-only: caught in `run_test()` and turned into an `"error"` `TestResult`."""


def evaluate_assertion(assertion: ChronicleAssertion, events: list[dict[str, Any]]) -> AssertionResult:
    """Evaluates one assertion against a replay run's events (as returned by `GET /runs/{id}/events`).

    Pure and side-effect free — reused directly by `chronicle-server`'s
    `POST /tests/{id}/run` (lazily imported, same pattern as
    `server/src/replay.py`'s `chronicle-sdk` dependency) so the two run
    paths (SDK-driven replay vs. server-driven replay) can never evaluate
    assertions differently.
    """
    scoped = [e for e in events if assertion.agent_name is None or e.get("agent_name") == assertion.agent_name]
    assertion_type = assertion.assertion_type
    target = assertion.target

    if assertion_type == "output_contains":
        output = _final_output(scoped)
        passed = target in output
        reason = f"final output {'contains' if passed else 'does not contain'} {target!r}"
    elif assertion_type == "output_not_contains":
        output = _final_output(scoped)
        passed = target not in output
        reason = f"final output {'does not contain' if passed else 'contains'} {target!r}"
    elif assertion_type == "output_matches_regex":
        output = _final_output(scoped)
        try:
            passed = re.search(target, output) is not None
            reason = f"final output {'matches' if passed else 'does not match'} regex {target!r}"
        except re.error as exc:
            passed = False
            reason = f"{target!r} is not a valid regex: {exc}"
    elif assertion_type == "tool_called":
        called = _tool_names(scoped)
        passed = target in called
        reason = f"tool {target!r} {'was called' if passed else 'was not called'}"
    elif assertion_type == "tool_not_called":
        called = _tool_names(scoped)
        passed = target not in called
        reason = f"tool {target!r} {'was not called' if passed else 'was called'}"
    elif assertion_type == "token_count_under":
        usage = total_token_usage(scoped)
        total = (usage["input_tokens"] or 0) + (usage["output_tokens"] or 0)
        try:
            limit = int(target)
            passed = total < limit
            reason = f"total tokens {total} {'is under' if passed else 'is not under'} {limit}"
        except ValueError:
            passed = False
            reason = f"{target!r} is not a valid integer token limit"
    elif assertion_type == "latency_under_ms":
        duration = total_duration_ms(scoped)
        try:
            limit = int(target)
            passed = duration < limit
            reason = f"duration {duration:.0f}ms {'is under' if passed else 'is not under'} {limit}ms"
        except ValueError:
            passed = False
            reason = f"{target!r} is not a valid integer millisecond limit"
    elif assertion_type == "no_errors":
        error_count = sum(1 for e in scoped if e.get("event_type") == "error")
        passed = error_count == 0
        reason = "no error events" if passed else f"{error_count} error event(s) found"
    else:  # "custom"
        passed = True
        reason = "custom assertion recorded (no automatic evaluation implemented yet)"

    return AssertionResult(
        assertion_id=assertion.assertion_id,
        assertion_type=assertion_type,
        passed=passed,
        reason=reason,
        on_fail=assertion.on_fail,
    )


def total_duration_ms(events: list[dict[str, Any]]) -> float:
    """Wall-clock span of a run, derived from its events' timestamps (0 if fewer than 2 events)."""
    timestamps = [e["timestamp"] for e in events if e.get("timestamp") is not None]
    if len(timestamps) < 2:
        return 0.0
    return (max(timestamps) - min(timestamps)) * 1000


def total_token_usage(events: list[dict[str, Any]]) -> dict[str, int | None]:
    input_tokens = sum(e.get("input_tokens") or 0 for e in events)
    output_tokens = sum(e.get("output_tokens") or 0 for e in events)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _final_output(events: list[dict[str, Any]]) -> str:
    """The last `agent_message`'s content, falling back to the last `llm_call`'s completion."""
    for event in reversed(events):
        if event.get("event_type") == "agent_message":
            content = (event.get("data") or {}).get("content")
            if content is not None:
                return str(content)
    for event in reversed(events):
        if event.get("event_type") == "llm_call":
            completion = (event.get("data") or {}).get("completion")
            if completion is not None:
                return str(completion)
    return ""


def _tool_names(events: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for event in events:
        if event.get("event_type") != "tool_call":
            continue
        tool_name = (event.get("data") or {}).get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            names.add(tool_name)
    return names
