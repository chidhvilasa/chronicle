import json

from chronicle import ChronicleTracer


def _unreachable_tracer(tmp_path, **kwargs):
    return ChronicleTracer(
        server_url="http://127.0.0.1:1",  # nothing listens here
        timeout=0.2,
        local_dir=tmp_path / "chronicle_runs",
        **kwargs,
    )


def _read_local_events(tmp_path, run_id):
    path = tmp_path / "chronicle_runs" / f"{run_id}.json"
    return json.loads(path.read_text())


def test_tracer_generates_run_id_when_not_provided(tmp_path):
    tracer = _unreachable_tracer(tmp_path)
    assert tracer.run_id
    tracer.close()


def test_tracer_accepts_explicit_run_id(tmp_path):
    tracer = _unreachable_tracer(tmp_path, run_id="my-run")
    assert tracer.run_id == "my-run"
    tracer.close()


def test_record_event_returns_event_with_expected_fields(tmp_path):
    tracer = _unreachable_tracer(tmp_path, batch_size=100)
    event = tracer.record_event("tool_call", data={"tool_name": "search"}, agent_name="agent-1")

    assert event.run_id == tracer.run_id
    assert event.event_type == "tool_call"
    assert event.agent_name == "agent-1"
    assert event.data == {"tool_name": "search"}
    assert event.event_id
    assert event.timestamp > 0
    tracer.close()


def test_flush_falls_back_to_local_json_when_server_unreachable(tmp_path):
    tracer = _unreachable_tracer(tmp_path, batch_size=100)
    tracer.record_event("tool_call", data={"tool_name": "search"})
    tracer.record_event("llm_call", data={"model": "gpt-4o"})
    tracer.close()

    events = _read_local_events(tmp_path, tracer.run_id)
    assert [e["event_type"] for e in events] == ["tool_call", "llm_call"]
    assert events[0]["run_id"] == tracer.run_id


def test_batching_flushes_automatically_at_batch_size(tmp_path):
    tracer = _unreachable_tracer(tmp_path, batch_size=2)
    path = tmp_path / "chronicle_runs" / f"{tracer.run_id}.json"

    tracer.record_event("tool_call", data={})
    assert not path.exists()

    tracer.record_event("tool_call", data={})
    assert path.exists()
    tracer.close()


def test_context_manager_flushes_on_exit(tmp_path):
    run_id = "ctx-run"
    path = tmp_path / "chronicle_runs" / f"{run_id}.json"

    with _unreachable_tracer(tmp_path, run_id=run_id, batch_size=100) as tracer:
        tracer.record_event("error", data={"message": "boom"}, error="boom")
        assert not path.exists()

    assert path.exists()
    events = _read_local_events(tmp_path, run_id)
    assert events[0]["error"] == "boom"
