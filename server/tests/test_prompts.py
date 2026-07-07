import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.prompt_diff import compute_prompt_diff
from src.prompts import build_prompt_detail, build_prompt_summaries


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CHRONICLE_DB_PATH", ":memory:")
    with TestClient(app) as test_client:
        yield test_client


def _llm_event(event_id="e1", run_id="run-1", timestamp=1000.0, agent_name="agent-a", data=None, **overrides):
    event = {
        "event_id": event_id,
        "run_id": run_id,
        "timestamp": timestamp,
        "event_type": "llm_call",
        "agent_name": agent_name,
        "duration_ms": 100.0,
        "input_tokens": 10,
        "output_tokens": 20,
        "data": data or {},
        "error": None,
    }
    event.update(overrides)
    return event


# --- build_prompt_summaries / build_prompt_detail (pure functions) --------------


def test_build_prompt_summaries_extracts_char_and_token_counts():
    events = [
        _llm_event(data={"prompt": "hello there", "completion": "hi!"}),
    ]
    summaries = build_prompt_summaries(events)
    assert len(summaries) == 1
    assert summaries[0]["step_index"] == 0
    assert summaries[0]["agent_name"] == "agent-a"
    assert summaries[0]["total_tokens"] == 30
    assert summaries[0]["total_chars"] == len("hello there") + len("hi!")


def test_build_prompt_summaries_orders_by_timestamp_and_assigns_step_index():
    events = [
        _llm_event(event_id="e2", timestamp=1001.0, data={"prompt": "second"}),
        _llm_event(event_id="e1", timestamp=1000.0, data={"prompt": "first"}),
    ]
    summaries = build_prompt_summaries(events)
    assert [s["event_id"] for s in summaries] == ["e1", "e2"]
    assert [s["step_index"] for s in summaries] == [0, 1]


def test_build_prompt_summaries_ignores_non_llm_events():
    events = [
        _llm_event(event_id="e1", data={"prompt": "hi"}),
        {**_llm_event(event_id="e2"), "event_type": "tool_call"},
    ]
    summaries = build_prompt_summaries(events)
    assert len(summaries) == 1


def test_build_prompt_summaries_empty_for_no_events():
    assert build_prompt_summaries([]) == []


def test_build_prompt_detail_extracts_system_user_assistant_messages():
    events = [
        _llm_event(
            data={
                "messages": [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "What's the weather?"},
                ],
                "completion": "It's sunny.",
            }
        )
    ]
    detail = build_prompt_detail(events, "e1")
    assert detail is not None
    assert detail["system_prompt"] == "You are helpful."
    assert detail["user_messages"] == [{"role": "user", "content": "What's the weather?"}]
    assert detail["assistant_messages"] == [{"role": "assistant", "content": "It's sunny."}]


def test_build_prompt_detail_falls_back_to_prompts_list_when_no_messages_key():
    events = [_llm_event(data={"prompts": ["prompt one", "prompt two"]})]
    detail = build_prompt_detail(events, "e1")
    assert detail is not None
    assert detail["user_messages"] == [
        {"role": "user", "content": "prompt one"},
        {"role": "user", "content": "prompt two"},
    ]


def test_build_prompt_detail_returns_none_for_missing_event_id():
    events = [_llm_event(data={"prompt": "hi"})]
    assert build_prompt_detail(events, "missing") is None


def test_build_prompt_detail_computes_total_chars_and_tokens():
    events = [_llm_event(data={"prompt": "abc"}, input_tokens=5, output_tokens=5)]
    detail = build_prompt_detail(events, "e1")
    assert detail is not None
    assert detail["total_tokens"] == 10
    assert detail["total_chars"] >= len("abc")


# --- compute_prompt_diff (pure function) -----------------------------------------


def test_compute_prompt_diff_counts_additions_and_deletions():
    result = compute_prompt_diff("hello world", "hello there")
    assert result["unchanged"] > 0
    assert result["additions"] > 0
    assert result["deletions"] > 0
    assert '<span class="add">' in result["diff_html"]
    assert '<span class="del">' in result["diff_html"]
    assert '<span class="same">' in result["diff_html"]


def test_compute_prompt_diff_identical_strings_have_no_additions_or_deletions():
    result = compute_prompt_diff("same text", "same text")
    assert result["additions"] == 0
    assert result["deletions"] == 0
    assert result["unchanged"] == len("same text")


def test_compute_prompt_diff_escapes_html_special_characters():
    result = compute_prompt_diff("<script>alert(1)</script>", "safe")
    # Character-level diffing fragments the string across multiple spans, so assert on
    # escaping generally rather than expecting one contiguous escaped substring.
    assert "<script>" not in result["diff_html"]
    assert "</script>" not in result["diff_html"]
    assert "&lt;" in result["diff_html"]
    assert "&gt;" in result["diff_html"]


# --- HTTP endpoints ---------------------------------------------------------------


def test_get_run_prompts_returns_summaries_without_message_content(client):
    client.post(
        "/events",
        json=[
            {
                "event_id": "e1",
                "run_id": "run-1",
                "timestamp": 1000.0,
                "event_type": "llm_call",
                "agent_name": "agent-a",
                "data": {"prompt": "hello", "completion": "hi"},
                "duration_ms": 100.0,
                "token_usage": {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
                "error": None,
            }
        ],
    )
    response = client.get("/runs/run-1/prompts")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["event_id"] == "e1"
    assert "system_prompt" not in body[0]
    assert "user_messages" not in body[0]


def test_get_run_prompts_404_for_missing_run(client):
    response = client.get("/runs/missing/prompts")
    assert response.status_code == 404


def test_get_run_prompt_detail_returns_full_content(client):
    client.post(
        "/events",
        json=[
            {
                "event_id": "e1",
                "run_id": "run-1",
                "timestamp": 1000.0,
                "event_type": "llm_call",
                "agent_name": "agent-a",
                "data": {"prompt": "hello", "completion": "hi"},
                "duration_ms": 100.0,
                "token_usage": None,
                "error": None,
            }
        ],
    )
    response = client.get("/runs/run-1/prompts/e1")
    assert response.status_code == 200
    body = response.json()
    assert body["user_messages"] == [{"role": "user", "content": "hello"}]
    assert body["assistant_messages"] == [{"role": "assistant", "content": "hi"}]


def test_get_run_prompt_detail_404_for_missing_event(client):
    client.post(
        "/events",
        json=[
            {
                "event_id": "e1",
                "run_id": "run-1",
                "timestamp": 1000.0,
                "event_type": "llm_call",
                "agent_name": "agent-a",
                "data": {},
                "duration_ms": None,
                "token_usage": None,
                "error": None,
            }
        ],
    )
    response = client.get("/runs/run-1/prompts/missing")
    assert response.status_code == 404


def test_get_prompts_diff_endpoint_computes_diff_across_runs(client):
    client.post(
        "/events",
        json=[
            {
                "event_id": "e1",
                "run_id": "run-a",
                "timestamp": 1000.0,
                "event_type": "llm_call",
                "agent_name": "agent-a",
                "data": {"prompt": "hello world"},
                "duration_ms": None,
                "token_usage": None,
                "error": None,
            }
        ],
    )
    client.post(
        "/events",
        json=[
            {
                "event_id": "e2",
                "run_id": "run-b",
                "timestamp": 1000.0,
                "event_type": "llm_call",
                "agent_name": "agent-a",
                "data": {"prompt": "hello there"},
                "duration_ms": None,
                "token_usage": None,
                "error": None,
            }
        ],
    )
    response = client.get(
        "/prompts/diff",
        params={"run_id_a": "run-a", "event_id_a": "e1", "run_id_b": "run-b", "event_id_b": "e2"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["additions"] > 0
    assert body["deletions"] > 0


def test_get_prompts_diff_404_for_missing_event(client):
    response = client.get(
        "/prompts/diff",
        params={"run_id_a": "missing", "event_id_a": "e1", "run_id_b": "missing", "event_id_b": "e2"},
    )
    assert response.status_code == 404
