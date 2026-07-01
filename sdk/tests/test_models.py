from chronicle.models import ChronicleEvent, TokenUsage


def test_token_usage_to_dict():
    usage = TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3)
    assert usage.to_dict() == {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}


def test_chronicle_event_to_dict_defaults():
    event = ChronicleEvent(run_id="run-1", event_type="tool_call")
    d = event.to_dict()

    assert d["run_id"] == "run-1"
    assert d["event_type"] == "tool_call"
    assert d["agent_name"] is None
    assert d["data"] == {}
    assert d["duration_ms"] is None
    assert d["token_usage"] is None
    assert d["error"] is None
    assert isinstance(d["event_id"], str) and d["event_id"]
    assert isinstance(d["timestamp"], float)


def test_chronicle_event_to_dict_with_token_usage():
    event = ChronicleEvent(
        run_id="run-1",
        event_type="llm_call",
        token_usage=TokenUsage(input_tokens=5, output_tokens=3, total_tokens=8),
    )

    assert event.to_dict()["token_usage"] == {
        "input_tokens": 5,
        "output_tokens": 3,
        "total_tokens": 8,
    }


def test_chronicle_event_ids_are_unique():
    event_a = ChronicleEvent(run_id="run-1", event_type="tool_call")
    event_b = ChronicleEvent(run_id="run-1", event_type="tool_call")
    assert event_a.event_id != event_b.event_id
