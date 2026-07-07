import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from chronicle import ChronicleTracer
from chronicle.adapters.langgraph import LangGraphAdapter


def _tracer(tmp_path, **kwargs):
    return ChronicleTracer(
        server_url="http://127.0.0.1:1",  # nothing listens here
        timeout=0.2,
        local_dir=tmp_path / "chronicle_runs",
        batch_size=1,
        **kwargs,
    )


def _read_events(tmp_path, run_id):
    path = tmp_path / "chronicle_runs" / f"{run_id}.json"
    return json.loads(path.read_text())


def test_llm_hooks_record_llm_call_event_with_token_usage(tmp_path):
    tracer = _tracer(tmp_path)
    adapter = LangGraphAdapter(tracer, agent_name="test-agent")
    run_id = uuid.uuid4()

    adapter.on_llm_start({"name": "gpt-4o"}, ["hello"], run_id=run_id)
    response = SimpleNamespace(
        generations=[[SimpleNamespace(text="hi there")]],
        llm_output={
            "token_usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
        },
    )
    adapter.on_llm_end(response, run_id=run_id)
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "llm_call"
    assert event["agent_name"] == "test-agent"
    assert event["data"]["model"] == "gpt-4o"
    assert event["data"]["prompts"] == ["hello"]
    assert event["data"]["completion"] == "hi there"
    assert event["token_usage"] == {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}
    assert event["duration_ms"] is not None


def test_llm_hooks_without_token_usage(tmp_path):
    tracer = _tracer(tmp_path)
    adapter = LangGraphAdapter(tracer)
    run_id = uuid.uuid4()

    adapter.on_llm_start({"name": "gpt-4o"}, ["hi"], run_id=run_id)
    response = SimpleNamespace(generations=[[SimpleNamespace(text="ok")]], llm_output={})
    adapter.on_llm_end(response, run_id=run_id)
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["token_usage"] is None


def test_tool_hooks_record_tool_call_event(tmp_path):
    tracer = _tracer(tmp_path)
    adapter = LangGraphAdapter(tracer)
    run_id = uuid.uuid4()

    adapter.on_tool_start({"name": "search"}, "weather query", run_id=run_id)
    adapter.on_tool_end("sunny", run_id=run_id)
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "tool_call"
    assert events[0]["data"]["tool_name"] == "search"
    assert events[0]["data"]["arguments"] == {"input": "weather query"}
    assert events[0]["data"]["result"] == "sunny"
    assert events[0]["duration_ms"] is not None


def test_on_agent_action_records_agent_message(tmp_path):
    tracer = _tracer(tmp_path)
    adapter = LangGraphAdapter(tracer)

    adapter.on_agent_action("call search tool", run_id=uuid.uuid4())
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "agent_message"
    assert events[0]["data"]["content"] == "call search tool"


def test_on_agent_finish_records_agent_message(tmp_path):
    tracer = _tracer(tmp_path)
    adapter = LangGraphAdapter(tracer)

    adapter.on_agent_finish("done", run_id=uuid.uuid4())
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "agent_message"
    assert events[0]["data"]["content"] == "done"


def test_on_chain_start_and_end_record_memory_update_when_state_changes(tmp_path):
    tracer = _tracer(tmp_path)
    adapter = LangGraphAdapter(tracer, agent_name="test-agent")
    run_id = uuid.uuid4()

    adapter.on_chain_start({}, {"counter": 1}, run_id=run_id)
    adapter.on_chain_end({"counter": 2}, run_id=run_id)
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    memory_events = [e for e in events if e["event_type"] == "memory_update"]
    assert len(memory_events) == 1
    assert memory_events[0]["data"]["memory_before"] == {"counter": 1}
    assert memory_events[0]["data"]["memory_after"] == {"counter": 2}
    assert memory_events[0]["data"]["keys_changed"] == ["counter"]


def test_on_chain_end_records_no_memory_update_when_state_is_unchanged(tmp_path):
    tracer = _tracer(tmp_path)
    adapter = LangGraphAdapter(tracer)
    run_id = uuid.uuid4()

    adapter.on_chain_start({}, {"counter": 1}, run_id=run_id)
    adapter.on_chain_end({"counter": 1}, run_id=run_id)
    # Force the events file to exist, since an unchanged memory diff records nothing.
    adapter.on_agent_action("noop", run_id=uuid.uuid4())
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert not any(e["event_type"] == "memory_update" for e in events)


def test_on_chain_end_records_no_memory_update_without_a_matching_chain_start(tmp_path):
    tracer = _tracer(tmp_path)
    adapter = LangGraphAdapter(tracer)

    adapter.on_chain_end({"counter": 1}, run_id=uuid.uuid4())
    # Force the events file to exist even though on_chain_end alone only records a
    # snapshot (not an event), so _read_events has something to read.
    adapter.on_agent_action("noop", run_id=uuid.uuid4())
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert not any(e["event_type"] == "memory_update" for e in events)


def test_on_chain_error_records_error_event(tmp_path):
    tracer = _tracer(tmp_path)
    adapter = LangGraphAdapter(tracer)

    adapter.on_chain_error(ValueError("boom"), run_id=uuid.uuid4())
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "error"
    assert events[0]["error"] == "boom"
    assert events[0]["data"]["error_type"] == "ValueError"


def test_auto_registers_graph_when_graph_module_and_attr_are_given():
    tracer = MagicMock(spec=ChronicleTracer)
    graph = object()

    LangGraphAdapter(tracer, graph=graph, graph_module="myapp.agent", graph_attr="graph")

    tracer.register_graph.assert_called_once_with(graph, "myapp.agent", "graph")


def test_does_not_register_graph_when_module_or_attr_is_missing():
    tracer = MagicMock(spec=ChronicleTracer)

    LangGraphAdapter(tracer, graph=object())
    LangGraphAdapter(tracer, graph_module="myapp.agent")
    LangGraphAdapter(tracer, graph_attr="graph")

    tracer.register_graph.assert_not_called()


def test_does_not_register_graph_by_default():
    tracer = MagicMock(spec=ChronicleTracer)

    LangGraphAdapter(tracer)

    tracer.register_graph.assert_not_called()
