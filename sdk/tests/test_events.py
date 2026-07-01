from chronicle.events import EventType, new_event


def test_new_event_has_required_fields():
    event = new_event("run-1", "tool_call", {"tool_name": "search"})
    assert event["run_id"] == "run-1"
    assert event["event_type"] == "tool_call"
    assert event["payload"] == {"tool_name": "search"}
    assert event["parent_id"] is None
    assert isinstance(event["id"], str) and event["id"]
    assert isinstance(event["timestamp"], float)


def test_new_event_with_parent_id():
    event = new_event("run-1", "retry", {"attempt": 1}, parent_id="parent-1")
    assert event["parent_id"] == "parent-1"


def test_event_type_enum_values():
    assert EventType.TOOL_CALL == "tool_call"
    assert EventType.LLM_CALL == "llm_call"
    assert EventType.AGENT_MESSAGE == "agent_message"
    assert EventType.MEMORY_UPDATE == "memory_update"
    assert EventType.ERROR == "error"
    assert EventType.RETRY == "retry"
