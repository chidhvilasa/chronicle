"""Semantic Kernel adapter: forwards kernel function/chat invocation hooks to a ChronicleTracer.

`ChronicleKernelPlugin` is a duck-typed implementation of Semantic Kernel's
invocation-hook interface - not a subclass of any `semantic_kernel` class, so
`semantic-kernel` is never imported here and never becomes a hard dependency.
Any object exposing `pre_invocation_hook`/`post_invocation_hook`/
`pre_chat_hook`/`post_chat_hook` can be added to a `Kernel`'s `plugins` list.

Maps onto the existing `tool_call`/`llm_call` event types (rather than
introducing new ones), matching the convention established by
`chronicle.adapters.openai_agents`: a kernel function invocation is
conceptually a tool call (`function_start`/`function_end` sub-events), and
the pre/post chat hook pair is one `llm_call` (`llm_call`/`llm_result`
sub-events) - so both ends of each pair share one event type and are
distinguished by `data["event"]`.
"""

from __future__ import annotations

import time
from typing import Any

from chronicle.models import TokenUsage
from chronicle.tracer import ChronicleTracer


class ChronicleKernelPlugin:
    """Records Semantic Kernel function/chat invocation hooks as Chronicle events."""

    def __init__(self, tracer: ChronicleTracer, agent_name: str = "agent") -> None:
        self.tracer = tracer
        self.agent_name = agent_name
        self._start_times: dict[str, float] = {}

    def pre_invocation_hook(
        self,
        function_name: str = "",
        plugin_name: str = "",
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._start_times[f"function:{plugin_name}.{function_name}"] = time.time()
        self.tracer.record_event(
            "tool_call",
            data={
                "event": "function_start",
                "function_name": function_name,
                "plugin_name": plugin_name,
                "arguments": arguments or {},
            },
            agent_name=self.agent_name,
        )

    def post_invocation_hook(
        self, function_name: str = "", plugin_name: str = "", result: Any = None, **kwargs: Any
    ) -> None:
        start = self._start_times.pop(f"function:{plugin_name}.{function_name}", None)
        self.tracer.record_event(
            "tool_call",
            data={
                "event": "function_end",
                "function_name": function_name,
                "plugin_name": plugin_name,
                "result": str(result),
            },
            agent_name=self.agent_name,
            duration_ms=_elapsed_ms(start),
            token_usage=_extract_token_usage(result),
        )

    def pre_chat_hook(self, messages: Any = None, **kwargs: Any) -> None:
        self._start_times["chat"] = time.time()
        self.tracer.record_event(
            "llm_call",
            data={"event": "llm_call", "messages": _serialize_messages(messages)},
            agent_name=self.agent_name,
        )

    def post_chat_hook(
        self, response: Any = None, finish_reason: str | None = None, **kwargs: Any
    ) -> None:
        start = self._start_times.pop("chat", None)
        self.tracer.record_event(
            "llm_call",
            data={
                "event": "llm_result",
                "response": _extract_response_content(response),
                "finish_reason": finish_reason,
            },
            agent_name=self.agent_name,
            duration_ms=_elapsed_ms(start),
            token_usage=_extract_token_usage(response),
        )


def _serialize_messages(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    serialized: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, dict):
            serialized.append({"role": message.get("role", "user"), "content": str(message.get("content", ""))})
        else:
            role = getattr(message, "role", None) or "user"
            content = getattr(message, "content", None)
            serialized.append({"role": str(role), "content": str(content if content is not None else message)})
    return serialized


def _extract_response_content(response: Any) -> str:
    if response is None:
        return ""
    content = getattr(response, "content", None)
    return str(content) if content is not None else str(response)


def _extract_token_usage(value: Any) -> TokenUsage | None:
    metadata = getattr(value, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    usage = metadata.get("usage") or metadata.get("token_usage")
    if usage is None:
        return None
    get = usage.get if isinstance(usage, dict) else lambda name, default=None: getattr(usage, name, default)
    return TokenUsage(
        input_tokens=get("prompt_tokens", get("input_tokens")),
        output_tokens=get("completion_tokens", get("output_tokens")),
        total_tokens=get("total_tokens"),
    )


def _elapsed_ms(start: float | None) -> float | None:
    if start is None:
        return None
    return (time.time() - start) * 1000
