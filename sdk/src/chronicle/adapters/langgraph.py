"""LangGraph/LangChain callback adapter that forwards lifecycle events to a ChronicleTracer.

`langchain_core` is an optional dependency. If it is installed, `LangGraphAdapter`
subclasses `BaseCallbackHandler` so it can be passed straight into a LangGraph
or LangChain `config={"callbacks": [...]}` call. If it isn't installed, the
adapter still works as a plain duck-typed object exposing the same hooks, and
none of this module's tests require LangChain to be installed.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from chronicle.models import TokenUsage
from chronicle.tracer import ChronicleTracer

try:
    from langchain_core.callbacks import BaseCallbackHandler as _BaseCallbackHandler
except ImportError:  # pragma: no cover - exercised only without langchain installed
    _BaseCallbackHandler = object


class LangGraphAdapter(_BaseCallbackHandler):  # type: ignore[misc]
    """Forwards LangGraph/LangChain lifecycle callbacks to a `ChronicleTracer`."""

    def __init__(self, tracer: ChronicleTracer, agent_name: str = "agent") -> None:
        self.tracer = tracer
        self.agent_name = agent_name
        self._pending: dict[UUID, dict[str, Any]] = {}

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._pending[run_id] = {
            "start": time.time(),
            "prompts": prompts,
            "model": serialized.get("name", "unknown"),
        }

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        pending = self._pending.pop(run_id, {})
        self.tracer.record_event(
            "llm_call",
            data={
                "model": pending.get("model", "unknown"),
                "prompts": pending.get("prompts", []),
                "completion": _extract_completion_text(response),
            },
            agent_name=self.agent_name,
            duration_ms=_elapsed_ms(pending.get("start")),
            token_usage=_extract_token_usage(response),
        )

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._pending[run_id] = {
            "start": time.time(),
            "tool_name": serialized.get("name", "unknown"),
            "input": input_str,
        }

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        pending = self._pending.pop(run_id, {})
        self.tracer.record_event(
            "tool_call",
            data={
                "tool_name": pending.get("tool_name", "unknown"),
                "arguments": {"input": pending.get("input", "")},
                "result": str(output),
            },
            agent_name=self.agent_name,
            duration_ms=_elapsed_ms(pending.get("start")),
        )

    def on_agent_action(self, action: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self.tracer.record_event(
            "agent_message",
            data={"role": "agent", "content": str(action)},
            agent_name=self.agent_name,
        )

    def on_agent_finish(self, finish: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self.tracer.record_event(
            "agent_message",
            data={"role": "agent", "content": str(finish)},
            agent_name=self.agent_name,
        )

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self.tracer.record_event(
            "error",
            data={"error_type": type(error).__name__},
            agent_name=self.agent_name,
            error=str(error),
        )


def _elapsed_ms(start: float | None) -> float | None:
    if start is None:
        return None
    return (time.time() - start) * 1000


def _extract_token_usage(response: Any) -> TokenUsage | None:
    llm_output = getattr(response, "llm_output", None) or {}
    usage = llm_output.get("token_usage") or llm_output.get("usage")
    if not usage:
        return None
    return TokenUsage(
        input_tokens=usage.get("prompt_tokens", usage.get("input_tokens")),
        output_tokens=usage.get("completion_tokens", usage.get("output_tokens")),
        total_tokens=usage.get("total_tokens"),
    )


def _extract_completion_text(response: Any) -> str:
    generations = getattr(response, "generations", None) or []
    texts = [
        gen.text
        for gen_list in generations
        for gen in gen_list
        if getattr(gen, "text", None)
    ]
    return "\n".join(texts)
