import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CHRONICLE_DB_PATH", ":memory:")
    with TestClient(app) as test_client:
        yield test_client


def _event(event_id="evt-1", run_id="run-1", timestamp=1000.0, event_type="tool_call", **overrides):
    event = {
        "event_id": event_id,
        "run_id": run_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "agent_name": "agent-a",
        "data": {"tool_name": "search"},
        "duration_ms": 120.0,
        "token_usage": None,
        "error": None,
    }
    event.update(overrides)
    return event


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_create_events_and_list_runs(client):
    response = client.post("/events", json=[_event()])
    assert response.status_code == 200
    assert response.json() == {"count": 1}

    response = client.get("/runs")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    assert runs[0]["run_id"] == "run-1"
    assert runs[0]["agent_count"] == 1
    assert runs[0]["status"] == "running"


def test_create_events_computes_total_tokens_and_error_status(client):
    events = [
        _event(
            event_id="evt-1",
            event_type="llm_call",
            token_usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        ),
        _event(event_id="evt-2", event_type="error", error="boom"),
    ]
    client.post("/events", json=events)

    run = client.get("/runs").json()[0]
    assert run["total_tokens"] == 15
    assert run["status"] == "error"


def test_create_events_handles_large_batch(client):
    events = [_event(event_id=f"evt-{i}", timestamp=1000.0 + i) for i in range(500)]
    response = client.post("/events", json=events)
    assert response.status_code == 200
    assert response.json() == {"count": 500}

    events_response = client.get("/runs/run-1/events")
    assert len(events_response.json()) == 500


def test_list_run_events(client):
    client.post(
        "/events",
        json=[_event(event_id="evt-1", timestamp=1000.0), _event(event_id="evt-2", timestamp=1001.0)],
    )
    response = client.get("/runs/run-1/events")
    assert response.status_code == 200
    events = response.json()
    assert [e["event_id"] for e in events] == ["evt-1", "evt-2"]


def test_list_run_events_404_has_consistent_error_shape(client):
    response = client.get("/runs/missing/events")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "not_found"
    assert "missing" in body["detail"]


def test_get_run_timeline(client):
    client.post("/events", json=[_event()])
    response = client.get("/runs/run-1/timeline")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run-1"
    assert len(body["lanes"]) == 1
    assert body["lanes"][0]["agent_name"] == "agent-a"
    assert body["lanes"][0]["segments"][0]["type"] == "tool_call"


def test_get_run_timeline_404(client):
    response = client.get("/runs/missing/timeline")
    assert response.status_code == 404


def test_get_run_graph(client):
    client.post("/events", json=[_event()])
    response = client.get("/runs/run-1/graph")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run-1"
    node_ids = {n["id"] for n in body["nodes"]}
    assert "agent:agent-a" in node_ids
    assert "tool:search" in node_ids
    assert body["metadata"]["total_nodes"] == len(body["nodes"])
    assert body["metadata"]["total_edges"] == len(body["edges"])


def test_get_run_graph_404(client):
    response = client.get("/runs/missing/graph")
    assert response.status_code == 404


def test_delete_run(client):
    client.post("/events", json=[_event()])

    response = client.delete("/runs/run-1")
    assert response.status_code == 204

    response = client.get("/runs/run-1/events")
    assert response.status_code == 404


def test_delete_run_404(client):
    response = client.delete("/runs/missing")
    assert response.status_code == 404


def test_invalid_event_payload_returns_consistent_error_shape(client):
    response = client.post("/events", json=[{"event_id": "evt-1"}])
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"
    assert "detail" in body and isinstance(body["detail"], str)


def test_cors_allows_tauri_dev_origin(client):
    response = client.options(
        "/runs",
        headers={
            "Origin": "http://localhost:1420",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:1420"
