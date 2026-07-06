"""Data model for Chronicle's regression testing system.

A `ChronicleTest` replays a stored run from a captured snapshot and checks
the result against a list of `ChronicleAssertion`s — see
`chronicle.testing.runner.ChronicleTestRunner`.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

AssertionType = Literal[
    "output_contains",
    "output_not_contains",
    "output_matches_regex",
    "tool_called",
    "tool_not_called",
    "token_count_under",
    "latency_under_ms",
    "no_errors",
    "custom",
]

TestStatus = Literal["pass", "fail", "error"]
OnFail = Literal["fail", "warn"]


@dataclass
class ChronicleAssertion:
    """One check to run against a test's replayed events.

    `target` is always a plain string (e.g. a substring, a regex pattern, a
    tool name, or a stringified number) — never executed as code, only
    compared/parsed by `chronicle.testing.runner.evaluate_assertion`.
    """

    assertion_type: AssertionType
    target: str
    agent_name: str | None = None
    on_fail: OnFail = "fail"
    assertion_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "assertion_type": self.assertion_type,
            "target": self.target,
            "agent_name": self.agent_name,
            "on_fail": self.on_fail,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChronicleAssertion":
        return cls(
            assertion_id=data.get("assertion_id") or str(uuid.uuid4()),
            assertion_type=data["assertion_type"],
            target=data["target"],
            agent_name=data.get("agent_name"),
            on_fail=data.get("on_fail", "fail"),
        )


@dataclass
class ChronicleTest:
    """A regression test: replay `source_run_id` and check the result.

    `source_snapshot_id` defaults to `None`, meaning "the snapshot at step
    0" — resolved lazily by `ChronicleTestRunner` at run time rather than
    eagerly here, since resolving it requires a server round-trip.
    """

    name: str
    source_run_id: str
    source_snapshot_id: str | None = None
    assertions: list[ChronicleAssertion] = field(default_factory=list)
    test_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    last_run_at: float | None = None
    last_result: TestStatus | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "source_run_id": self.source_run_id,
            "source_snapshot_id": self.source_snapshot_id,
            "assertions": [a.to_dict() for a in self.assertions],
            "created_at": self.created_at,
            "last_run_at": self.last_run_at,
            "last_result": self.last_result,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChronicleTest":
        return cls(
            test_id=data.get("test_id") or str(uuid.uuid4()),
            name=data["name"],
            source_run_id=data["source_run_id"],
            source_snapshot_id=data.get("source_snapshot_id"),
            assertions=[ChronicleAssertion.from_dict(a) for a in data.get("assertions", [])],
            created_at=data.get("created_at", time.time()),
            last_run_at=data.get("last_run_at"),
            last_result=data.get("last_result"),
        )


@dataclass
class AssertionResult:
    """The outcome of evaluating one `ChronicleAssertion` against a replay's events."""

    assertion_id: str
    assertion_type: str
    passed: bool
    reason: str
    on_fail: OnFail = "fail"

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "assertion_type": self.assertion_type,
            "passed": self.passed,
            "reason": self.reason,
            "on_fail": self.on_fail,
        }


@dataclass
class TestResult:
    """The outcome of running one `ChronicleTest`.

    `status` is `"error"` when the replay itself couldn't be started,
    timed out, or failed before assertions could even be evaluated (see
    `error_reason`); otherwise it's `"pass"`/`"fail"` based on whether any
    assertion with `on_fail == "fail"` failed. `passed` mirrors
    `status == "pass"` for convenience.
    """

    __test__ = False  # not a pytest test class, despite the name

    test_id: str
    replay_run_id: str | None
    status: TestStatus
    passed: bool
    assertion_results: list[AssertionResult] = field(default_factory=list)
    duration_ms: float | None = None
    token_usage: dict[str, int | None] | None = None
    error_reason: str | None = None
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "test_id": self.test_id,
            "replay_run_id": self.replay_run_id,
            "status": self.status,
            "passed": self.passed,
            "assertion_results": [r.to_dict() for r in self.assertion_results],
            "duration_ms": self.duration_ms,
            "token_usage": self.token_usage,
            "error_reason": self.error_reason,
            "created_at": self.created_at,
        }


@dataclass
class SuiteResult:
    """Aggregate outcome of running a list of `ChronicleTest`s via `run_suite()`."""

    results: list[TestResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.status == "pass")

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.status == "fail")

    @property
    def errored_count(self) -> int:
        return sum(1 for r in self.results if r.status == "error")

    @property
    def all_passed(self) -> bool:
        return all(r.status == "pass" for r in self.results)
