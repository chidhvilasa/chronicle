from chronicle.testing.models import ChronicleAssertion
from chronicle.testing.runner import evaluate_assertion, total_duration_ms, total_token_usage


def _event(event_type, agent_name="agent-a", data=None, timestamp=1000.0, **overrides):
    event = {
        "event_id": "evt-1",
        "run_id": "run-1",
        "timestamp": timestamp,
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


def _assertion(assertion_type, target, **overrides):
    return ChronicleAssertion(assertion_type=assertion_type, target=target, **overrides)


def test_output_contains_passes_when_final_agent_message_has_target():
    events = [_event("agent_message", data={"content": "hello world"})]
    result = evaluate_assertion(_assertion("output_contains", "hello"), events)
    assert result.passed is True


def test_output_contains_fails_when_missing():
    events = [_event("agent_message", data={"content": "goodbye"})]
    result = evaluate_assertion(_assertion("output_contains", "hello"), events)
    assert result.passed is False


def test_output_not_contains_inverse_of_output_contains():
    events = [_event("agent_message", data={"content": "goodbye"})]
    result = evaluate_assertion(_assertion("output_not_contains", "hello"), events)
    assert result.passed is True


def test_output_matches_regex():
    events = [_event("agent_message", data={"content": "order #42 shipped"})]
    assert evaluate_assertion(_assertion("output_matches_regex", r"#\d+"), events).passed is True
    assert evaluate_assertion(_assertion("output_matches_regex", r"#[a-z]+"), events).passed is False


def test_final_output_falls_back_to_last_llm_call_completion():
    events = [_event("llm_call", data={"completion": "the answer is 42"})]
    result = evaluate_assertion(_assertion("output_contains", "42"), events)
    assert result.passed is True


def test_tool_called_and_tool_not_called():
    events = [_event("tool_call", data={"tool_name": "search"})]
    assert evaluate_assertion(_assertion("tool_called", "search"), events).passed is True
    assert evaluate_assertion(_assertion("tool_called", "weather"), events).passed is False
    assert evaluate_assertion(_assertion("tool_not_called", "weather"), events).passed is True
    assert evaluate_assertion(_assertion("tool_not_called", "search"), events).passed is False


def test_token_count_under():
    events = [_event("llm_call", input_tokens=100, output_tokens=50)]
    assert evaluate_assertion(_assertion("token_count_under", "200"), events).passed is True
    assert evaluate_assertion(_assertion("token_count_under", "100"), events).passed is False


def test_latency_under_ms():
    events = [
        _event("llm_call", timestamp=1000.0),
        _event("llm_call", timestamp=1000.5),
    ]
    assert evaluate_assertion(_assertion("latency_under_ms", "1000"), events).passed is True
    assert evaluate_assertion(_assertion("latency_under_ms", "100"), events).passed is False


def test_no_errors_passes_with_zero_error_events():
    events = [_event("tool_call")]
    assert evaluate_assertion(_assertion("no_errors", ""), events).passed is True


def test_no_errors_fails_when_an_error_event_exists():
    events = [_event("tool_call"), _event("error")]
    assert evaluate_assertion(_assertion("no_errors", ""), events).passed is False


def test_custom_assertion_always_passes():
    result = evaluate_assertion(_assertion("custom", "anything"), [])
    assert result.passed is True
    assert "no automatic evaluation" in result.reason


def test_agent_name_scopes_the_assertion_to_one_agent():
    events = [
        _event("tool_call", agent_name="agent-a", data={"tool_name": "search"}),
        _event("tool_call", agent_name="agent-b", data={"tool_name": "weather"}),
    ]
    result = evaluate_assertion(
        _assertion("tool_called", "weather", agent_name="agent-a"), events
    )
    assert result.passed is False

    result = evaluate_assertion(
        _assertion("tool_called", "weather", agent_name="agent-b"), events
    )
    assert result.passed is True


def test_total_duration_ms_with_fewer_than_two_events_is_zero():
    assert total_duration_ms([]) == 0.0
    assert total_duration_ms([_event("tool_call")]) == 0.0


def test_total_token_usage_sums_input_and_output():
    events = [
        _event("llm_call", input_tokens=10, output_tokens=5),
        _event("llm_call", input_tokens=20, output_tokens=None),
    ]
    usage = total_token_usage(events)
    assert usage == {"input_tokens": 30, "output_tokens": 5, "total_tokens": 35}
