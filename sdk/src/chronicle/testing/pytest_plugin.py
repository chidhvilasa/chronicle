"""Pytest plugin exposing the `chronicle_test` fixture.

Registered as a `pytest11` entry point (`sdk/pyproject.toml`), so it's
picked up automatically once `chronicle-sdk` is installed — no
`pytest_plugins = [...]` needed in the consuming project's `conftest.py`.

    def test_my_agent(chronicle_test):
        result = chronicle_test.run("my agent test name")
        assert result.passed
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from chronicle.testing.models import TestResult
from chronicle.testing.runner import ChronicleTestRunner


class ChronicleTestFixture:
    """Thin wrapper the `chronicle_test` fixture hands to test functions."""

    def __init__(self, runner: ChronicleTestRunner) -> None:
        self._runner = runner

    def run(self, name: str) -> TestResult:
        """Looks up a stored `ChronicleTest` by name and runs it."""
        test = self._runner.get_test_by_name(name)
        return self._runner.run_test(test)


@pytest.fixture
def chronicle_test() -> Iterator[ChronicleTestFixture]:
    with ChronicleTestRunner() as runner:
        yield ChronicleTestFixture(runner)
