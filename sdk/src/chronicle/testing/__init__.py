"""Chronicle regression testing: define assertions on agent outputs, replay stored runs, and check them.

    from chronicle.testing import ChronicleAssertion, ChronicleTest, ChronicleTestRunner

    test = ChronicleTest(
        name="agent still greets the user",
        source_run_id="run-123",
        assertions=[ChronicleAssertion(assertion_type="output_contains", target="hello")],
    )
    result = ChronicleTestRunner().run_test(test)
"""

from chronicle.testing.models import (
    AssertionResult,
    ChronicleAssertion,
    ChronicleTest,
    SuiteResult,
    TestResult,
)
from chronicle.testing.runner import ChronicleTestRunner

__all__ = [
    "ChronicleAssertion",
    "ChronicleTest",
    "AssertionResult",
    "TestResult",
    "SuiteResult",
    "ChronicleTestRunner",
]
