"""Tests for chronicle.models.StateSnapshot and its capture/delivery path."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from chronicle import ChronicleTracer, StateSnapshot
from chronicle.adapters.langgraph import LangGraphAdapter, _json_safe


def _tracer(tmp_path, **kwargs):
    return ChronicleTracer(
        server_url="http://127.0.0.1:1",  # nothing listens here
        timeout=0.2,
        local_dir=tmp_path / "chronicle_runs",
        **kwargs,
    )


def _mock_tracer(run_id: str = "run-1") -> MagicMock:
    tracer = MagicMock(spec=ChronicleTracer)
    tracer.run_id = run_id
    return tracer


# --- StateSnapshot model ----------------------------------------------------


def test_state_snapshot_has_correct_fields():
    snapshot = StateSnapshot(
        run_id="run-1",
        step_index=2,
        event_id="evt-1",
        agent_name="agent-a",
        messages=[{"role": "user", "content": "hi"}],
        tool_results=[{"tool": "search", "result": "sunny"}],
        graph_state={"foo": "bar"},
        metadata={"note": "test"},
    )

    assert snapshot.run_id == "run-1"
    assert snapshot.step_index == 2
    assert snapshot.event_id == "evt-1"
    assert snapshot.agent_name == "agent-a"
    assert snapshot.messages == [{"role": "user", "content": "hi"}]
    assert snapshot.tool_results == [{"tool": "search", "result": "sunny"}]
    assert snapshot.graph_state == {"foo": "bar"}
    assert snapshot.metadata == {"note": "test"}
    assert snapshot.snapshot_id
    assert snapshot.timestamp > 0


def test_state_snapshot_to_dict_is_json_serializable():
    snapshot = StateSnapshot(run_id="run-1", step_index=0, graph_state={"a": 1})
    payload = snapshot.to_dict()
    json.dumps(payload)  # must not raise
    assert payload["run_id"] == "run-1"
    assert payload["step_index"] == 0
    assert payload["graph_state"] == {"a": 1}


def test_state_snapshot_default_ids_are_unique():
    a = StateSnapshot(run_id="run-1", step_index=0)
    b = StateSnapshot(run_id="run-1", step_index=1)
    assert a.snapshot_id != b.snapshot_id


# --- LangGraphAdapter: on_chain_end / on_agent_finish capture ---------------


def test_on_chain_end_triggers_snapshot_capture():
    tracer = _mock_tracer()
    adapter = LangGraphAdapter(tracer, agent_name="agent-a")

    adapter.on_chain_end({"messages": [{"role": "user", "content": "hi"}]}, run_id=uuid.uuid4())

    tracer.record_snapshot.assert_called_once()
    snapshot = tracer.record_snapshot.call_args[0][0]
    assert isinstance(snapshot, StateSnapshot)
    assert snapshot.run_id == "run-1"
    assert snapshot.step_index == 0
    assert snapshot.agent_name == "agent-a"
    assert snapshot.messages == [{"role": "user", "content": "hi"}]
    assert snapshot.graph_state == {"messages": [{"role": "user", "content": "hi"}]}


def test_on_chain_end_increments_step_index_across_calls():
    tracer = _mock_tracer()
    adapter = LangGraphAdapter(tracer)

    adapter.on_chain_end({}, run_id=uuid.uuid4())
    adapter.on_chain_end({}, run_id=uuid.uuid4())

    first_snapshot = tracer.record_snapshot.call_args_list[0][0][0]
    second_snapshot = tracer.record_snapshot.call_args_list[1][0][0]
    assert first_snapshot.step_index == 0
    assert second_snapshot.step_index == 1


def test_on_chain_end_ignores_non_dict_outputs():
    tracer = _mock_tracer()
    adapter = LangGraphAdapter(tracer)

    adapter.on_chain_end("not a dict", run_id=uuid.uuid4())  # type: ignore[arg-type]

    tracer.record_snapshot.assert_not_called()


def test_on_agent_finish_captures_snapshot_from_return_values():
    tracer = _mock_tracer()
    adapter = LangGraphAdapter(tracer)

    finish = SimpleNamespace(return_values={"messages": []}, log="done")
    adapter.on_agent_finish(finish, run_id=uuid.uuid4())

    tracer.record_snapshot.assert_called_once()
    snapshot = tracer.record_snapshot.call_args[0][0]
    assert snapshot.graph_state == {"messages": []}


def test_on_agent_finish_without_return_values_still_captures_empty_snapshot():
    tracer = _mock_tracer()
    adapter = LangGraphAdapter(tracer)

    adapter.on_agent_finish("done", run_id=uuid.uuid4())

    tracer.record_snapshot.assert_called_once()
    snapshot = tracer.record_snapshot.call_args[0][0]
    assert snapshot.graph_state == {}


# --- Fallback to local file when the server is unreachable -----------------


def test_snapshot_fallback_to_local_file_when_server_unreachable(tmp_path):
    tracer = _tracer(tmp_path)
    snapshot = StateSnapshot(run_id=tracer.run_id, step_index=0, graph_state={"foo": "bar"})

    thread = tracer.record_snapshot(snapshot)
    thread.join(timeout=5)
    tracer.close()

    path = tmp_path / "chronicle_runs" / f"{tracer.run_id}_snapshots.json"
    assert path.exists()
    saved = json.loads(path.read_text())
    assert len(saved) == 1
    assert saved[0]["snapshot_id"] == snapshot.snapshot_id
    assert saved[0]["graph_state"] == {"foo": "bar"}


def test_multiple_concurrent_snapshot_fallback_writes_all_accumulate(tmp_path):
    tracer = _tracer(tmp_path)
    threads = [
        tracer.record_snapshot(StateSnapshot(run_id=tracer.run_id, step_index=i))
        for i in range(5)
    ]
    for thread in threads:
        thread.join(timeout=5)
    tracer.close()

    path = tmp_path / "chronicle_runs" / f"{tracer.run_id}_snapshots.json"
    saved = json.loads(path.read_text())
    assert len(saved) == 5
    assert sorted(s["step_index"] for s in saved) == [0, 1, 2, 3, 4]


def test_record_snapshot_returns_immediately_without_blocking(tmp_path):
    tracer = _tracer(tmp_path)
    snapshot = StateSnapshot(run_id=tracer.run_id, step_index=0)

    start = time.perf_counter()
    thread = tracer.record_snapshot(snapshot)
    elapsed = time.perf_counter() - start

    # The HTTP attempt has a 0.2s timeout; record_snapshot must return
    # essentially instantly, not wait for that attempt to fail.
    assert elapsed < 0.1
    thread.join(timeout=5)
    tracer.close()


# --- JSON-safety for non-serializable graph state ---------------------------


def test_json_safe_converts_non_serializable_values_to_strings():
    class Unserializable:
        def __str__(self) -> str:
            return "<Unserializable>"

    value = {
        "when": datetime(2024, 1, 1),
        "obj": Unserializable(),
        "nested": {"list": [1, "two", Unserializable()]},
        "fine": "ok",
    }

    safe, warned = _json_safe(value)

    assert warned is True
    assert safe["when"] == str(datetime(2024, 1, 1))
    assert safe["obj"] == "<Unserializable>"
    assert safe["nested"]["list"][2] == "<Unserializable>"
    assert safe["fine"] == "ok"
    json.dumps(safe)  # must not raise


def test_json_safe_reports_no_warning_for_fully_serializable_input():
    safe, warned = _json_safe({"a": 1, "b": ["x", "y"], "c": None, "d": True})
    assert warned is False
    assert safe == {"a": 1, "b": ["x", "y"], "c": None, "d": True}


def test_on_chain_end_with_non_serializable_state_flags_warning_and_does_not_crash():
    class Unserializable:
        pass

    tracer = _mock_tracer()
    adapter = LangGraphAdapter(tracer)

    adapter.on_chain_end({"weird": Unserializable()}, run_id=uuid.uuid4())

    tracer.record_snapshot.assert_called_once()
    snapshot = tracer.record_snapshot.call_args[0][0]
    assert snapshot.metadata.get("_serialization_warning") is True
    json.dumps(snapshot.to_dict())  # must not raise


def test_capture_snapshot_never_raises_even_if_tracer_explodes():
    tracer = _mock_tracer()
    tracer.record_snapshot.side_effect = RuntimeError("boom")
    adapter = LangGraphAdapter(tracer)

    # Must not raise, per the "zero-impact on the agent" constraint.
    adapter.on_chain_end({"messages": []}, run_id=uuid.uuid4())
