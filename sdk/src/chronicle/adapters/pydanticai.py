"""PydanticAI adapter: wraps an Agent's `run_sync` to capture prompt/response/tool calls/tokens.

`ChronicleMiddleware` is not a subclass of `pydantic_ai.Agent` (avoiding a
hard dependency on `pydantic-ai`) — it delegates every attribute other than
`run_sync` to the wrapped agent via `__getattr__`, so
`chronicle.instrument(agent)` is a drop-in replacement. Only `run_sync` is
instrumented; async `run`/`run_stream` pass straight through unwrapped (see
`KNOWN_ISSUES.md` — async support is planned).
"""

from __future__ import annotations

import time
from typing import Any

from chronicle.memory_diff import json_safe_dict, record_memory_update
from chronicle.models import TokenUsage
from chronicle.tracer import ChronicleTracer


def _extract_state(kwargs: dict[str, Any]) -> Any:
    """Looks for a `state`/`memory` dict passed to `run_sync(...)`, per the SDK's
    memory-capture convention (see `chronicle.memory_diff`).
    """
    for name in ("state", "memory"):
        value = kwargs.get(name)
        if isinstance(value, dict):
            return value
    return None


class ChronicleMiddleware:
    """Records one `llm_call` (or `error`) event per `run_sync()` call on a PydanticAI agent."""

    def __init__(self, agent: Any, tracer: ChronicleTracer, agent_name: str = "agent") -> None:
        self._agent = agent
        self.tracer = tracer
        self.agent_name = getattr(agent, "name", None) or agent_name

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)

    def run_sync(self, prompt: Any = None, *args: Any, **kwargs: Any) -> Any:
        model_name = _extract_model_name(self._agent)
        before_state = _extract_state(kwargs)
        # Captured as an independent snapshot now, in case `run_sync` mutates the same
        # dict object in place - otherwise "before" and "after" would alias one another.
        before_snapshot = json_safe_dict(before_state) if before_state is not None else None
        start = time.time()
        try:
            result = self._agent.run_sync(prompt, *args, **kwargs)
        except Exception as exc:
            self.tracer.record_event(
                "error",
                data={"error_type": type(exc).__name__, "model": model_name, "prompt": str(prompt)},
                agent_name=self.agent_name,
                duration_ms=_elapsed_ms(start),
                error=str(exc),
            )
            raise

        if before_snapshot is not None:
            record_memory_update(self.tracer, self.agent_name, before_snapshot, _extract_state(kwargs))

        self.tracer.record_event(
            "llm_call",
            data={
                "model": model_name,
                "prompt": str(prompt),
                "response": _extract_response_text(result),
                "tool_calls": _extract_tool_calls(result),
            },
            agent_name=self.agent_name,
            duration_ms=_elapsed_ms(start),
            token_usage=_extract_token_usage(result),
        )
        return result


def _extract_model_name(agent: Any) -> str:
    model = getattr(agent, "model", None)
    if model is None:
        return "unknown"
    return getattr(model, "model_name", None) or getattr(model, "name", None) or str(model)


def _extract_response_text(result: Any) -> str:
    for attr in ("output", "data"):
        value = getattr(result, attr, None)
        if value is not None:
            return str(value)
    return str(result)


def _extract_tool_calls(result: Any) -> list[dict[str, Any]]:
    messages_attr = getattr(result, "all_messages", None)
    messages = messages_attr() if callable(messages_attr) else messages_attr
    if not messages:
        return []

    calls: list[dict[str, Any]] = []
    for message in messages:
        for part in getattr(message, "parts", None) or []:
            if type(part).__name__ == "ToolCallPart":
                calls.append(
                    {"tool_name": getattr(part, "tool_name", None), "args": getattr(part, "args", None)}
                )
    return calls


def _extract_token_usage(result: Any) -> TokenUsage | None:
    usage_fn = getattr(result, "usage", None)
    if not callable(usage_fn):
        return None
    usage = usage_fn()
    if usage is None:
        return None
    return TokenUsage(
        input_tokens=getattr(usage, "request_tokens", None),
        output_tokens=getattr(usage, "response_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )


def _elapsed_ms(start: float) -> float:
    return (time.time() - start) * 1000
