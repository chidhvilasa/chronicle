"""Tests for src/integrity.py's hash chain and the GET /runs/{id}/verify endpoint."""

import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from src import integrity
from src.database import Database
from src.main import app

_BASE_TIME = time.time() - 1000.0


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "chronicle.db"
    monkeypatch.setenv("CHRONICLE_DB_PATH", str(path))
    monkeypatch.chdir(tmp_path)
    return path


@pytest.fixture
def client(db_path):
    with TestClient(app) as test_client:
        yield test_client


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


# --- integrity.py: pure hashing functions ------------------------------------


def test_compute_event_hash_is_deterministic():
    event = {"event_id": "e1", "run_id": "r1", "timestamp": 1.0, "event_type": "tool_call", "data": {"a": 1}}
    assert integrity.compute_event_hash(event) == integrity.compute_event_hash(event)


def test_compute_event_hash_is_order_independent_for_data_keys():
    base = {"event_id": "e1", "run_id": "r1", "timestamp": 1.0, "event_type": "tool_call"}
    a = {**base, "data": {"x": 1, "y": 2}}
    b = {**base, "data": {"y": 2, "x": 1}}
    assert integrity.compute_event_hash(a) == integrity.compute_event_hash(b)


def test_compute_event_hash_changes_when_data_changes():
    base = {"event_id": "e1", "run_id": "r1", "timestamp": 1.0, "event_type": "tool_call"}
    a = integrity.compute_event_hash({**base, "data": {"x": 1}})
    b = integrity.compute_event_hash({**base, "data": {"x": 2}})
    assert a != b


def test_compute_chain_hash_depends_on_previous_hash():
    event_hash = "abc"
    first = integrity.compute_chain_hash(event_hash, integrity.GENESIS_CHAIN_HASH)
    second = integrity.compute_chain_hash(event_hash, "different-previous")
    assert first != second


def test_build_chain_produces_one_entry_per_event_in_order():
    events = [
        {"event_id": "e1", "run_id": "r1", "timestamp": 1.0, "event_type": "tool_call", "data": {}},
        {"event_id": "e2", "run_id": "r1", "timestamp": 2.0, "event_type": "tool_call", "data": {}},
    ]
    chain = integrity.build_chain(events)
    assert len(chain) == 2
    event_hash_0, chain_hash_0 = chain[0]
    assert chain_hash_0 == integrity.compute_chain_hash(event_hash_0, integrity.GENESIS_CHAIN_HASH)
    event_hash_1, chain_hash_1 = chain[1]
    assert chain_hash_1 == integrity.compute_chain_hash(event_hash_1, chain_hash_0)


def test_verify_run_events_passes_for_an_untampered_chain():
    events = [
        {"event_id": "e1", "run_id": "r1", "timestamp": 1.0, "event_type": "tool_call", "data": {}},
        {"event_id": "e2", "run_id": "r1", "timestamp": 2.0, "event_type": "tool_call", "data": {}},
    ]
    for event, (event_hash, chain_hash) in zip(events, integrity.build_chain(events)):
        event["event_hash"] = event_hash
        event["chain_hash"] = chain_hash

    result = integrity.verify_run_events("r1", events)
    assert result.ok
    assert result.event_count == 2
    assert result.violations == []


def test_verify_run_events_detects_a_modified_event():
    events = [
        {"event_id": "e1", "run_id": "r1", "timestamp": 1.0, "event_type": "tool_call", "data": {"n": 1}},
        {"event_id": "e2", "run_id": "r1", "timestamp": 2.0, "event_type": "tool_call", "data": {"n": 2}},
    ]
    for event, (event_hash, chain_hash) in zip(events, integrity.build_chain(events)):
        event["event_hash"] = event_hash
        event["chain_hash"] = chain_hash

    events[0]["data"] = {"n": 999}  # tampered after hashing

    result = integrity.verify_run_events("r1", events)
    assert not result.ok
    violation_event_ids = {v.event_id for v in result.violations}
    assert "e1" in violation_event_ids


def test_verify_run_events_detects_a_deleted_event_via_broken_chain():
    events = [
        {"event_id": "e1", "run_id": "r1", "timestamp": 1.0, "event_type": "tool_call", "data": {}},
        {"event_id": "e2", "run_id": "r1", "timestamp": 2.0, "event_type": "tool_call", "data": {}},
        {"event_id": "e3", "run_id": "r1", "timestamp": 3.0, "event_type": "tool_call", "data": {}},
    ]
    for event, (event_hash, chain_hash) in zip(events, integrity.build_chain(events)):
        event["event_hash"] = event_hash
        event["chain_hash"] = chain_hash

    remaining = [events[0], events[2]]  # e2 deleted; e3's stored chain_hash now stale

    result = integrity.verify_run_events("r1", remaining)
    assert not result.ok
    assert any(v.event_id == "e3" for v in result.violations)


def test_verify_run_events_passes_for_an_empty_run():
    result = integrity.verify_run_events("r1", [])
    assert result.ok
    assert result.event_count == 0


# --- Database: hash chain computed and stored on insert -----------------------


async def test_insert_events_stores_a_matching_hash_chain(tmp_path):
    db = Database(db_path=tmp_path / "chronicle.db")
    await db.connect()
    try:
        await db.insert_events(
            [
                {"event_id": "e1", "run_id": "r1", "timestamp": 1.0, "event_type": "tool_call", "data": {}},
                {"event_id": "e2", "run_id": "r1", "timestamp": 2.0, "event_type": "tool_call", "data": {}},
            ]
        )
        events = await db.list_events_with_hashes("r1")
        result = integrity.verify_run_events("r1", events)
        assert result.ok
        assert result.event_count == 2
    finally:
        await db.close()


async def test_recompute_event_chain_handles_out_of_order_inserts(tmp_path):
    """Inserting an earlier-timestamped event after a later one must still produce a
    chain that verifies clean - the chain is always rebuilt in canonical (timestamp)
    order, not insertion order.
    """
    db = Database(db_path=tmp_path / "chronicle.db")
    await db.connect()
    try:
        await db.insert_events(
            [{"event_id": "e2", "run_id": "r1", "timestamp": 2.0, "event_type": "tool_call", "data": {}}]
        )
        await db.insert_events(
            [{"event_id": "e1", "run_id": "r1", "timestamp": 1.0, "event_type": "tool_call", "data": {}}]
        )
        events = await db.list_events_with_hashes("r1")
        assert [e["event_id"] for e in events] == ["e1", "e2"]
        result = integrity.verify_run_events("r1", events)
        assert result.ok
    finally:
        await db.close()


# --- GET /runs/{run_id}/verify --------------------------------------------------


def test_verify_endpoint_404s_for_a_missing_run(client):
    response = client.get("/runs/missing/verify")
    assert response.status_code == 404


def test_verify_endpoint_reports_ok_for_an_untampered_run(client):
    client.post("/events", json=[_event(event_id="evt-1"), _event(event_id="evt-2", timestamp=1001.0)])

    response = client.get("/runs/run-1/verify")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["event_count"] == 2
    assert body["violations"] == []


def test_verify_endpoint_detects_a_directly_edited_event(client, db_path):
    client.post("/events", json=[_event(event_id="evt-1", data={"original": True})])

    raw = sqlite3.connect(db_path)
    raw.execute(
        "UPDATE events SET data = ? WHERE event_id = ?", ('{"tampered": true}', "evt-1")
    )
    raw.commit()
    raw.close()

    response = client.get("/runs/run-1/verify")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert any(v["event_id"] == "evt-1" for v in body["violations"])


def test_verify_endpoint_passes_for_a_run_with_no_events(client):
    client.post("/runs/run-empty/metadata", json={"metadata": {"note": "no events yet"}})
    response = client.get("/runs/run-empty/verify")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["event_count"] == 0
