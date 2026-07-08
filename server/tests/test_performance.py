"""Performance stress tests: 7 required latency/throughput thresholds.

All tests share one module-scoped 10k-event run (seeding it once, not per
test, since generating and ingesting 10k events is itself the expensive part).
If a threshold fails on a particular machine, see PERFORMANCE.md - these are
meant to catch algorithmic regressions (an accidental O(n^2) loop, a missing
index), not to be a hard pass/fail gate tied to one machine's absolute speed.
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from src.main import app

EVENT_COUNT = 10_000
BATCH_SIZE = 500

THRESHOLDS_S = {
    "ingest_10k_events": 30.0,
    "get_events": 2.0,
    "get_timeline": 3.0,
    "get_graph": 5.0,
    "get_metrics_overview": 0.5,
    "get_metrics_trends": 1.0,
    "verify": 60.0,
}


def _assert_under(elapsed: float, key: str) -> None:
    threshold = THRESHOLDS_S[key]
    assert elapsed < threshold, (
        f"{key} took {elapsed:.3f}s, exceeding the {threshold}s threshold - "
        f"see PERFORMANCE.md before treating this as a hard failure"
    )


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("perf") / "chronicle.db"
    previous = os.environ.get("CHRONICLE_DB_PATH")
    os.environ["CHRONICLE_DB_PATH"] = str(db_path)
    with TestClient(app) as test_client:
        test_client.perf_db_path = db_path  # type: ignore[attr-defined]
        yield test_client
    if previous is None:
        os.environ.pop("CHRONICLE_DB_PATH", None)
    else:
        os.environ["CHRONICLE_DB_PATH"] = previous


@pytest.fixture(scope="module")
def seeded_run(client):
    """Ingests EVENT_COUNT events for one run, then marks it complete and backfills
    run_metrics so /metrics/overview and /metrics/trends have real data to aggregate.
    """
    run_id = str(uuid.uuid4())
    base_ts = time.time() - 100_000
    event_types = ["tool_call", "llm_call", "agent_message", "memory_update", "error", "retry"]

    events = [
        {
            "event_id": str(uuid.uuid4()),
            "run_id": run_id,
            "timestamp": base_ts + i * 0.05,
            "event_type": event_types[i % len(event_types)],
            "agent_name": f"agent-{i % 5}",
            "data": {"index": i, "note": "perf test payload"},
            "duration_ms": float(10 + (i % 200)),
            "token_usage": {"input_tokens": 20 + (i % 50), "output_tokens": 10 + (i % 30)},
            "error": "boom" if i % 97 == 0 else None,
        }
        for i in range(EVENT_COUNT)
    ]

    start = time.perf_counter()
    for i in range(0, len(events), BATCH_SIZE):
        response = client.post("/events", json=events[i : i + BATCH_SIZE])
        assert response.status_code == 200
    ingest_elapsed = time.perf_counter() - start

    raw = sqlite3.connect(client.perf_db_path)  # type: ignore[attr-defined]
    raw.execute("UPDATE runs SET status = 'complete' WHERE run_id = ?", (run_id,))
    raw.commit()
    raw.close()

    backfill_response = client.post("/metrics/backfill")
    assert backfill_response.status_code == 200

    return {"run_id": run_id, "ingest_elapsed": ingest_elapsed}


# --- 1. Ingest 10k events -------------------------------------------------------


def test_ingest_10k_events_under_threshold(seeded_run):
    _assert_under(seeded_run["ingest_elapsed"], "ingest_10k_events")


# --- 2. GET events ---------------------------------------------------------------


def test_get_events_under_threshold(client, seeded_run):
    start = time.perf_counter()
    response = client.get(f"/runs/{seeded_run['run_id']}/events")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    assert len(response.json()) == EVENT_COUNT
    _assert_under(elapsed, "get_events")


# --- 3. GET timeline --------------------------------------------------------------


def test_get_timeline_under_threshold(client, seeded_run):
    start = time.perf_counter()
    response = client.get(f"/runs/{seeded_run['run_id']}/timeline")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    _assert_under(elapsed, "get_timeline")


# --- 4. GET graph ------------------------------------------------------------------


def test_get_graph_under_threshold(client, seeded_run):
    start = time.perf_counter()
    response = client.get(f"/runs/{seeded_run['run_id']}/graph")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    _assert_under(elapsed, "get_graph")


# --- 5. GET metrics/overview --------------------------------------------------------


def test_get_metrics_overview_under_threshold(client, seeded_run):
    start = time.perf_counter()
    response = client.get("/metrics/overview")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    _assert_under(elapsed, "get_metrics_overview")


# --- 6. GET metrics/trends -----------------------------------------------------------


def test_get_metrics_trends_under_threshold(client, seeded_run):
    start = time.perf_counter()
    response = client.get("/metrics/trends", params={"period": "day", "metric": "tokens"})
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    _assert_under(elapsed, "get_metrics_trends")


# --- 7. chronicle verify -------------------------------------------------------------


def test_verify_under_threshold(client, seeded_run):
    start = time.perf_counter()
    response = client.get(f"/runs/{seeded_run['run_id']}/verify")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["event_count"] == EVENT_COUNT
    _assert_under(elapsed, "verify")
