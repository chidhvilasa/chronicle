"""LangGraph/LangChain callback handler that forwards events to a ChronicleTracer.

`langchain_core` is an optional dependency. If it is installed, the handler
subclasses `BaseCallbackHandler` so it can be passed straight into a LangGraph
or LangChain `config={"callbacks": [...]}` call. If it isn't installed, the
handler still works as a plain duck-typed object exposing the same methods.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from chronicle.tracer import ChronicleTracer

try:
    from langchain_core.callbacks import BaseCallbackHandler as _BaseCallbackHandler
except ImportError:  # pragma: no cover - exercised only without langchain installed
    _BaseCallbackHandler = object


class ChronicleCallbackHandler(_BaseCallbackHandler):  # type: ignore[misc]
    """Forwards LangChain/LangGraph lifecycle events to a `ChronicleTracer`."""

    def __init__(self, tracer: ChronicleTracer) -> None:
        self.tracer = tracer

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, **kwargs: Any
    ) -> None:
        self.tracer.tool_call(
            tool_name=serialized.get("name", "unknown"),
            arguments={"input": input_str},
        )

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self.tracer.log_event("tool_call", {"result": str(output)})

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], *, run_id: UUID, **kwargs: Any
    ) -> None:
        self.tracer.llm_call(
            model=serialized.get("name", "unknown"),
            prompt=prompts[0] if prompts else "",
        )

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self.tracer.log_event("llm_call", {"completion": str(response)})

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self.tracer.error(message=str(error), error_type=type(error).__name__)

    def on_agent_action(self, action: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self.tracer.agent_message(role="agent", content=str(action))
