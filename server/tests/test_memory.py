import time

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.memory_builder import build_memory_snapshots


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CHRONICLE_DB_PATH", ":memory:")
    with TestClient(app) as test_client:
        yield test_client


def _memory_event(event_id="e1", run_id="run-1", timestamp=1000.0, agent_name="agent-a", data=None):
    return {
        "event_id": event_id,
        "run_id": run_id,
        "timestamp": timestamp,
        "event_type": "memory_update",
        "agent_name": agent_name,
        "duration_ms": None,
        "input_tokens": None,
        "output_tokens": None,
        "data": data or {},
        "error": None,
    }


# --- build_memory_snapshots (pure function) --------------------------------------


def test_build_memory_snapshots_detects_added_keys():
    events = [_memory_event(data={"memory_before": {"a": 1}, "memory_after": {"a": 1, "b": 2}})]
    snapshots = build_memory_snapshots(events)
    assert len(snapshots) == 1
    assert snapshots[0]["keys_added"] == ["b"]
    assert snapshots[0]["keys_removed"] == []
    assert snapshots[0]["keys_changed"] == []


def test_build_memory_snapshots_detects_removed_keys():
    events = [_memory_event(data={"memory_before": {"a": 1, "b": 2}, "memory_after": {"a": 1}})]
    snapshots = build_memory_snapshots(events)
    assert snapshots[0]["keys_removed"] == ["b"]


def test_build_memory_snapshots_detects_changed_keys():
    events = [_memory_event(data={"memory_before": {"a": 1}, "memory_after": {"a": 2}})]
    snapshots = build_memory_snapshots(events)
    assert snapshots[0]["keys_changed"] == ["a"]


def test_build_memory_snapshots_detects_nested_dict_changes_as_top_level_key_change():
    events = [
        _memory_event(
            data={
                "memory_before": {"user": {"name": "Alice", "age": 30}},
                "memory_after": {"user": {"name": "Alice", "age": 31}},
            }
        )
    ]
    snapshots = build_memory_snapshots(events)
    assert snapshots[0]["keys_changed"] == ["user"]
    assert snapshots[0]["keys_added"] == []
    assert snapshots[0]["keys_removed"] == []
    # The full nested diff is available via memory_before/memory_after directly.
    assert snapshots[0]["memory_after"]["user"]["age"] == 31


def test_build_memory_snapshots_unchanged_keys_are_not_in_any_diff_list():
    events = [_memory_event(data={"memory_before": {"a": 1, "b": 2}, "memory_after": {"a": 1, "b": 3}})]
    snapshots = build_memory_snapshots(events)
    assert "a" not in snapshots[0]["keys_changed"]
    assert "a" not in snapshots[0]["keys_added"]
    assert "a" not in snapshots[0]["keys_removed"]


def test_build_memory_snapshots_orders_by_timestamp_and_assigns_step_index():
    events = [
        _memory_event(event_id="e2", timestamp=1001.0, data={"memory_before": {}, "memory_after": {"b": 1}}),
        _memory_event(event_id="e1", timestamp=1000.0, data={"memory_before": {}, "memory_after": {"a": 1}}),
    ]
    snapshots = build_memory_snapshots(events)
    assert [s["event_id"] for s in snapshots] == ["e1", "e2"]
    assert [s["step_index"] for s in snapshots] == [0, 1]


def test_build_memory_snapshots_ignores_non_memory_events():
    events = [
        _memory_event(event_id="e1", data={"memory_before": {}, "memory_after": {"a": 1}}),
        {**_memory_event(event_id="e2"), "event_type": "tool_call"},
    ]
    assert len(build_memory_snapshots(events)) == 1


def test_build_memory_snapshots_empty_for_no_events():
    assert build_memory_snapshots([]) == []


def test_build_memory_snapshots_defaults_missing_before_after_to_empty_dict():
    events = [_memory_event(data={})]
    snapshots = build_memory_snapshots(events)
    assert snapshots[0]["memory_before"] == {}
    assert snapshots[0]["memory_after"] == {}
    assert snapshots[0]["keys_added"] == []


# --- HTTP endpoint -----------------------------------------------------------------


def test_get_run_memory_returns_snapshots(client):
    client.post(
        "/events",
        json=[
            {
                "event_id": "e1",
                "run_id": "run-1",
                "timestamp": time.time(),
                "event_type": "memory_update",
                "agent_name": "agent-a",
                "data": {"memory_before": {"a": 1}, "memory_after": {"a": 1, "b": 2}},
                "duration_ms": None,
                "token_usage": None,
                "error": None,
            }
        ],
    )
    response = client.get("/runs/run-1/memory")
    assert response.status_code == 200
    body = response.json()
    assert body["message"] is None
    assert len(body["snapshots"]) == 1
    assert body["snapshots"][0]["keys_added"] == ["b"]


def test_get_run_memory_returns_message_when_empty(client):
    client.post(
        "/events",
        json=[
            {
                "event_id": "e1",
                "run_id": "run-1",
                "timestamp": time.time(),
                "event_type": "tool_call",
                "agent_name": "agent-a",
                "data": {},
                "duration_ms": None,
                "token_usage": None,
                "error": None,
            }
        ],
    )
    response = client.get("/runs/run-1/memory")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshots"] == []
    assert "chronicle-sdk 0.7.0" in body["message"]


def test_get_run_memory_404_for_missing_run(client):
    response = client.get("/runs/missing/memory")
    assert response.status_code == 404
