import json
from types import SimpleNamespace

import pytest

from chronicle import ChronicleTracer
from chronicle.adapters.pydanticai import ChronicleMiddleware


def _tracer(tmp_path, **kwargs):
    return ChronicleTracer(
        server_url="http://127.0.0.1:1",  # nothing listens here
        timeout=0.2,
        local_dir=tmp_path / "chronicle_runs",
        batch_size=1,
        **kwargs,
    )


def _read_events(tmp_path, run_id):
    path = tmp_path / "chronicle_runs" / f"{run_id}.json"
    return json.loads(path.read_text())


class ToolCallPart:
    """Named to match `pydantic_ai.messages.ToolCallPart`, which the adapter detects by class name."""

    def __init__(self, tool_name, args):
        self.tool_name = tool_name
        self.args = args


def _make_agent(result=None, error=None):
    def run_sync(prompt, *args, **kwargs):
        if error is not None:
            raise error
        return result

    return SimpleNamespace(name="assistant", model=SimpleNamespace(model_name="gpt-4o"), run_sync=run_sync)


def _make_result(output="hello", tool_calls=None, usage=None):
    messages = []
    if tool_calls:
        messages.append(SimpleNamespace(parts=[ToolCallPart(name, args) for name, args in tool_calls]))
    return SimpleNamespace(
        output=output,
        all_messages=lambda: messages,
        usage=lambda: usage,
    )


def test_run_sync_records_llm_call_with_prompt_and_response(tmp_path):
    tracer = _tracer(tmp_path)
    agent = _make_agent(result=_make_result(output="it's sunny"))
    middleware = ChronicleMiddleware(agent, tracer)

    result = middleware.run_sync("what's the weather?")
    tracer.close()

    assert result.output == "it's sunny"
    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "llm_call"
    assert events[0]["agent_name"] == "assistant"
    assert events[0]["data"]["model"] == "gpt-4o"
    assert events[0]["data"]["prompt"] == "what's the weather?"
    assert events[0]["data"]["response"] == "it's sunny"
    assert events[0]["duration_ms"] is not None


def test_run_sync_captures_tool_calls(tmp_path):
    tracer = _tracer(tmp_path)
    agent = _make_agent(result=_make_result(tool_calls=[("search", {"query": "weather"})]))
    middleware = ChronicleMiddleware(agent, tracer)

    middleware.run_sync("what's the weather?")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["data"]["tool_calls"] == [{"tool_name": "search", "args": {"query": "weather"}}]


def test_run_sync_captures_token_usage(tmp_path):
    tracer = _tracer(tmp_path)
    usage = SimpleNamespace(request_tokens=10, response_tokens=5, total_tokens=15)
    agent = _make_agent(result=_make_result(usage=usage))
    middleware = ChronicleMiddleware(agent, tracer)

    middleware.run_sync("hi")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["token_usage"] == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


def test_run_sync_records_error_event_and_reraises(tmp_path):
    tracer = _tracer(tmp_path)
    agent = _make_agent(error=ValueError("model unavailable"))
    middleware = ChronicleMiddleware(agent, tracer)

    with pytest.raises(ValueError, match="model unavailable"):
        middleware.run_sync("hi")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "error"
    assert events[0]["error"] == "model unavailable"


def test_middleware_delegates_unknown_attributes_to_the_wrapped_agent(tmp_path):
    tracer = _tracer(tmp_path)
    agent = _make_agent(result=_make_result())
    agent.custom_attribute = "value"
    middleware = ChronicleMiddleware(agent, tracer)

    assert middleware.custom_attribute == "value"
