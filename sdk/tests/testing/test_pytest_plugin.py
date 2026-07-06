from unittest.mock import MagicMock

from chronicle.testing.models import ChronicleTest, TestResult
from chronicle.testing.pytest_plugin import ChronicleTestFixture


def test_fixture_run_looks_up_test_by_name_and_runs_it():
    test = ChronicleTest(name="my agent test name", source_run_id="run-1")
    expected_result = TestResult(test_id=test.test_id, replay_run_id="replay-1", status="pass", passed=True)

    runner = MagicMock()
    runner.get_test_by_name.return_value = test
    runner.run_test.return_value = expected_result

    fixture = ChronicleTestFixture(runner)
    result = fixture.run("my agent test name")

    runner.get_test_by_name.assert_called_once_with("my agent test name")
    runner.run_test.assert_called_once_with(test)
    assert result is expected_result
    assert result.passed is True


def test_plugin_is_registered_as_a_pytest11_entry_point():
    from importlib.metadata import entry_points

    plugins = entry_points(group="pytest11")
    names = [ep.name for ep in plugins]
    assert "chronicle" in names


def test_chronicle_test_fixture_is_usable_in_a_real_pytest_run(pytester):
    # No explicit `-p chronicle.testing.pytest_plugin` needed: installing
    # chronicle-sdk registers it automatically via the `pytest11` entry
    # point exercised by the test above.
    pytester.makepyfile(
        """
        def test_uses_fixture(chronicle_test):
            assert hasattr(chronicle_test, "run")
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)
