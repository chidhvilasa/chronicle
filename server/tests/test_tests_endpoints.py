"""Tests for the regression test engine's storage endpoints: POST/GET/DELETE /tests,
GET /tests/{id}/history, and POST /tests/{id}/run.
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
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as test_client:
        yield test_client


class _MockGraph:
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
    module_name = "chronicle_test_fixture_tests_graph"
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


def _test_payload(**overrides):
    payload = {
        "name": "greets the user",
        "source_run_id": "run-1",
        "source_snapshot_id": "snap-1",
        "assertions": [
            {"assertion_type": "no_errors", "target": ""},
        ],
    }
    payload.update(overrides)
    return payload


# --- CRUD ---------------------------------------------------------------------


def test_create_test_404s_when_source_run_does_not_exist(client):
    response = client.post("/tests", json=_test_payload())
    assert response.status_code == 404


def test_create_test_succeeds_for_an_existing_run(client):
    client.post("/events", json=[_event()])

    response = client.post("/tests", json=_test_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "greets the user"
    assert body["source_run_id"] == "run-1"
    assert body["last_result"] is None
    assert body["last_run_at"] is None
    assert len(body["assertions"]) == 1


def test_list_tests_orders_by_created_at_desc(client):
    client.post("/events", json=[_event()])
    client.post("/tests", json=_test_payload(name="first"))
    client.post("/tests", json=_test_payload(name="second"))

    response = client.get("/tests")
    assert response.status_code == 200
    names = [t["name"] for t in response.json()]
    assert names == ["second", "first"]


def test_get_test_returns_full_detail(client):
    client.post("/events", json=[_event()])
    created = client.post("/tests", json=_test_payload()).json()

    response = client.get(f"/tests/{created['test_id']}")
    assert response.status_code == 200
    assert response.json()["test_id"] == created["test_id"]


def test_get_test_404_for_missing_test(client):
    response = client.get("/tests/missing")
    assert response.status_code == 404


def test_delete_test_removes_it(client):
    client.post("/events", json=[_event()])
    created = client.post("/tests", json=_test_payload()).json()

    response = client.delete(f"/tests/{created['test_id']}")
    assert response.status_code == 204
    assert client.get(f"/tests/{created['test_id']}").status_code == 404


def test_delete_test_404_for_missing_test(client):
    response = client.delete("/tests/missing")
    assert response.status_code == 404


def test_history_404_for_missing_test(client):
    response = client.get("/tests/missing/history")
    assert response.status_code == 404


def test_history_is_empty_before_any_run(client):
    client.post("/events", json=[_event()])
    created = client.post("/tests", json=_test_payload()).json()

    response = client.get(f"/tests/{created['test_id']}/history")
    assert response.status_code == 200
    assert response.json() == []


# --- POST /tests/{id}/run -------------------------------------------------------


def test_run_test_400s_without_a_registered_graph(client):
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot()])
    created = client.post("/tests", json=_test_payload()).json()

    response = client.post(f"/tests/{created['test_id']}/run")
    assert response.status_code == 400


def test_run_test_404s_for_a_missing_test(client):
    response = client.post("/tests/missing/run")
    assert response.status_code == 404


def test_run_test_evaluates_assertions_and_stores_result(client, mock_graph):
    module_name, _graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot()])
    created = client.post("/tests", json=_test_payload()).json()

    response = client.post(f"/tests/{created['test_id']}/run")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pass"
    assert body["passed"] is True
    assert body["replay_run_id"] is not None
    assert body["replay_run_id"] != "run-1"
    assert len(body["assertion_results"]) == 1
    assert body["assertion_results"][0]["assertion_type"] == "no_errors"

    updated_test = client.get(f"/tests/{created['test_id']}").json()
    assert updated_test["last_result"] == "pass"
    assert updated_test["last_run_at"] is not None

    history = client.get(f"/tests/{created['test_id']}/history").json()
    assert len(history) == 1
    assert history[0]["status"] == "pass"


def test_run_test_stamps_replay_run_with_triggered_by_test_metadata(client, mock_graph):
    module_name, _graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot()])
    created = client.post("/tests", json=_test_payload()).json()

    response = client.post(f"/tests/{created['test_id']}/run")
    replay_run_id = response.json()["replay_run_id"]

    replay_run = next(r for r in client.get("/runs").json() if r["run_id"] == replay_run_id)
    assert replay_run["metadata"]["triggered_by"] == "test"
    assert replay_run["metadata"]["test_id"] == created["test_id"]


def test_run_test_never_modifies_the_source_run(client, mock_graph):
    module_name, _graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot()])
    created = client.post("/tests", json=_test_payload()).json()

    before = client.get("/runs/run-1/events").json()
    client.post(f"/tests/{created['test_id']}/run")
    after = client.get("/runs/run-1/events").json()

    assert before == after


def test_run_test_resolves_step_zero_snapshot_when_none_specified(client, mock_graph):
    module_name, _graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot(step_index=0)])
    created = client.post("/tests", json=_test_payload(source_snapshot_id=None)).json()

    response = client.post(f"/tests/{created['test_id']}/run")
    assert response.status_code == 200
    assert response.json()["status"] == "pass"


def test_run_test_marks_error_when_replay_run_fails(client):
    module_name = "chronicle_test_fixture_tests_failing_graph"
    module = types.ModuleType(module_name)
    module.graph = _MockGraph(error=RuntimeError("boom"))  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    try:
        client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
        client.post("/events", json=[_event()])
        client.post("/snapshots", json=[_snapshot()])
        created = client.post("/tests", json=_test_payload()).json()

        response = client.post(f"/tests/{created['test_id']}/run")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        assert body["passed"] is False
        assert body["error_reason"] is not None
    finally:
        del sys.modules[module_name]


def test_run_test_with_failing_assertion_marks_test_failed(client, mock_graph):
    # The mock graph's invoke() never calls the tracer, so the replay run
    # always has zero events - a "tool_called" assertion against it always
    # fails, which is exactly what this test exercises.
    module_name, _graph = mock_graph
    client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    client.post("/events", json=[_event()])
    client.post("/snapshots", json=[_snapshot()])
    created = client.post(
        "/tests",
        json=_test_payload(
            assertions=[{"assertion_type": "tool_called", "target": "search"}]
        ),
    ).json()

    response = client.post(f"/tests/{created['test_id']}/run")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "fail"
    assert body["passed"] is False
    assert body["assertion_results"][0]["passed"] is False
