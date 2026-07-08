"""Tests for the replay engine: graph registration, snapshot endpoints, and POST /replay.

Uses a fake importable module (injected into `sys.modules`) standing in for
a real LangGraph graph, so these tests never need a real LLM or a real
LangGraph installation.
"""

import sys
import time
import types

import pytest
from fastapi.testclient import TestClient

from src.main import app

# See test_endpoints.py's _BASE_TIME comment: rebases small relative-offset test
# timestamps onto real wall-clock time so they pass POST /events' timestamp-window check.
_BASE_TIME = time.time() - 1000.0


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_DB_PATH", str(tmp_path / "chronicle.db"))
    # Keeps any chronicle_runs/ fallback writes (from the replay's own
    # ChronicleTracer, if it can't reach a real server) inside the test's
    # throwaway directory instead of the repo.
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as test_client:
        yield test_client


class _MockGraph:
    """Stands in for a compiled LangGraph graph: just records what it's invoked with."""

    def __init__(self, result=None, error=None):
        self.invoke_calls: list[tuple[dict, object]] = []
        self._result = result if result is not None else {}
        self._error = error

    def invoke(self, state, config=None):
        self.invoke_calls.append((dict(state), config))
        if self._error is not None:
            raise self._error
        return self._result


@pytest.fixture
def mock_graph():
    """Installs a fake importable module exposing a mock graph as `.graph`, then cleans up."""
    module_name = "chronicle_test_fixture_graph"
    module = types.ModuleType(module_name)
    graph = _MockGraph()
    module.graph = graph  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    yield module_name, graph
    del sys.modules[module_name]


def _event(event_id="evt-1", run_id="run-1", timestamp=1000.0, event_type="tool_call", **overrides):
    event = {
        "event_id": event_id,
        "run_id": run_id,
        "timestamp": _BASE_TIME + timestamp,
        "event_type": event_type,
        "agent_name": "agent-a",
        "data": {},
        "duration_ms": None,
        "token_usage": None,
        "error": None,
    }
    event.update(overrides)
    return event


def _snapshot(snapshot_id="snap-1", run_id="run-1", step_index=0, **overrides):
    snapshot = {
        "snapshot_id": snapshot_id,
        "run_id": run_id,
        "event_id": "evt-1",
        "step_index": step_index,
        "timestamp": 1000.0,
        "agent_name": "agent-a",
        "messages": [{"role": "user", "content": "hi"}],
        "tool_results": [],
        "graph_state": {"messages": [{"role": "user", "content": "hi"}]},
        "metadata": {},
    }
    snapshot.update(overrides)
    return snapshot


# --- Graph registration ------------------------------------------------------


def test_register_graph_succeeds_for_an_importable_module(client, mock_graph):
    module_name, _graph = mock_graph
    response = client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    assert response.status_code == 200
    assert response.json() == {"name": f"{module_name}.graph"}


def test_register_graph_returns_a_clear_error_for_an_unimportable_module(client):
    response = client.post(
        "/register", json={"graph_module": "definitely_not_a_real_module", "graph_attr": "graph"}
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"
    assert "definitely_not_a_real_module" in body["detail"]
    assert "Python path" in body["detail"]


def test_register_graph_returns_a_clear_error_for_a_missing_attribute(client, mock_graph):
    module_name, _graph = mock_graph
    response = client.post(
        "/register", json={"graph_module": module_name, "graph_attr": "not_an_attr"}
    )
    assert response.status_code == 400


def test_registry_lists_registered_graphs(client, mock_graph):
    module_name, _graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    response = client.get("/registry")
    assert response.status_code == 200
    assert response.json() == [f"{module_name}.graph"]


def test_registry_is_empty_before_anything_is_registered(client):
    response = client.get("/registry")
    assert response.status_code == 200
    assert response.json() == []


# --- GET /runs/{id}/snapshots and snapshot detail ----------------------------


def test_list_run_snapshots_returns_correct_step_order(client):
    client.post("/events", json=[_event()])
    client.post(
        "/snapshots",
        json=[
            _snapshot(snapshot_id="snap-2", step_index=2),
            _snapshot(snapshot_id="snap-0", step_index=0),
            _snapshot(snapshot_id="snap-1", step_index=1),
        ],
    )

    response = client.get("/runs/run-1/snapshots")
    assert response.status_code == 200
    body = response.json()
    assert [s["step_index"] for s in body] == [0, 1, 2]
    assert [s["snapshot_id"] for s in body] == ["snap-0", "snap-1", "snap-2"]
    assert "graph_state" not in body[0]
    assert "messages" not in body[0]


def test_list_run_snapshots_404_for_a_missing_run(client):
    response = client.get("/runs/missing/snapshots")
    assert response.status_code == 404


def test_get_run_snapshot_returns_full_detail(client):
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot(graph_state={"foo": "bar"})])

    response = client.get("/runs/run-1/snapshots/snap-1")
    assert response.status_code == 200
    body = response.json()
    assert body["graph_state"] == {"foo": "bar"}
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_get_run_snapshot_404_for_a_missing_snapshot(client):
    client.post("/events", json=[_event()])
    response = client.get("/runs/run-1/snapshots/missing")
    assert response.status_code == 404


# --- POST /replay -------------------------------------------------------------


def test_replay_without_a_registered_graph_returns_400_with_the_documented_message(client):
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot()])

    response = client.post(
        "/replay", json={"run_id": "run-1", "snapshot_id": "snap-1", "modifications": {}}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == (
        "No graph registered. Call tracer.register_graph() before replaying."
    )


def test_replay_returns_404_for_a_missing_snapshot(client, mock_graph):
    module_name, _graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})

    response = client.post(
        "/replay", json={"run_id": "run-1", "snapshot_id": "missing", "modifications": {}}
    )
    assert response.status_code == 404


def test_replay_returns_a_new_run_id(client, mock_graph):
    module_name, _graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot()])

    response = client.post(
        "/replay", json={"run_id": "run-1", "snapshot_id": "snap-1", "modifications": {}}
    )
    assert response.status_code == 200
    new_run_id = response.json()["run_id"]
    assert new_run_id
    assert new_run_id != "run-1"


def test_replay_sets_is_replay_metadata_on_the_new_run(client, mock_graph):
    module_name, _graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot(step_index=2)])

    response = client.post(
        "/replay", json={"run_id": "run-1", "snapshot_id": "snap-1", "modifications": {}}
    )
    new_run_id = response.json()["run_id"]

    replay_run = next(r for r in client.get("/runs").json() if r["run_id"] == new_run_id)
    assert replay_run["metadata"]["is_replay"] is True
    assert replay_run["metadata"]["source_run_id"] == "run-1"
    assert replay_run["metadata"]["source_snapshot_id"] == "snap-1"
    assert replay_run["metadata"]["step_index"] == 2


def test_replay_applies_modifications_to_graph_state_before_invoking(client, mock_graph):
    module_name, graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    client.post("/events", json=[_event()])
    client.post(
        "/snapshots",
        json=[_snapshot(graph_state={"messages": [{"role": "user", "content": "original"}]})],
    )

    client.post(
        "/replay",
        json={
            "run_id": "run-1",
            "snapshot_id": "snap-1",
            "modifications": {"messages": [{"role": "user", "content": "modified"}]},
        },
    )

    assert len(graph.invoke_calls) == 1
    state_passed_to_invoke, _config = graph.invoke_calls[0]
    assert state_passed_to_invoke["messages"] == [{"role": "user", "content": "modified"}]


def test_replay_as_is_passes_the_unmodified_snapshot_state(client, mock_graph):
    module_name, graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot(graph_state={"messages": ["original"]})])

    client.post("/replay", json={"run_id": "run-1", "snapshot_id": "snap-1", "modifications": {}})

    state_passed_to_invoke, _config = graph.invoke_calls[0]
    assert state_passed_to_invoke == {"messages": ["original"]}


def test_replay_marks_the_new_run_complete_on_success(client, mock_graph):
    module_name, _graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot()])

    response = client.post(
        "/replay", json={"run_id": "run-1", "snapshot_id": "snap-1", "modifications": {}}
    )
    new_run_id = response.json()["run_id"]

    replay_run = next(r for r in client.get("/runs").json() if r["run_id"] == new_run_id)
    assert replay_run["status"] == "complete"


def test_replay_marks_the_new_run_failed_when_the_graph_raises(client, tmp_path, monkeypatch):
    module_name = "chronicle_test_fixture_failing_graph"
    module = types.ModuleType(module_name)
    module.graph = _MockGraph(error=RuntimeError("boom"))  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    try:
        client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
        client.post("/events", json=[_event()])
        client.post("/snapshots", json=[_snapshot()])

        response = client.post(
            "/replay", json={"run_id": "run-1", "snapshot_id": "snap-1", "modifications": {}}
        )
        new_run_id = response.json()["run_id"]

        replay_run = next(r for r in client.get("/runs").json() if r["run_id"] == new_run_id)
        assert replay_run["status"] == "failed"
    finally:
        del sys.modules[module_name]


def test_replay_uses_the_snapshots_agent_name_for_the_replayed_adapter(client, mock_graph):
    module_name, graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot(agent_name="planner")])

    response = client.post(
        "/replay", json={"run_id": "run-1", "snapshot_id": "snap-1", "modifications": {}}
    )
    assert response.status_code == 200
    # No direct assertion on the adapter's agent_name (internal), but this
    # exercises the path where agent_name is read off the snapshot without
    # raising.
    assert len(graph.invoke_calls) == 1
