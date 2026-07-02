import json
from types import SimpleNamespace

from chronicle import ChronicleTracer
from chronicle.adapters.openai_agents import ChronicleAgentHooks


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


def test_on_agent_start_records_agent_message(tmp_path):
    tracer = _tracer(tmp_path)
    hooks = ChronicleAgentHooks(tracer, agent_name="researcher")

    hooks.on_agent_start(agent=SimpleNamespace(name="researcher"), input="find the weather")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "agent_message"
    assert events[0]["agent_name"] == "researcher"
    assert events[0]["data"]["event"] == "agent_start"
    assert events[0]["data"]["input"] == "find the weather"


def test_on_agent_end_records_agent_message_with_duration(tmp_path):
    tracer = _tracer(tmp_path)
    hooks = ChronicleAgentHooks(tracer)
    agent = SimpleNamespace(name="researcher")

    hooks.on_agent_start(agent=agent, input="go")
    hooks.on_agent_end(agent=agent, output="done")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[1]["event_type"] == "agent_message"
    assert events[1]["data"]["event"] == "agent_end"
    assert events[1]["data"]["output"] == "done"
    assert events[1]["duration_ms"] is not None


def test_on_tool_call_and_on_tool_result_record_tool_call_events(tmp_path):
    tracer = _tracer(tmp_path)
    hooks = ChronicleAgentHooks(tracer)
    agent = SimpleNamespace(name="researcher")

    hooks.on_tool_call(tool_name="search", arguments={"query": "weather"}, agent=agent)
    hooks.on_tool_result(tool_name="search", result="sunny", agent=agent)
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "tool_call"
    assert events[0]["data"]["event"] == "tool_call"
    assert events[0]["data"]["tool_name"] == "search"
    assert events[0]["data"]["arguments"] == {"query": "weather"}

    assert events[1]["event_type"] == "tool_call"
    assert events[1]["data"]["event"] == "tool_result"
    assert events[1]["data"]["result"] == "sunny"
    assert events[1]["duration_ms"] is not None


def test_on_handoff_records_source_and_target_agent(tmp_path):
    tracer = _tracer(tmp_path)
    hooks = ChronicleAgentHooks(tracer)

    hooks.on_handoff(source=SimpleNamespace(name="triage"), target=SimpleNamespace(name="billing"))
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "agent_message"
    assert events[0]["data"]["event"] == "handoff"
    assert events[0]["data"]["source_agent"] == "triage"
    assert events[0]["data"]["target_agent"] == "billing"
    assert events[0]["agent_name"] == "triage"


def test_hooks_fall_back_to_default_agent_name_when_agent_has_no_name(tmp_path):
    tracer = _tracer(tmp_path)
    hooks = ChronicleAgentHooks(tracer, agent_name="fallback-agent")

    hooks.on_agent_start(agent=None, input="hi")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["agent_name"] == "fallback-agent"
