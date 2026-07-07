import json
from types import SimpleNamespace

from chronicle import ChronicleTracer
from chronicle.adapters.semantickernel import ChronicleKernelPlugin


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


def test_pre_and_post_invocation_hooks_record_tool_call_events(tmp_path):
    tracer = _tracer(tmp_path)
    plugin = ChronicleKernelPlugin(tracer, agent_name="agent-a")

    plugin.pre_invocation_hook(function_name="get_weather", plugin_name="weather", arguments={"city": "Paris"})
    plugin.post_invocation_hook(function_name="get_weather", plugin_name="weather", result="sunny")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "tool_call"
    assert events[0]["data"]["event"] == "function_start"
    assert events[0]["data"]["function_name"] == "get_weather"
    assert events[0]["data"]["plugin_name"] == "weather"
    assert events[0]["data"]["arguments"] == {"city": "Paris"}

    assert events[1]["event_type"] == "tool_call"
    assert events[1]["data"]["event"] == "function_end"
    assert events[1]["data"]["result"] == "sunny"
    assert events[1]["duration_ms"] is not None


def test_post_invocation_hook_extracts_token_usage_from_result_metadata(tmp_path):
    tracer = _tracer(tmp_path)
    plugin = ChronicleKernelPlugin(tracer)
    result = SimpleNamespace(metadata={"usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}})

    plugin.pre_invocation_hook(function_name="f", plugin_name="p")
    plugin.post_invocation_hook(function_name="f", plugin_name="p", result=result)
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[1]["token_usage"] == {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}


def test_pre_and_post_chat_hooks_record_llm_call_events(tmp_path):
    tracer = _tracer(tmp_path)
    plugin = ChronicleKernelPlugin(tracer, agent_name="agent-a")

    plugin.pre_chat_hook(messages=[{"role": "user", "content": "hi"}])
    plugin.post_chat_hook(response=SimpleNamespace(content="hello"), finish_reason="stop")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "llm_call"
    assert events[0]["data"]["event"] == "llm_call"
    assert events[0]["data"]["messages"] == [{"role": "user", "content": "hi"}]

    assert events[1]["event_type"] == "llm_call"
    assert events[1]["data"]["event"] == "llm_result"
    assert events[1]["data"]["response"] == "hello"
    assert events[1]["data"]["finish_reason"] == "stop"
    assert events[1]["duration_ms"] is not None


def test_pre_chat_hook_serializes_object_style_messages(tmp_path):
    tracer = _tracer(tmp_path)
    plugin = ChronicleKernelPlugin(tracer)
    message = SimpleNamespace(role="system", content="be helpful")

    plugin.pre_chat_hook(messages=[message])
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["data"]["messages"] == [{"role": "system", "content": "be helpful"}]


def test_post_chat_hook_without_token_usage(tmp_path):
    tracer = _tracer(tmp_path)
    plugin = ChronicleKernelPlugin(tracer)

    plugin.pre_chat_hook(messages=[])
    plugin.post_chat_hook(response=SimpleNamespace(content="ok"))
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[1]["token_usage"] is None
