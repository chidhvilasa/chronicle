"""Regression tests for the v0.8.0 security hardening pass (see SECURITY_AUDIT.md).

Covers: SQL injection resistance across query parameters, path traversal in
POST /register, payload size limits, JSON nesting depth limits, integer
clamping, timestamp window validation, replay depth limits, and CORS config.
"""

import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.main import ALLOWED_ORIGINS, app
from src.validation import (
    INT32_MAX,
    MAX_EVENT_PAYLOAD_BYTES,
    MAX_EVENTS_PER_REQUEST,
    MAX_JSON_DEPTH,
    json_depth,
    validate_timestamp,
)

_BASE_TIME = time.time() - 1000.0


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CHRONICLE_DB_PATH", ":memory:")
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
        "duration_ms": 10.0,
        "token_usage": None,
        "error": None,
    }
    event.update(overrides)
    return event


# --- SQL injection resistance -----------------------------------------------------


SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE runs; --",
    "' OR '1'='1",
    "run-1' OR 1=1--",
    "1; DELETE FROM events WHERE 1=1;",
    "run-1\"; DROP TABLE events;--",
]


@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_run_id_path_param_treats_sql_payloads_as_literal_strings(client, payload):
    """A SQL-injection-shaped run_id must 404 (treated as a literal, non-existent id),
    never execute as SQL or 500."""
    response = client.get(f"/runs/{payload}/events")
    assert response.status_code == 404


@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_framework_query_param_is_parameterized_not_concatenated(client, payload):
    client.post("/events", json=[_event()])
    response = client.get("/metrics/runs", params={"framework": payload})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_status_query_param_is_parameterized_not_concatenated(client, payload):
    client.post("/events", json=[_event()])
    response = client.get("/metrics/runs", params={"status": payload})
    assert response.status_code == 200


def test_sql_injection_payload_as_run_id_does_not_delete_other_runs(client):
    client.post("/events", json=[_event(run_id="run-victim")])
    client.delete("/runs/run-victim'; DROP TABLE runs;--")

    # The real run must still exist - the malicious id was never executed as SQL.
    response = client.get("/runs/run-victim/events")
    assert response.status_code == 200


def test_database_schema_survives_repeated_injection_attempts(client):
    """After throwing injection payloads at several endpoints, the database must still
    be fully functional - proof no SQL actually executed."""
    for payload in SQL_INJECTION_PAYLOADS:
        client.get(f"/runs/{payload}/events")
        client.get(f"/runs/{payload}/timeline")
        client.delete(f"/runs/{payload}")

    client.post("/events", json=[_event(run_id="run-still-works")])
    response = client.get("/runs/run-still-works/events")
    assert response.status_code == 200
    assert len(response.json()) == 1


# --- Path traversal in POST /register ----------------------------------------------


PATH_TRAVERSAL_MODULE_PAYLOADS = [
    "../../etc/passwd",
    "..",
    "/etc/passwd",
    "os.system('rm -rf /')",
    "a/b/c",
    ".hidden",
    "a..b",
    "a.",
    "",
    "os; import subprocess",
]


@pytest.mark.parametrize("payload", PATH_TRAVERSAL_MODULE_PAYLOADS)
def test_register_rejects_non_dotted_identifier_module_paths(client, payload):
    response = client.post("/register", json={"graph_module": payload, "graph_attr": "graph"})
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"


@pytest.mark.parametrize("payload", ["../escape", "a/b", "os.system", "", "123abc"])
def test_register_rejects_invalid_graph_attr(client, payload):
    response = client.post("/register", json={"graph_module": "os", "graph_attr": payload})
    assert response.status_code == 400


def test_register_accepts_a_normal_dotted_module_path():
    from src.registry import GraphRegistry

    registry = GraphRegistry()
    name = registry.register("os", "path")
    assert name == "os.path"


# --- Payload size limits ------------------------------------------------------------


def test_post_events_rejects_more_than_max_events_per_request(client):
    events = [_event(event_id=f"evt-{i}", timestamp=1000.0 + i) for i in range(MAX_EVENTS_PER_REQUEST + 1)]
    response = client.post("/events", json=events)
    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"


def test_post_events_accepts_exactly_the_max_events_per_request(client):
    events = [_event(event_id=f"evt-{i}", timestamp=1000.0 + i) for i in range(MAX_EVENTS_PER_REQUEST)]
    response = client.post("/events", json=events)
    assert response.status_code == 200
    assert response.json() == {"count": MAX_EVENTS_PER_REQUEST}


def test_post_events_rejects_an_oversized_event_payload(client):
    huge_string = "x" * (MAX_EVENT_PAYLOAD_BYTES + 1)
    response = client.post("/events", json=[_event(data={"value": huge_string})])
    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"


def test_post_events_accepts_a_reasonably_sized_payload(client):
    response = client.post("/events", json=[_event(data={"value": "x" * 1000})])
    assert response.status_code == 200


# --- JSON depth limit ----------------------------------------------------------------


def _nested_dict(depth: int):
    value: dict = {"leaf": True}
    for _ in range(depth):
        value = {"nested": value}
    return value


def test_json_depth_helper_computes_correct_depth():
    assert json_depth({"a": 1}) == 1
    assert json_depth({"a": {"b": 1}}) == 2
    assert json_depth([1, [2, [3]]]) == 3
    assert json_depth("scalar") == 0


def test_post_events_rejects_deeply_nested_data(client):
    response = client.post("/events", json=[_event(data=_nested_dict(MAX_JSON_DEPTH + 5))])
    assert response.status_code == 400
    assert "nested" in response.json()["detail"]


def test_post_events_accepts_data_within_the_depth_limit(client):
    response = client.post("/events", json=[_event(data=_nested_dict(5))])
    assert response.status_code == 200


# --- Integer clamping ----------------------------------------------------------------


def test_post_events_clamps_oversized_token_counts(client):
    client.post(
        "/events",
        json=[_event(token_usage={"input_tokens": 2**40, "output_tokens": 2**40, "total_tokens": 2**40})],
    )
    events = client.get("/runs/run-1/events").json()
    assert events[0]["input_tokens"] == INT32_MAX
    assert events[0]["output_tokens"] == INT32_MAX


def test_post_events_clamps_oversized_duration(client):
    client.post("/events", json=[_event(duration_ms=2**40)])
    events = client.get("/runs/run-1/events").json()
    assert events[0]["duration_ms"] == INT32_MAX


def test_post_events_clamps_negative_duration_to_zero(client):
    client.post("/events", json=[_event(duration_ms=-500.0)])
    events = client.get("/runs/run-1/events").json()
    assert events[0]["duration_ms"] == 0.0


# --- Timestamp validation ------------------------------------------------------------


def test_validate_timestamp_accepts_now():
    assert validate_timestamp(time.time()) is None


def test_validate_timestamp_rejects_far_future():
    assert validate_timestamp(time.time() + 7200) is not None


def test_validate_timestamp_rejects_far_past():
    assert validate_timestamp(time.time() - 40 * 86400) is not None


def _raw_event(timestamp: float, event_id: str = "evt-1") -> dict:
    """Builds a POST /events payload with an *absolute* timestamp, bypassing
    _event()'s _BASE_TIME-relative offset rebasing (which only makes sense for the
    small relative-offset style used elsewhere in this file)."""
    return {
        "event_id": event_id,
        "run_id": "run-1",
        "timestamp": timestamp,
        "event_type": "tool_call",
        "agent_name": "agent-a",
        "data": {},
        "duration_ms": 10.0,
        "token_usage": None,
        "error": None,
    }


def test_post_events_rejects_a_timestamp_too_far_in_the_future(client):
    response = client.post("/events", json=[_raw_event(time.time() + 7200, event_id="future")])
    assert response.status_code == 400
    assert "future" in response.json()["detail"]


def test_post_events_rejects_a_timestamp_too_far_in_the_past(client):
    ancient = time.time() - 40 * 86400
    response = client.post("/events", json=[_raw_event(ancient, event_id="ancient")])
    assert response.status_code == 400
    assert "past" in response.json()["detail"]


def test_post_events_accepts_a_timestamp_within_the_window(client):
    response = client.post("/events", json=[_raw_event(time.time())])
    assert response.status_code == 200


# --- Replay depth limit ---------------------------------------------------------------


def _register_mock_graph(module_name: str):
    import sys
    import types

    module = types.ModuleType(module_name)

    class _MockGraph:
        def invoke(self, state, config=None):
            return {}

    module.graph = _MockGraph()  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    return module_name


def _post_snapshot(client, run_id="run-1", snapshot_id="snap-1", event_id="evt-1"):
    client.post(
        "/snapshots",
        json=[
            {
                "snapshot_id": snapshot_id,
                "run_id": run_id,
                "event_id": event_id,
                "step_index": 0,
                "timestamp": time.time(),
                "agent_name": "agent-a",
                "messages": [],
                "tool_results": [],
                "graph_state": {},
                "metadata": {},
            }
        ],
    )


def test_replay_depth_field_is_stamped_on_a_fresh_replay(client):
    module_name = _register_mock_graph("chronicle_test_fixture_security_graph")
    try:
        client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
        client.post("/events", json=[_event()])
        _post_snapshot(client)

        response = client.post(
            "/replay", json={"run_id": "run-1", "snapshot_id": "snap-1", "modifications": {}}
        )
        new_run_id = response.json()["run_id"]
        replay_run = next(r for r in client.get("/runs").json() if r["run_id"] == new_run_id)
        assert replay_run["metadata"]["replay_depth"] == 1
    finally:
        del __import__("sys").modules[module_name]


async def test_source_replay_depth_returns_zero_for_a_non_replay_run(client):
    from src.main import _source_replay_depth

    client.post("/events", json=[_event()])
    result = await _source_replay_depth(app.state.db, "run-1")
    assert result == 0


async def test_source_replay_depth_returns_zero_for_a_missing_run(client):
    from src.main import _source_replay_depth

    result = await _source_replay_depth(app.state.db, "does-not-exist")
    assert result == 0


async def test_source_replay_depth_reads_the_stamped_metadata_field(client):
    from src.main import _source_replay_depth

    await app.state.db.set_run_metadata("run-deep", {"is_replay": True, "replay_depth": 3})
    result = await _source_replay_depth(app.state.db, "run-deep")
    assert result == 3


async def test_source_replay_depth_defaults_legacy_replay_runs_to_one(client):
    """A replay run recorded before `replay_depth` existed in its metadata (is_replay is
    True but no replay_depth key) is treated as depth 1, not 0."""
    from src.main import _source_replay_depth

    await app.state.db.set_run_metadata("run-legacy-replay", {"is_replay": True})
    result = await _source_replay_depth(app.state.db, "run-legacy-replay")
    assert result == 1


def test_require_replay_depth_ok_raises_at_the_limit():
    from src.main import MAX_REPLAY_DEPTH, _require_replay_depth_ok

    with pytest.raises(HTTPException) as exc_info:
        _require_replay_depth_ok(MAX_REPLAY_DEPTH)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Maximum replay depth reached."


def test_require_replay_depth_ok_passes_below_the_limit():
    from src.main import MAX_REPLAY_DEPTH, _require_replay_depth_ok

    _require_replay_depth_ok(MAX_REPLAY_DEPTH - 1)  # must not raise


async def test_replay_endpoint_400s_when_source_is_already_at_max_depth(client):
    module_name = _register_mock_graph("chronicle_test_fixture_security_depth_graph")
    try:
        client.post("/register", json={"graph_module": module_name, "graph_attr": "graph"})
        client.post("/events", json=[_event()])
        _post_snapshot(client)
        await app.state.db.set_run_metadata("run-1", {"is_replay": True, "replay_depth": 3})

        response = client.post(
            "/replay", json={"run_id": "run-1", "snapshot_id": "snap-1", "modifications": {}}
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Maximum replay depth reached."
    finally:
        del __import__("sys").modules[module_name]


# --- CORS hardening -------------------------------------------------------------------


def test_cors_allows_only_the_tauri_dev_origin_no_wildcard():
    assert ALLOWED_ORIGINS == ["http://localhost:1420"]
    assert "*" not in ALLOWED_ORIGINS


def test_cors_preflight_rejects_an_untrusted_origin(client):
    response = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") != "https://evil.example.com"
    assert response.headers.get("access-control-allow-origin") != "*"
