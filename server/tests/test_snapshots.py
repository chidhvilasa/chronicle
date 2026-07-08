import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CHRONICLE_DB_PATH", ":memory:")
    with TestClient(app) as test_client:
        yield test_client


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
        "graph_state": {"foo": "bar"},
        "metadata": {},
    }
    snapshot.update(overrides)
    return snapshot


def test_create_snapshots_returns_count(client):
    response = client.post("/snapshots", json=[_snapshot()])
    assert response.status_code == 200
    assert response.json() == {"count": 1}


def test_create_snapshots_accepts_a_batch(client):
    snapshots = [_snapshot(snapshot_id=f"snap-{i}", step_index=i) for i in range(5)]
    response = client.post("/snapshots", json=snapshots)
    assert response.status_code == 200
    assert response.json() == {"count": 5}


def test_create_snapshots_accepts_empty_batch(client):
    response = client.post("/snapshots", json=[])
    assert response.status_code == 200
    assert response.json() == {"count": 0}


def test_create_snapshots_accepts_large_graph_state(client):
    # ~1MB graph_state, per the "snapshots can be up to 1MB" constraint.
    large_state = {"data": "x" * (1024 * 1024)}
    response = client.post("/snapshots", json=[_snapshot(graph_state=large_state)])
    assert response.status_code == 200
    assert response.json() == {"count": 1}


def test_create_snapshots_defaults_optional_fields(client):
    minimal = {
        "snapshot_id": "snap-min",
        "run_id": "run-1",
        "step_index": 0,
        "timestamp": 1000.0,
    }
    response = client.post("/snapshots", json=[minimal])
    assert response.status_code == 200
    assert response.json() == {"count": 1}


def test_create_snapshots_invalid_payload_returns_consistent_error_shape(client):
    response = client.post("/snapshots", json=[{"snapshot_id": "snap-1"}])
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"
    assert "detail" in body and isinstance(body["detail"], str)


def test_create_snapshots_persists_to_the_snapshots_table(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_DB_PATH", str(tmp_path / "chronicle.db"))
    with TestClient(app) as file_client:
        file_client.post(
            "/snapshots",
            json=[
                _snapshot(
                    snapshot_id="snap-1",
                    run_id="run-1",
                    step_index=3,
                    graph_state={"foo": "bar"},
                    messages=[{"role": "user", "content": "hi"}],
                )
            ],
        )

    conn = sqlite3.connect(tmp_path / "chronicle.db")
    row = conn.execute(
        "SELECT snapshot_id, run_id, event_id, step_index, agent_name, "
        "graph_state, messages, tool_results, metadata FROM snapshots WHERE snapshot_id = ?",
        ("snap-1",),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "snap-1"
    assert row[1] == "run-1"
    assert row[2] == "evt-1"
    assert row[3] == 3
    assert row[4] == "agent-a"
    assert json.loads(row[5]) == {"foo": "bar"}
    assert json.loads(row[6]) == [{"role": "user", "content": "hi"}]
    assert json.loads(row[7]) == []
    assert json.loads(row[8]) == {}


def test_delete_run_also_deletes_its_snapshots(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_DB_PATH", str(tmp_path / "chronicle.db"))
    with TestClient(app) as file_client:
        file_client.post("/events", json=[
            {
                "event_id": "evt-1",
                "run_id": "run-1",
                "timestamp": time.time(),
                "event_type": "tool_call",
                "agent_name": "agent-a",
                "data": {},
                "duration_ms": None,
                "token_usage": None,
                "error": None,
            }
        ])
        file_client.post("/snapshots", json=[_snapshot()])
        file_client.delete("/runs/run-1")

    conn = sqlite3.connect(tmp_path / "chronicle.db")
    count = conn.execute("SELECT COUNT(*) FROM snapshots WHERE run_id = ?", ("run-1",)).fetchone()[0]
    conn.close()
    assert count == 0
