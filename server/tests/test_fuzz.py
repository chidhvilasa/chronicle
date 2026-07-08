"""Fuzz tests (Hypothesis) for the four required server endpoints.

Each target's only invariant is "never an unhandled 500" - a 4xx for malformed
input is always fine, a 200/404 for a lookup is always fine, a 500 never is.

Pytest fixtures (`tmp_path`, `monkeypatch`) are resolved once, outside the
`@given`-decorated inner function, rather than passed as fixture arguments to
a Hypothesis test - Hypothesis re-runs the test body per generated example,
and mixing that with function-scoped fixtures either re-creates the app on
every example (slow) or trips Hypothesis's function-scoped-fixture health
check. Creating the `TestClient` once per test function and closing over it
from a plain nested function avoids both.
"""

from __future__ import annotations

import urllib.parse

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.main import app

_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**9), max_value=10**9),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=30),
)

_json_values = st.recursive(
    _json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=15), children, max_size=4),
    ),
    max_leaves=25,
)


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_DB_PATH", str(tmp_path / "chronicle.db"))
    monkeypatch.chdir(tmp_path)
    return TestClient(app)


# --- 1. POST /events random payloads -----------------------------------------


def test_fuzz_post_events_never_returns_500(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:

        @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
        @given(body=st.one_of(st.lists(_json_values, max_size=5), _json_values))
        def run(body):
            response = client.post("/events", json=body)
            assert response.status_code != 500, response.text

        run()


def test_fuzz_post_events_with_valid_shape_and_random_data_never_returns_500(tmp_path, monkeypatch):
    """A structurally-valid event list with a fuzzed `data` payload - exercises the
    payload-size/JSON-depth/int-clamping validation path with real event shapes,
    not just malformed request bodies that fail Pydantic validation immediately.
    """
    with _client(tmp_path, monkeypatch) as client:

        @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
        @given(
            data=st.dictionaries(st.text(max_size=15), _json_values, max_size=6),
            timestamp=st.floats(allow_nan=False, allow_infinity=False, min_value=-1e15, max_value=1e15),
            input_tokens=st.one_of(st.none(), st.integers(min_value=-(10**15), max_value=10**15)),
        )
        def run(data, timestamp, input_tokens):
            event = {
                "event_id": "fuzz-evt",
                "run_id": "fuzz-run",
                "timestamp": timestamp,
                "event_type": "tool_call",
                "agent_name": "agent",
                "data": data,
                "duration_ms": None,
                "token_usage": {"input_tokens": input_tokens} if input_tokens is not None else None,
                "error": None,
            }
            response = client.post("/events", json=[event])
            assert response.status_code != 500, response.text

        run()


# --- 2. GET /metrics/trends random params ------------------------------------


def test_fuzz_get_metrics_trends_never_returns_500(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:

        @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
        @given(
            period=st.text(max_size=20),
            metric=st.text(max_size=20),
            stat=st.text(max_size=20),
        )
        def run(period, metric, stat):
            response = client.get(
                "/metrics/trends", params={"period": period, "metric": metric, "stat": stat}
            )
            assert response.status_code != 500, response.text

        run()


# --- 3. GET /runs/{id}/graph with adversarial run_ids ------------------------


_adversarial_run_id_fragments = st.sampled_from(
    [
        "../../etc/passwd",
        "..\\..\\windows\\system32",
        "%2e%2e%2fetc%2fpasswd",
        "' OR '1'='1",
        "%' OR '1'='1",
        "run'; DROP TABLE runs;--",
        "\x00",
        "run\x00id",
        "éè中文\U0001F600",
        "a" * 500,
        "",
        " ",
        "%00",
        "run_id/../../../secret",
    ]
)


def test_fuzz_get_run_graph_with_adversarial_run_ids_never_returns_500(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:

        @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
        @given(run_id=st.one_of(_adversarial_run_id_fragments, st.text(max_size=100)))
        def run(run_id):
            encoded = urllib.parse.quote(run_id, safe="")
            response = client.get(f"/runs/{encoded}/graph")
            assert response.status_code in (200, 404), (run_id, response.status_code, response.text)

        run()


# --- 4. POST /replay deeply nested modifications -----------------------------


def _nested_replay_body(depth: int) -> bytes:
    """Builds the raw JSON request body via string concatenation (no Python-level
    recursion), so a very deep `depth` can't blow the *test client's* own recursion
    limit while json-encoding the request - only the server's JSON parsing (over
    the wire, on real bytes) is meant to be exercised here.
    """
    nested = '{"nested":' * depth + '{"leaf":true}' + "}" * depth
    body = (
        '{"run_id":"fuzz-source-run","snapshot_id":"fuzz-snap","modifications":'
        + nested
        + "}"
    )
    return body.encode("utf-8")


def test_fuzz_post_replay_deeply_nested_modifications_never_returns_500(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:

        @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
        @given(depth=st.integers(min_value=0, max_value=3000))
        def run(depth):
            response = client.post(
                "/replay",
                content=_nested_replay_body(depth),
                headers={"Content-Type": "application/json"},
            )
            assert response.status_code != 500, (depth, response.text)

        run()
