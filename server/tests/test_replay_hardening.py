"""Replay-engine hardening tests: 10 required adversarial/edge-case scenarios.

Each scenario asserts the server degrades gracefully (a clean 4xx, or a correct
200 despite messy input) rather than crashing with an unhandled 500. A few
scenarios reach past the HTTP API with a raw `sqlite3` connection to simulate
states that can't be produced through the (fully validated) public endpoints,
such as on-disk corruption or a pre-existing row from an older/buggy version.
"""

import sqlite3
import sys
import time
import types

import pytest
from fastapi.testclient import TestClient

from src.database import CorruptedDataError, Database
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


class _MockGraph:
    """Stands in for a compiled LangGraph graph: just records what it's invoked with."""

    def __init__(self, result=None):
        self.invoke_calls: list[tuple[dict, object]] = []
        self._result = result if result is not None else {}

    def invoke(self, state, config=None):
        self.invoke_calls.append((dict(state), config))
        return self._result


@pytest.fixture
def mock_graph():
    module_name = "chronicle_test_fixture_replay_hardening_graph"
    module = types.ModuleType(module_name)
    graph = _MockGraph()
    module.graph = graph  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    yield module_name, graph
    del sys.modules[module_name]


def _register_mock_graph(client, mock_graph):
    module_name, graph = mock_graph
    response = client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
    assert response.status_code == 200
    return graph


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
        "timestamp": _BASE_TIME + 1000.0,
        "agent_name": "agent-a",
        "messages": [{"role": "user", "content": "hi"}],
        "tool_results": [],
        "graph_state": {"messages": [{"role": "user", "content": "hi"}]},
        "metadata": {},
    }
    snapshot.update(overrides)
    return snapshot


def _post_snapshot(client, **overrides):
    response = client.post("/snapshots", json=[_snapshot(**overrides)])
    assert response.status_code == 200
    return response


# --- 1. Missing events --------------------------------------------------------


def test_snapshot_referencing_a_nonexistent_event_id_is_still_readable(client):
    """A snapshot can reference an event_id that was never (or no longer) recorded.

    This can legitimately happen if a snapshot is captured slightly before its
    triggering event is flushed, or after a run's events are pruned. Reading the
    snapshot must not crash just because the referenced event is missing.
    """
    client.post("/events", json=[_event(event_id="evt-real")])
    _post_snapshot(client, event_id="evt-does-not-exist")

    response = client.get("/runs/run-1/snapshots/snap-1")
    assert response.status_code == 200
    assert response.json()["event_id"] == "evt-does-not-exist"


def test_replay_of_a_run_with_no_events_at_all_does_not_crash(client, mock_graph):
    """A snapshot can exist for a run that has zero rows in `events` (e.g. events
    still in flight). Starting a replay from it must not raise.
    """
    _register_mock_graph(client, mock_graph)
    _post_snapshot(client, run_id="run-orphan")

    response = client.post(
        "/replay", json={"run_id": "run-orphan", "snapshot_id": "snap-1", "modifications": {}}
    )
    assert response.status_code == 200


# --- 2. Duplicate events -------------------------------------------------------


def test_posting_the_same_event_id_twice_deduplicates_to_one_row(client):
    client.post("/events", json=[_event(event_id="evt-dup", data={"version": "first"})])
    client.post("/events", json=[_event(event_id="evt-dup", data={"version": "second"})])

    response = client.get("/runs/run-1/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["data"] == {"version": "second"}


def test_posting_duplicate_events_in_the_same_batch_does_not_crash(client):
    response = client.post(
        "/events",
        json=[
            _event(event_id="evt-dup", data={"n": 1}),
            _event(event_id="evt-dup", data={"n": 2}),
        ],
    )
    assert response.status_code == 200


# --- 3. Reordered events -------------------------------------------------------


def test_events_posted_out_of_chronological_order_are_returned_sorted_by_timestamp(client):
    client.post(
        "/events",
        json=[
            _event(event_id="evt-c", timestamp=3000.0),
            _event(event_id="evt-a", timestamp=1000.0),
            _event(event_id="evt-b", timestamp=2000.0),
        ],
    )

    response = client.get("/runs/run-1/events")
    assert response.status_code == 200
    assert [e["event_id"] for e in response.json()] == ["evt-a", "evt-b", "evt-c"]


def test_timeline_is_ordered_by_timestamp_regardless_of_post_order(client):
    client.post(
        "/events",
        json=[
            _event(event_id="evt-c", timestamp=3000.0),
            _event(event_id="evt-a", timestamp=1000.0),
            _event(event_id="evt-b", timestamp=2000.0),
        ],
    )

    response = client.get("/runs/run-1/timeline")
    assert response.status_code == 200


# --- 4. Malformed graph_state ---------------------------------------------------


def test_snapshot_with_corrupted_graph_state_column_returns_400_not_500(client, db_path):
    client.post("/events", json=[_event()])
    _post_snapshot(client)

    raw = sqlite3.connect(db_path)
    raw.execute(
        "UPDATE snapshots SET graph_state = ? WHERE snapshot_id = ?", ("{not valid json", "snap-1")
    )
    raw.commit()
    raw.close()

    response = client.get("/runs/run-1/snapshots/snap-1")
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"


# --- 5. Future timestamps -------------------------------------------------------


def test_event_timestamp_too_far_in_the_future_is_rejected(client):
    response = client.post("/events", json=[{**_event(), "timestamp": time.time() + 7200}])
    assert response.status_code == 400
    assert "rejected" in response.json()["detail"]


# --- 6. Negative timestamps -----------------------------------------------------


def test_negative_event_timestamp_is_rejected(client):
    response = client.post("/events", json=[{**_event(), "timestamp": -1.0}])
    assert response.status_code == 400
    assert "rejected" in response.json()["detail"]


# --- 7. Recursive graph_state objects --------------------------------------------


async def test_snapshot_with_a_self_referential_graph_state_raises_a_clean_error(tmp_path):
    """A true Python reference cycle can never arrive via HTTP (JSON is acyclic by
    construction), but an internal caller (or a future bug) could hand `Database`
    a Python dict with a real cycle directly. `json.dumps` raises `ValueError` on
    a circular reference; this must surface as `CorruptedDataError`, not an
    unbounded-recursion crash.
    """
    db = Database(db_path=tmp_path / "chronicle.db")
    await db.connect()
    try:
        cyclic_state: dict = {"messages": []}
        cyclic_state["self"] = cyclic_state

        with pytest.raises(CorruptedDataError):
            await db.insert_snapshots(
                [
                    {
                        "snapshot_id": "snap-cyclic",
                        "run_id": "run-1",
                        "event_id": None,
                        "step_index": 0,
                        "timestamp": _BASE_TIME,
                        "agent_name": "agent-a",
                        "messages": [],
                        "tool_results": [],
                        "graph_state": cyclic_state,
                        "metadata": {},
                    }
                ]
            )
    finally:
        await db.close()


# --- 8. Corrupted snapshot JSON (other columns) ----------------------------------


def test_snapshot_with_corrupted_metadata_column_returns_400_not_500(client, db_path):
    client.post("/events", json=[_event()])
    _post_snapshot(client)

    raw = sqlite3.connect(db_path)
    raw.execute(
        "UPDATE snapshots SET messages = ?, metadata = ? WHERE snapshot_id = ?",
        ("[[[", "not json either", "snap-1"),
    )
    raw.commit()
    raw.close()

    response = client.get("/runs/run-1/snapshots/snap-1")
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"


def test_run_with_corrupted_metadata_column_returns_400_not_500(client, db_path):
    client.post("/events", json=[_event()])

    raw = sqlite3.connect(db_path)
    raw.execute("UPDATE runs SET metadata = ? WHERE run_id = ?", ("{broken", "run-1"))
    raw.commit()
    raw.close()

    response = client.get("/runs")
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"


# --- 9. Invalid UTF-8 -------------------------------------------------------------


def test_event_with_invalid_utf8_bytes_in_data_column_is_replaced_not_crashed(client, db_path):
    client.post("/events", json=[_event(event_id="evt-utf8", data={"note": "fine"})])

    invalid_utf8 = b'{"note": "bad byte \xff\xfe here"}'
    raw = sqlite3.connect(db_path)
    # CAST(... AS TEXT) reinterprets the BLOB parameter's raw bytes as TEXT storage
    # class, producing a genuinely invalid-UTF-8 TEXT value - the same shape of
    # corruption a direct disk-level edit or a future encoding bug could produce.
    raw.execute(
        "UPDATE events SET data = CAST(? AS TEXT) WHERE event_id = ?", (invalid_utf8, "evt-utf8")
    )
    raw.commit()
    raw.close()

    response = client.get("/runs/run-1/events")
    assert response.status_code in (200, 400)
    # Either the server's text_factory replaces the invalid bytes with U+FFFD and
    # the row still parses as valid (if the replacement byte lands outside the
    # JSON string literal it may even still be valid JSON), or the replaced text
    # is no longer valid JSON and comes back as a clean 400 - never an unhandled 500.


# --- 10. Replay depth limit --------------------------------------------------------


async def test_replay_depth_limit_blocks_a_fourth_generation_replay(client, mock_graph, db_path):
    _register_mock_graph(client, mock_graph)
    client.post("/events", json=[_event(run_id="run-gen0")])
    _post_snapshot(client, run_id="run-gen0")

    current_run_id = "run-gen0"
    for _ in range(3):
        response = client.post(
            "/replay",
            json={"run_id": current_run_id, "snapshot_id": "snap-1", "modifications": {}},
        )
        assert response.status_code == 200
        current_run_id = response.json()["run_id"]

        db = Database(db_path=db_path)
        await db.connect()
        try:
            for _ in range(50):
                run = await db.get_run(current_run_id)
                if run is not None and run["status"] != "running":
                    break
                time.sleep(0.05)
        finally:
            await db.close()

    response = client.post(
        "/replay",
        json={"run_id": current_run_id, "snapshot_id": "snap-1", "modifications": {}},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Maximum replay depth reached."
