import json
from types import SimpleNamespace

from chronicle import ChronicleTracer
from chronicle.adapters.crewai import ChronicleCrewAICallbackHandler


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


def _make_crew(name="research crew", agents=None, tasks=None):
    return SimpleNamespace(name=name, agents=agents or [], tasks=tasks or [])


def test_on_crew_start_records_agent_message_with_crew_details(tmp_path):
    tracer = _tracer(tmp_path)
    handler = ChronicleCrewAICallbackHandler(tracer)
    agent = SimpleNamespace(role="researcher", goal="find facts")
    task = SimpleNamespace(description="research topic")
    crew = _make_crew(agents=[agent], tasks=[task])

    handler.on_crew_start(crew=crew, inputs={"topic": "AI"})
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "agent_message"
    assert events[0]["data"]["event"] == "crew_start"
    assert events[0]["data"]["crew_name"] == "research crew"
    assert events[0]["data"]["agent_names"] == ["researcher"]
    assert events[0]["data"]["task_names"] == ["research topic"]
    assert events[0]["data"]["inputs"] == {"topic": "AI"}


def test_on_crew_end_records_output_and_duration(tmp_path):
    tracer = _tracer(tmp_path)
    handler = ChronicleCrewAICallbackHandler(tracer)
    crew = _make_crew()

    handler.on_crew_start(crew=crew, inputs={})
    handler.on_crew_end(crew=crew, output="final report")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[1]["event_type"] == "agent_message"
    assert events[1]["data"]["event"] == "crew_end"
    assert events[1]["data"]["output"] == "final report"
    assert events[1]["duration_ms"] is not None


def test_on_agent_start_and_end_record_role_goal_and_output(tmp_path):
    tracer = _tracer(tmp_path)
    handler = ChronicleCrewAICallbackHandler(tracer)
    agent = SimpleNamespace(role="writer", goal="write clearly")
    task = SimpleNamespace(description="write summary")

    handler.on_agent_start(agent=agent, task=task)
    handler.on_agent_end(agent=agent, output="summary text")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "agent_message"
    assert events[0]["data"]["event"] == "agent_start"
    assert events[0]["data"]["role"] == "writer"
    assert events[0]["data"]["goal"] == "write clearly"
    assert events[0]["data"]["task_name"] == "write summary"
    assert events[0]["agent_name"] == "writer"

    assert events[1]["data"]["event"] == "agent_end"
    assert events[1]["data"]["output"] == "summary text"
    assert events[1]["duration_ms"] is not None


def test_on_task_start_and_end_record_description_and_assigned_agent(tmp_path):
    tracer = _tracer(tmp_path)
    handler = ChronicleCrewAICallbackHandler(tracer)
    agent = SimpleNamespace(role="analyst")
    task = SimpleNamespace(description="analyze data", expected_output="a report", agent=agent)

    handler.on_task_start(task=task)
    handler.on_task_end(task=task, output="analysis complete")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["data"]["event"] == "task_start"
    assert events[0]["data"]["description"] == "analyze data"
    assert events[0]["data"]["expected_output"] == "a report"
    assert events[0]["data"]["assigned_agent"] == "analyst"
    assert events[0]["agent_name"] == "analyst"

    assert events[1]["data"]["event"] == "task_end"
    assert events[1]["data"]["output"] == "analysis complete"
    assert events[1]["duration_ms"] is not None


def test_on_tool_start_and_end_record_tool_call_events(tmp_path):
    tracer = _tracer(tmp_path)
    handler = ChronicleCrewAICallbackHandler(tracer)
    agent = SimpleNamespace(role="researcher")

    handler.on_tool_start(tool_name="search", input="weather today", agent=agent)
    handler.on_tool_end(tool_name="search", output="sunny", agent=agent)
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "tool_call"
    assert events[0]["data"]["event"] == "tool_call"
    assert events[0]["data"]["tool_name"] == "search"
    assert events[0]["data"]["input"] == "weather today"

    assert events[1]["event_type"] == "tool_call"
    assert events[1]["data"]["event"] == "tool_result"
    assert events[1]["data"]["output"] == "sunny"
    assert events[1]["duration_ms"] is not None


def test_on_tool_error_records_error_event(tmp_path):
    tracer = _tracer(tmp_path)
    handler = ChronicleCrewAICallbackHandler(tracer)
    agent = SimpleNamespace(role="researcher")

    handler.on_tool_start(tool_name="search", input="x", agent=agent)
    handler.on_tool_error(tool_name="search", error=RuntimeError("timeout"), agent=agent)
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[1]["event_type"] == "error"
    assert events[1]["data"]["event"] == "tool_error"
    assert events[1]["data"]["tool_name"] == "search"
    assert events[1]["error"] == "timeout"


def test_on_crew_start_and_end_record_memory_update_when_state_kwarg_changes(tmp_path):
    tracer = _tracer(tmp_path)
    handler = ChronicleCrewAICallbackHandler(tracer)
    crew = _make_crew()

    handler.on_crew_start(crew=crew, inputs={}, state={"phase": "start"})
    handler.on_crew_end(crew=crew, output="done", state={"phase": "end"})
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    memory_events = [e for e in events if e["event_type"] == "memory_update"]
    assert len(memory_events) == 1
    assert memory_events[0]["data"]["memory_before"] == {"phase": "start"}
    assert memory_events[0]["data"]["memory_after"] == {"phase": "end"}
    assert memory_events[0]["data"]["keys_changed"] == ["phase"]


def test_handler_falls_back_to_default_agent_name_when_agent_has_no_role(tmp_path):
    tracer = _tracer(tmp_path)
    handler = ChronicleCrewAICallbackHandler(tracer, agent_name="fallback-agent")

    handler.on_agent_start(agent=None, task=None)
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["agent_name"] == "fallback-agent"
    assert events[0]["data"]["task_name"] == "unknown"
