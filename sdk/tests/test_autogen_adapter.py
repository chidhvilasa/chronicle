import json
from types import SimpleNamespace

from chronicle import ChronicleTracer
from chronicle.adapters.autogen import ChronicleAutoGenHook


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


def _make_agent(name="assistant", chat_result=None, function_result=None):
    def initiate_chat(recipient, message, *args, **kwargs):
        return chat_result if chat_result is not None else SimpleNamespace(summary="done")

    def receive(message, sender, request_reply=None, silent=None, *args, **kwargs):
        return None

    def execute_function(func_call, *args, **kwargs):
        return function_result if function_result is not None else {"content": "42"}

    return SimpleNamespace(
        name=name, initiate_chat=initiate_chat, receive=receive, execute_function=execute_function
    )


def test_initiate_chat_records_conversation_start_and_end(tmp_path):
    tracer = _tracer(tmp_path)
    agent = _make_agent(name="initiator", chat_result=SimpleNamespace(summary="all done"))
    hook = ChronicleAutoGenHook(agent, tracer)
    recipient = SimpleNamespace(name="responder")

    hook.initiate_chat(recipient=recipient, message="hello there")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "agent_message"
    assert events[0]["data"]["event"] == "conversation_start"
    assert events[0]["data"]["initiator"] == "initiator"
    assert events[0]["data"]["recipient"] == "responder"
    assert events[0]["data"]["initial_message"] == "hello there"

    assert events[1]["data"]["event"] == "conversation_end"
    assert events[1]["data"]["final_message"] == "all done"
    assert events[1]["data"]["total_messages"] == 0
    assert events[1]["duration_ms"] is not None


def test_receive_records_process_message_with_sender_and_content(tmp_path):
    tracer = _tracer(tmp_path)
    agent = _make_agent(name="responder")
    hook = ChronicleAutoGenHook(agent, tracer)
    sender = SimpleNamespace(name="initiator")

    hook.receive(message={"content": "what's the weather?"}, sender=sender)
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "agent_message"
    assert events[0]["data"]["event"] == "process_message"
    assert events[0]["data"]["sender"] == "initiator"
    assert events[0]["data"]["recipient"] == "responder"
    assert events[0]["data"]["message"] == "what's the weather?"


def test_receive_captures_token_usage_when_present(tmp_path):
    tracer = _tracer(tmp_path)
    agent = _make_agent()
    hook = ChronicleAutoGenHook(agent, tracer)

    hook.receive(
        message={"content": "hi", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
        sender=SimpleNamespace(name="initiator"),
    )
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["token_usage"] == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


def test_initiate_chat_counts_messages_received_during_the_conversation(tmp_path):
    tracer = _tracer(tmp_path)

    def initiate_chat(recipient, message, *args, **kwargs):
        hook.receive(message="reply 1", sender=recipient)
        hook.receive(message="reply 2", sender=recipient)
        return SimpleNamespace(summary="wrapped up")

    agent = SimpleNamespace(name="initiator", initiate_chat=initiate_chat, receive=lambda *a, **kw: None)
    hook = ChronicleAutoGenHook(agent, tracer)

    hook.initiate_chat(recipient=SimpleNamespace(name="responder"), message="start")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    conversation_end = next(e for e in events if e["data"].get("event") == "conversation_end")
    assert conversation_end["data"]["total_messages"] == 2


def test_execute_function_records_tool_call_and_tool_result(tmp_path):
    tracer = _tracer(tmp_path)
    agent = _make_agent(function_result="42")
    hook = ChronicleAutoGenHook(agent, tracer)

    hook.execute_function({"name": "calculator", "arguments": {"expr": "6*7"}})
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "tool_call"
    assert events[0]["data"]["event"] == "tool_call"
    assert events[0]["data"]["tool_name"] == "calculator"
    assert events[0]["data"]["arguments"] == {"expr": "6*7"}

    assert events[1]["event_type"] == "tool_call"
    assert events[1]["data"]["event"] == "tool_result"
    assert events[1]["data"]["result"] == "42"
    assert events[1]["duration_ms"] is not None


def test_hook_delegates_unknown_attributes_to_the_wrapped_agent(tmp_path):
    tracer = _tracer(tmp_path)
    agent = _make_agent()
    agent.custom_attribute = "value"
    hook = ChronicleAutoGenHook(agent, tracer)

    assert hook.custom_attribute == "value"


def test_hook_falls_back_to_default_agent_name_when_agent_has_no_name(tmp_path):
    tracer = _tracer(tmp_path)
    agent = SimpleNamespace(
        initiate_chat=lambda recipient, message, *a, **kw: SimpleNamespace(summary="ok"),
        receive=lambda *a, **kw: None,
        execute_function=lambda *a, **kw: None,
    )
    hook = ChronicleAutoGenHook(agent, tracer, agent_name="fallback-agent")

    hook.initiate_chat(recipient=None, message="hi")
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["agent_name"] == "fallback-agent"
    assert events[0]["data"]["recipient"] == "unknown"
