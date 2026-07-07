"""AutoGen adapter: wraps a ConversableAgent to capture conversations, messages, and tool calls.

`ChronicleAutoGenHook` is not a subclass of `autogen.ConversableAgent`
(avoiding a hard dependency on `pyautogen`) — it delegates every attribute
other than the instrumented methods to the wrapped agent via `__getattr__`,
so `chronicle.instrument(agent)` is a drop-in replacement. Maps onto the
existing `agent_message`/`tool_call` event types (rather than introducing new
ones), matching the convention established by `chronicle.adapters.openai_agents`.
"""

from __future__ import annotations

import time
from typing import Any

from chronicle.memory_diff import json_safe_dict, record_memory_update
from chronicle.models import TokenUsage
from chronicle.tracer import ChronicleTracer


def _extract_state(kwargs: dict[str, Any]) -> Any:
    """Looks for a `state`/`memory` dict passed to `initiate_chat(...)`, per the SDK's
    memory-capture convention (see `chronicle.memory_diff`).
    """
    for name in ("state", "memory"):
        value = kwargs.get(name)
        if isinstance(value, dict):
            return value
    return None


class ChronicleAutoGenHook:
    """Records an AutoGen `ConversableAgent`'s conversation/message/tool activity."""

    def __init__(self, agent: Any, tracer: ChronicleTracer, agent_name: str = "agent") -> None:
        self._agent = agent
        self.tracer = tracer
        self.agent_name = getattr(agent, "name", None) or agent_name
        self._message_count = 0
        self._conversation_start: float | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)

    def initiate_chat(self, recipient: Any = None, message: Any = None, *args: Any, **kwargs: Any) -> Any:
        """Instruments a full conversation: `conversation_start` before, `conversation_end` after."""
        recipient_name = _agent_name(recipient, "unknown")
        self._conversation_start = time.time()
        self._message_count = 0
        before_state = _extract_state(kwargs)
        before_snapshot = json_safe_dict(before_state) if before_state is not None else None
        self.tracer.record_event(
            "agent_message",
            data={
                "event": "conversation_start",
                "initiator": self.agent_name,
                "recipient": recipient_name,
                "initial_message": _extract_message_content(message),
            },
            agent_name=self.agent_name,
        )

        result = self._agent.initiate_chat(recipient, message, *args, **kwargs)

        if before_snapshot is not None:
            record_memory_update(self.tracer, self.agent_name, before_snapshot, _extract_state(kwargs))

        self.tracer.record_event(
            "agent_message",
            data={
                "event": "conversation_end",
                "final_message": _extract_final_message(result),
                "total_messages": self._message_count,
            },
            agent_name=self.agent_name,
            duration_ms=_elapsed_ms(self._conversation_start),
        )
        return result

    def receive(
        self,
        message: Any = None,
        sender: Any = None,
        request_reply: bool | None = None,
        silent: bool | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Instruments each message processed by this agent (`process_message`)."""
        self._message_count += 1
        sender_name = _agent_name(sender, "unknown")
        self.tracer.record_event(
            "agent_message",
            data={
                "event": "process_message",
                "sender": sender_name,
                "recipient": self.agent_name,
                "message": _extract_message_content(message),
            },
            agent_name=self.agent_name,
            token_usage=_extract_token_usage(message),
        )
        return self._agent.receive(message, sender, request_reply, silent, *args, **kwargs)

    def execute_function(self, func_call: Any, *args: Any, **kwargs: Any) -> Any:
        """Instruments AutoGen's function/tool execution with `tool_call`/`tool_result` events."""
        tool_name = _function_name(func_call)
        start = time.time()
        self.tracer.record_event(
            "tool_call",
            data={"event": "tool_call", "tool_name": tool_name, "arguments": _function_arguments(func_call)},
            agent_name=self.agent_name,
        )
        result = self._agent.execute_function(func_call, *args, **kwargs)
        self.tracer.record_event(
            "tool_call",
            data={"event": "tool_result", "tool_name": tool_name, "result": str(result)},
            agent_name=self.agent_name,
            duration_ms=_elapsed_ms(start),
        )
        return result


def _agent_name(agent: Any, default: str) -> str:
    if agent is None:
        return default
    return getattr(agent, "name", None) or default


def _extract_message_content(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(message)


def _extract_final_message(result: Any) -> str:
    summary = getattr(result, "summary", None)
    if summary is not None:
        return str(summary)
    history = getattr(result, "chat_history", None)
    if history:
        return _extract_message_content(history[-1])
    return str(result)


def _function_name(func_call: Any) -> str:
    if isinstance(func_call, dict):
        return func_call.get("name", "unknown")
    return getattr(func_call, "name", None) or "unknown"


def _function_arguments(func_call: Any) -> Any:
    if isinstance(func_call, dict):
        return func_call.get("arguments", {})
    return getattr(func_call, "arguments", {})


def _extract_token_usage(message: Any) -> TokenUsage | None:
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    return TokenUsage(
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    )


def _elapsed_ms(start: float | None) -> float | None:
    if start is None:
        return None
    return (time.time() - start) * 1000
