from unittest.mock import MagicMock

import httpx
import pytest

from chronicle.testing.models import ChronicleAssertion, ChronicleTest
from chronicle.testing.runner import ChronicleTestRunner


def _runner(**kwargs):
    return ChronicleTestRunner(
        server_url="http://127.0.0.1:1",  # never actually dialed; every call is mocked
        poll_interval=0.01,
        max_wait_s=0.05,
        **kwargs,
    )


def _json_response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=response
        )
    return response


def _event(event_type, agent_name="agent-a", data=None, **overrides):
    event = {
        "event_id": "evt-1",
        "run_id": "replay-1",
        "timestamp": 1000.0,
        "event_type": event_type,
        "agent_name": agent_name,
        "duration_ms": None,
        "input_tokens": None,
        "output_tokens": None,
        "data": data or {},
        "error": None,
    }
    event.update(overrides)
    return event


class TestRunTest:
    def test_replays_and_evaluates_assertions_on_success(self, monkeypatch):
        runner = _runner()
        test = ChronicleTest(
            name="greets user",
            source_run_id="run-1",
            source_snapshot_id="snap-1",
            assertions=[ChronicleAssertion(assertion_type="output_contains", target="hello")],
        )

        post = MagicMock(return_value=_json_response({"run_id": "replay-1"}))
        get_calls = iter(
            [
                _json_response([{"run_id": "replay-1", "status": "complete"}]),
                _json_response([_event("agent_message", data={"content": "hello there"})]),
            ]
        )
        monkeypatch.setattr(runner._client, "post", post)
        monkeypatch.setattr(runner._client, "get", MagicMock(side_effect=lambda *a, **k: next(get_calls)))

        result = runner.run_test(test)

        assert result.status == "pass"
        assert result.passed is True
        assert result.replay_run_id == "replay-1"
        assert len(result.assertion_results) == 1
        assert result.assertion_results[0].passed is True

        post.assert_called_once()
        sent_body = post.call_args.kwargs["json"]
        assert sent_body["run_id"] == "run-1"
        assert sent_body["snapshot_id"] == "snap-1"
        assert sent_body["metadata"] == {"triggered_by": "test", "test_id": test.test_id}

    def test_resolves_step_zero_snapshot_when_source_snapshot_id_is_none(self, monkeypatch):
        runner = _runner()
        test = ChronicleTest(name="t", source_run_id="run-1", assertions=[])

        responses = iter(
            [
                _json_response([{"snapshot_id": "snap-0", "step_index": 0}]),
                _json_response([{"run_id": "replay-1", "status": "complete"}]),
                _json_response([]),
            ]
        )
        monkeypatch.setattr(runner._client, "get", MagicMock(side_effect=lambda *a, **k: next(responses)))
        post = MagicMock(return_value=_json_response({"run_id": "replay-1"}))
        monkeypatch.setattr(runner._client, "post", post)

        result = runner.run_test(test)

        assert result.status == "pass"
        assert post.call_args.kwargs["json"]["snapshot_id"] == "snap-0"

    def test_returns_error_result_when_no_step_zero_snapshot_exists(self, monkeypatch):
        runner = _runner()
        test = ChronicleTest(name="t", source_run_id="run-1", assertions=[])

        monkeypatch.setattr(runner._client, "get", MagicMock(return_value=_json_response([])))

        result = runner.run_test(test)

        assert result.status == "error"
        assert "no step-0 snapshot" in result.error_reason

    def test_returns_error_result_when_replay_fails_to_start(self, monkeypatch):
        runner = _runner()
        test = ChronicleTest(name="t", source_run_id="run-1", source_snapshot_id="snap-1", assertions=[])

        monkeypatch.setattr(
            runner._client, "post", MagicMock(side_effect=httpx.ConnectError("refused"))
        )

        result = runner.run_test(test)

        assert result.status == "error"
        assert "failed to start replay" in result.error_reason

    def test_returns_error_result_on_timeout(self, monkeypatch):
        runner = _runner()
        test = ChronicleTest(name="t", source_run_id="run-1", source_snapshot_id="snap-1", assertions=[])

        monkeypatch.setattr(
            runner._client, "post", MagicMock(return_value=_json_response({"run_id": "replay-1"}))
        )
        monkeypatch.setattr(
            runner._client,
            "get",
            MagicMock(return_value=_json_response([{"run_id": "replay-1", "status": "running"}])),
        )

        result = runner.run_test(test)

        assert result.status == "error"
        assert result.error_reason == "replay timeout after 300s"

    def test_returns_error_result_when_replay_run_fails(self, monkeypatch):
        runner = _runner()
        test = ChronicleTest(name="t", source_run_id="run-1", source_snapshot_id="snap-1", assertions=[])

        monkeypatch.setattr(
            runner._client, "post", MagicMock(return_value=_json_response({"run_id": "replay-1"}))
        )
        monkeypatch.setattr(
            runner._client,
            "get",
            MagicMock(return_value=_json_response([{"run_id": "replay-1", "status": "failed"}])),
        )

        result = runner.run_test(test)

        assert result.status == "error"
        assert "failed" in result.error_reason

    def test_warn_on_fail_assertion_does_not_fail_the_overall_test(self, monkeypatch):
        runner = _runner()
        test = ChronicleTest(
            name="t",
            source_run_id="run-1",
            source_snapshot_id="snap-1",
            assertions=[
                ChronicleAssertion(assertion_type="output_contains", target="missing", on_fail="warn")
            ],
        )

        monkeypatch.setattr(
            runner._client, "post", MagicMock(return_value=_json_response({"run_id": "replay-1"}))
        )
        get_calls = iter(
            [
                _json_response([{"run_id": "replay-1", "status": "complete"}]),
                _json_response([_event("agent_message", data={"content": "hi"})]),
            ]
        )
        monkeypatch.setattr(runner._client, "get", MagicMock(side_effect=lambda *a, **k: next(get_calls)))

        result = runner.run_test(test)

        assert result.passed is True
        assert result.assertion_results[0].passed is False


class TestGetTestByName:
    def test_finds_matching_test(self, monkeypatch):
        runner = _runner()
        monkeypatch.setattr(
            runner._client,
            "get",
            MagicMock(
                return_value=_json_response(
                    [{"test_id": "t1", "name": "my test", "source_run_id": "run-1", "assertions": []}]
                )
            ),
        )

        test = runner.get_test_by_name("my test")
        assert test.test_id == "t1"

    def test_raises_when_no_test_matches(self, monkeypatch):
        runner = _runner()
        monkeypatch.setattr(runner._client, "get", MagicMock(return_value=_json_response([])))

        with pytest.raises(ValueError, match="No Chronicle test named"):
            runner.get_test_by_name("missing")


class TestRunSuite:
    def test_aggregates_pass_fail_error_counts(self, monkeypatch):
        runner = _runner()
        tests = [
            ChronicleTest(name="a", source_run_id="run-1", source_snapshot_id="snap-1", assertions=[]),
            ChronicleTest(name="b", source_run_id="run-1", source_snapshot_id="snap-1", assertions=[]),
        ]

        monkeypatch.setattr(
            runner._client, "post", MagicMock(return_value=_json_response({"run_id": "replay-1"}))
        )
        monkeypatch.setattr(
            runner._client,
            "get",
            MagicMock(
                side_effect=lambda *a, **k: _json_response([{"run_id": "replay-1", "status": "complete"}])
                if a[0].endswith("/runs")
                else _json_response([])
            ),
        )

        suite = runner.run_suite(tests)

        assert suite.total == 2
        assert suite.passed_count == 2
        assert suite.all_passed is True
