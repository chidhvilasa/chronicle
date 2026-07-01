import pytest
from fastapi.testclient import TestClient

from chronicle_server.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_DB_PATH", str(tmp_path / "chronicle.db"))
    with TestClient(app) as test_client:
        yield test_client


def _sample_event(run_id: str = "run-1", event_id: str = "evt-1", timestamp: float = 1000.0):
    return {
        "id": event_id,
        "run_id": run_id,
        "parent_id": None,
        "event_type": "tool_call",
        "timestamp": timestamp,
        "payload": {"tool_name": "search"},
    }


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_event_and_list_runs(client):
    response = client.post("/events", json=_sample_event())
    assert response.status_code == 201

    response = client.get("/runs")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    assert runs[0]["id"] == "run-1"
    assert runs[0]["event_count"] == 1


def test_list_run_events(client):
    client.post("/events", json=_sample_event())
    client.post("/events", json=_sample_event(event_id="evt-2", timestamp=1001.0))

    response = client.get("/runs/run-1/events")
    assert response.status_code == 200
    events = response.json()
    assert [e["id"] for e in events] == ["evt-1", "evt-2"]


def test_list_run_events_404(client):
    response = client.get("/runs/missing/events")
    assert response.status_code == 404


def test_get_run_timeline(client):
    client.post("/events", json=_sample_event())
    response = client.get("/runs/run-1/timeline")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_delete_run(client):
    client.post("/events", json=_sample_event())

    response = client.delete("/runs/run-1")
    assert response.status_code == 204

    response = client.get("/runs/run-1/events")
    assert response.status_code == 404


def test_delete_run_404(client):
    response = client.delete("/runs/missing")
    assert response.status_code == 404
