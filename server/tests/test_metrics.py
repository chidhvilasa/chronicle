"""Tests for the performance metrics aggregation layer: `Database.compute_run_metrics`
and the `GET/POST /metrics/*` endpoints.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import src.database as database_module
from src.main import _compute_metrics_if_complete, app

# See test_endpoints.py's _BASE_TIME comment: rebases small relative-offset test
# timestamps onto real wall-clock time so they pass POST /events' timestamp-window check.
_BASE_TIME = time.time() - 1000.0


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_DB_PATH", str(tmp_path / "chronicle.db"))
    monkeypatch.chdir(tmp_path)
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


# --- Database.compute_run_metrics ---------------------------------------------


async def test_compute_run_metrics_aggregates_events_correctly(client):
    client.post(
        "/events",
        json=[
            _event(
                event_id="e1",
                event_type="llm_call",
                timestamp=1000.0,
                duration_ms=100.0,
                token_usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
                data={"model": "gpt-4"},
            ),
            _event(
                event_id="e2",
                event_type="llm_call",
                timestamp=1001.0,
                duration_ms=300.0,
                token_usage={"input_tokens": 5, "output_tokens": 15, "total_tokens": 20},
                data={"model": "gpt-3.5-turbo"},
            ),
            _event(
                event_id="e3",
                event_type="tool_call",
                timestamp=1002.0,
                duration_ms=50.0,
                data={"tool_name": "search"},
            ),
            _event(event_id="e4", event_type="error", timestamp=1003.0, error="boom"),
            _event(event_id="e5", event_type="retry", timestamp=1004.0),
        ],
    )

    metrics = await app.state.db.compute_run_metrics("run-1")

    assert metrics is not None
    assert metrics["llm_call_count"] == 2
    assert metrics["tool_call_count"] == 1
    assert metrics["error_count"] == 1
    assert metrics["retry_count"] == 1
    assert metrics["total_input_tokens"] == 15
    assert metrics["total_output_tokens"] == 35
    assert metrics["total_tokens"] == 50
    # gpt-4 event: 10 * 0.00001 + 20 * 0.00003 = 0.0007
    # gpt-3.5 event (default rate): 5 * 0.000003 + 15 * 0.000015 = 0.00024
    assert metrics["estimated_cost_usd"] == pytest.approx(0.00094)
    assert metrics["avg_llm_latency_ms"] == pytest.approx(200.0)
    assert metrics["avg_tool_latency_ms"] == pytest.approx(50.0)
    assert metrics["p95_llm_latency_ms"] is not None
    assert metrics["agent_count"] == 1


async def test_compute_run_metrics_is_idempotent_and_reflects_new_events(client):
    client.post("/events", json=[_event(event_id="e1", event_type="tool_call", duration_ms=10.0)])
    first = await app.state.db.compute_run_metrics("run-1")
    assert first["tool_call_count"] == 1

    client.post("/events", json=[_event(event_id="e2", event_type="tool_call", duration_ms=20.0)])
    second = await app.state.db.compute_run_metrics("run-1")
    assert second["tool_call_count"] == 2


async def test_compute_run_metrics_404_equivalent_for_missing_run(client):
    result = await app.state.db.compute_run_metrics("no-such-run")
    assert result is None


# --- GET /metrics/overview -----------------------------------------------------


async def test_metrics_overview_returns_correct_totals(client):
    client.post(
        "/events",
        json=[
            _event(
                event_id="e1",
                run_id="run-1",
                event_type="llm_call",
                duration_ms=100.0,
                token_usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
                data={"model": "gpt-4"},
            )
        ],
    )
    await app.state.db.set_run_status("run-1", "complete")
    await app.state.db.compute_run_metrics("run-1")

    client.post(
        "/events",
        json=[_event(event_id="e2", run_id="run-2", event_type="tool_call", duration_ms=20.0)],
    )
    await app.state.db.set_run_status("run-2", "complete")
    await app.state.db.compute_run_metrics("run-2")

    response = client.get("/metrics/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["total_runs"] == 2
    assert body["total_tokens"] == 30
    assert body["total_errors"] == 0
    assert body["cost_is_estimate"] is True
    assert body["most_expensive_run_id"] == "run-1"


async def test_metrics_overview_is_empty_before_any_complete_run(client):
    response = client.get("/metrics/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["total_runs"] == 0
    assert body["total_tokens"] == 0
    assert body["most_expensive_run_id"] is None
    assert body["slowest_run_id"] is None


# --- GET /metrics/trends --------------------------------------------------------


async def test_metrics_trends_buckets_by_day(client, monkeypatch):
    client.post(
        "/events",
        json=[
            _event(
                event_id="e1",
                run_id="run-1",
                event_type="llm_call",
                token_usage={"input_tokens": 10, "output_tokens": 0, "total_tokens": 10},
            )
        ],
    )
    client.post(
        "/events",
        json=[
            _event(
                event_id="e2",
                run_id="run-2",
                event_type="llm_call",
                token_usage={"input_tokens": 20, "output_tokens": 0, "total_tokens": 20},
            )
        ],
    )
    await app.state.db.set_run_status("run-1", "complete")
    await app.state.db.set_run_status("run-2", "complete")

    day1 = datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp()
    day2 = datetime(2026, 7, 2, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(database_module.time, "time", lambda: day1)
    await app.state.db.compute_run_metrics("run-1")
    monkeypatch.setattr(database_module.time, "time", lambda: day2)
    await app.state.db.compute_run_metrics("run-2")

    response = client.get("/metrics/trends?period=day&metric=tokens")
    assert response.status_code == 200
    buckets = {point["bucket"]: point["value"] for point in response.json()}
    assert buckets["2026-07-01"] == 10
    assert buckets["2026-07-02"] == 20


async def test_metrics_trends_buckets_by_week(client, monkeypatch):
    client.post(
        "/events",
        json=[
            _event(
                event_id="e1",
                run_id="run-1",
                event_type="llm_call",
                token_usage={"input_tokens": 10, "output_tokens": 0, "total_tokens": 10},
            )
        ],
    )
    client.post(
        "/events",
        json=[
            _event(
                event_id="e2",
                run_id="run-2",
                event_type="llm_call",
                token_usage={"input_tokens": 20, "output_tokens": 0, "total_tokens": 20},
            )
        ],
    )
    await app.state.db.set_run_status("run-1", "complete")
    await app.state.db.set_run_status("run-2", "complete")

    ref = datetime(2026, 7, 1, tzinfo=timezone.utc)
    monday = ref - timedelta(days=ref.weekday())
    same_week_day = monday + timedelta(days=2)
    monkeypatch.setattr(database_module.time, "time", lambda: monday.timestamp())
    await app.state.db.compute_run_metrics("run-1")
    monkeypatch.setattr(database_module.time, "time", lambda: same_week_day.timestamp())
    await app.state.db.compute_run_metrics("run-2")

    response = client.get("/metrics/trends?period=week&metric=tokens")
    assert response.status_code == 200
    points = response.json()
    assert len(points) == 1
    assert points[0]["bucket"] == monday.strftime("%Y-%m-%d")
    assert points[0]["value"] == 30


async def test_metrics_trends_buckets_by_month(client, monkeypatch):
    client.post(
        "/events",
        json=[
            _event(
                event_id="e1",
                run_id="run-1",
                event_type="llm_call",
                token_usage={"input_tokens": 10, "output_tokens": 0, "total_tokens": 10},
            )
        ],
    )
    client.post(
        "/events",
        json=[
            _event(
                event_id="e2",
                run_id="run-2",
                event_type="llm_call",
                token_usage={"input_tokens": 20, "output_tokens": 0, "total_tokens": 20},
            )
        ],
    )
    await app.state.db.set_run_status("run-1", "complete")
    await app.state.db.set_run_status("run-2", "complete")

    early_in_month = datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp()
    later_in_month = datetime(2026, 7, 20, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(database_module.time, "time", lambda: early_in_month)
    await app.state.db.compute_run_metrics("run-1")
    monkeypatch.setattr(database_module.time, "time", lambda: later_in_month)
    await app.state.db.compute_run_metrics("run-2")

    response = client.get("/metrics/trends?period=month&metric=tokens")
    assert response.status_code == 200
    points = response.json()
    assert len(points) == 1
    assert points[0]["bucket"] == "2026-07-01"
    assert points[0]["value"] == 30


def test_metrics_trends_rejects_an_invalid_period(client):
    response = client.get("/metrics/trends?period=year&metric=tokens")
    assert response.status_code == 400


def test_metrics_trends_rejects_an_invalid_metric(client):
    response = client.get("/metrics/trends?period=day&metric=bogus")
    assert response.status_code == 400


# --- GET /metrics/tools ----------------------------------------------------------


def test_metrics_tools_aggregates_tool_stats_correctly(client):
    client.post(
        "/events",
        json=[
            _event(
                event_id="e1",
                run_id="run-1",
                event_type="tool_call",
                duration_ms=100.0,
                data={"tool_name": "search"},
                token_usage={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
            ),
            _event(
                event_id="e2",
                run_id="run-1",
                event_type="tool_call",
                duration_ms=200.0,
                data={"tool_name": "search"},
                error="request failed",
            ),
            _event(
                event_id="e3",
                run_id="run-1",
                event_type="tool_call",
                duration_ms=50.0,
                data={"tool_name": "calculator"},
            ),
        ],
    )

    response = client.get("/metrics/tools")
    assert response.status_code == 200
    body = response.json()

    assert body[0]["tool_name"] == "search"
    search = next(t for t in body if t["tool_name"] == "search")
    assert search["call_count"] == 2
    assert search["error_rate"] == pytest.approx(0.5)
    assert search["avg_latency_ms"] == pytest.approx(150.0)
    assert search["total_tokens"] == 10

    calculator = next(t for t in body if t["tool_name"] == "calculator")
    assert calculator["call_count"] == 1
    assert calculator["error_rate"] == 0.0


def test_metrics_tools_is_empty_with_no_tool_calls(client):
    response = client.get("/metrics/tools")
    assert response.status_code == 200
    assert response.json() == []


# --- GET /metrics/models ----------------------------------------------------------


def test_metrics_models_aggregates_per_model_stats(client):
    client.post(
        "/events",
        json=[
            _event(
                event_id="e1",
                run_id="run-1",
                event_type="llm_call",
                duration_ms=100.0,
                data={"model": "gpt-4"},
                token_usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            ),
            _event(
                event_id="e2",
                run_id="run-1",
                event_type="llm_call",
                duration_ms=200.0,
                data={"model": "gpt-4"},
                token_usage={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
            ),
        ],
    )

    response = client.get("/metrics/models")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["model_name"] == "gpt-4"
    assert body[0]["call_count"] == 2
    assert body[0]["total_input_tokens"] == 15
    assert body[0]["total_output_tokens"] == 25
    assert body[0]["cost_is_estimate"] is True


# --- POST /metrics/backfill --------------------------------------------------------


async def test_backfill_processes_complete_runs_without_existing_metrics(client):
    client.post("/events", json=[_event(event_id="e1", run_id="run-1", event_type="tool_call")])
    await app.state.db.set_run_status("run-1", "complete")

    client.post("/events", json=[_event(event_id="e2", run_id="run-2", event_type="tool_call")])
    # run-2 stays "running" - backfill should skip it.

    response = client.post("/metrics/backfill")
    assert response.status_code == 200
    assert response.json()["backfilled_count"] == 1

    rows = client.get("/metrics/runs").json()
    run_ids = {row["run_id"] for row in rows}
    assert "run-1" in run_ids
    assert "run-2" not in run_ids


async def test_backfill_is_a_no_op_the_second_time(client):
    client.post("/events", json=[_event(event_id="e1", run_id="run-1", event_type="tool_call")])
    await app.state.db.set_run_status("run-1", "complete")

    first = client.post("/metrics/backfill").json()
    second = client.post("/metrics/backfill").json()
    assert first["backfilled_count"] == 1
    assert second["backfilled_count"] == 0


async def test_backfill_returns_409_when_already_running(client):
    async with app.state.backfill_lock:
        response = client.post("/metrics/backfill")
    assert response.status_code == 409


# --- POST /events background metrics recomputation ---------------------------------
#
# `_refresh_run_aggregates` always resets a run's status to "running"/"error" on every
# `POST /events` batch, so a run can never be freshly observed as "complete" from
# *within* that same request - the hook only ever matters for a run that was marked
# complete by another path (e.g. the replay engine) earlier. These tests exercise the
# hook's conditional logic directly rather than through an unreachable HTTP scenario.


async def test_compute_metrics_if_complete_computes_metrics_for_a_complete_run(client):
    client.post(
        "/events", json=[_event(event_id="e1", run_id="run-1", event_type="tool_call", duration_ms=10.0)]
    )
    await app.state.db.set_run_status("run-1", "complete")

    await _compute_metrics_if_complete(app.state.db, "run-1")

    rows = client.get("/metrics/runs").json()
    assert any(row["run_id"] == "run-1" for row in rows)


async def test_compute_metrics_if_complete_is_a_no_op_for_a_running_run(client):
    client.post("/events", json=[_event(event_id="e1", run_id="run-1", event_type="tool_call")])

    await _compute_metrics_if_complete(app.state.db, "run-1")

    rows = client.get("/metrics/runs").json()
    assert not any(row["run_id"] == "run-1" for row in rows)
