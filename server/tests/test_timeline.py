from src.timeline import build_timeline


def _event(
    event_id,
    run_id="run-1",
    timestamp=1000.0,
    event_type="tool_call",
    agent_name=None,
    duration_ms=None,
    input_tokens=None,
    output_tokens=None,
    data=None,
    error=None,
):
    return {
        "event_id": event_id,
        "run_id": run_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "agent_name": agent_name,
        "duration_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "data": data or {},
        "error": error,
    }


def test_build_timeline_empty():
    assert build_timeline([]) == []


def test_build_timeline_groups_by_agent():
    events = [
        _event("e1", agent_name="agent-a", event_type="llm_call", duration_ms=500, data={"model": "gpt-4o"}),
        _event("e2", agent_name="agent-b", event_type="tool_call", duration_ms=200, data={"tool_name": "search"}),
    ]
    lanes = build_timeline(events)
    assert [lane["agent_name"] for lane in lanes] == ["agent-a", "agent-b"]


def test_build_timeline_defaults_missing_agent_name_to_unknown():
    events = [_event("e1", agent_name=None, event_type="tool_call")]
    lanes = build_timeline(events)
    assert lanes[0]["agent_name"] == "unknown"


def test_build_timeline_segment_fields():
    events = [
        _event(
            "e1",
            agent_name="agent-a",
            event_type="llm_call",
            duration_ms=500,
            input_tokens=10,
            output_tokens=5,
            data={"model": "gpt-4o"},
        )
    ]
    segment = build_timeline(events)[0]["segments"][0]
    assert segment["type"] == "llm_call"
    assert segment["start_time_ms"] == 0
    assert segment["duration_ms"] == 500
    assert segment["label"] == "gpt-4o"
    assert segment["token_usage"] == {"input_tokens": 10, "output_tokens": 5}


def test_build_timeline_tool_call_label_uses_tool_name():
    events = [_event("e1", agent_name="agent-a", event_type="tool_call", data={"tool_name": "search"})]
    segment = build_timeline(events)[0]["segments"][0]
    assert segment["label"] == "search"
    assert segment["token_usage"] is None


def test_build_timeline_infers_waiting_segment_from_gap():
    events = [
        _event("e1", agent_name="agent-a", event_type="tool_call", timestamp=1000.0, duration_ms=100),
        _event("e2", agent_name="agent-a", event_type="tool_call", timestamp=1000.6, duration_ms=100),
    ]
    segments = build_timeline(events)[0]["segments"]
    assert [s["type"] for s in segments] == ["tool_call", "waiting", "tool_call"]

    waiting = segments[1]
    assert waiting["start_time_ms"] == 100
    assert round(waiting["duration_ms"]) == 500


def test_build_timeline_no_waiting_segment_when_events_are_contiguous():
    events = [
        _event("e1", agent_name="agent-a", event_type="tool_call", timestamp=1000.0, duration_ms=100),
        _event("e2", agent_name="agent-a", event_type="tool_call", timestamp=1000.1, duration_ms=100),
    ]
    segments = build_timeline(events)[0]["segments"]
    assert [s["type"] for s in segments] == ["tool_call", "tool_call"]


def test_build_timeline_error_segment_uses_error_message_as_label():
    events = [_event("e1", agent_name="agent-a", event_type="error", error="boom")]
    segment = build_timeline(events)[0]["segments"][0]
    assert segment["type"] == "error"
    assert segment["label"] == "boom"


def test_build_timeline_skips_non_segment_event_types():
    events = [_event("e1", agent_name="agent-a", event_type="agent_message", data={"content": "hi"})]
    assert build_timeline(events)[0]["segments"] == []


def test_build_timeline_retry_label_uses_reason():
    events = [_event("e1", agent_name="agent-a", event_type="retry", data={"reason": "timeout"})]
    segment = build_timeline(events)[0]["segments"][0]
    assert segment["type"] == "retry"
    assert segment["label"] == "timeout"
    assert segment["token_usage"] is None


def test_build_timeline_retry_label_defaults_when_no_reason():
    events = [_event("e1", agent_name="agent-a", event_type="retry")]
    segment = build_timeline(events)[0]["segments"][0]
    assert segment["label"] == "retry"
