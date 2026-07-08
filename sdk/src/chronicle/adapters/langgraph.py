"""LangGraph/LangChain callback adapter that forwards lifecycle events to a ChronicleTracer.

`langchain_core` is an optional dependency. If it is installed, `LangGraphAdapter`
subclasses `BaseCallbackHandler` so it can be passed straight into a LangGraph
or LangChain `config={"callbacks": [...]}` call. If it isn't installed, the
adapter still works as a plain duck-typed object exposing the same hooks, and
none of this module's tests require LangChain to be installed.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from chronicle.chaos import ChaosConfig, ChaosMixin
from chronicle.memory_diff import json_safe_dict, record_memory_update
from chronicle.models import StateSnapshot, TokenUsage
from chronicle.tracer import ChronicleTracer

try:
    from langchain_core.callbacks import BaseCallbackHandler as _BaseCallbackHandler
except ImportError:  # pragma: no cover - exercised only without langchain installed
    _BaseCallbackHandler = object

logger = logging.getLogger("chronicle")


class LangGraphAdapter(_BaseCallbackHandler):  # type: ignore[misc]
    """Forwards LangGraph/LangChain lifecycle callbacks to a `ChronicleTracer`."""

    def __init__(
        self,
        tracer: ChronicleTracer,
        agent_name: str = "agent",
        graph: Any = None,
        graph_module: str | None = None,
        graph_attr: str | None = None,
        chaos: ChaosConfig | None = None,
    ) -> None:
        """`graph`/`graph_module`/`graph_attr` are optional; if all three are given, the
        graph is auto-registered with the server (via `tracer.register_graph`) so
        `POST /replay` can re-invoke it later. See `ChronicleTracer.register_graph`.

        `chaos`, if given, activates synthetic tool-call failure/latency/malformed-
        response injection for this run (see `chronicle.chaos`) — never applied to
        LLM calls. `None` (the default) means chaos is fully inactive; there is no
        way to end up with chaos behavior without explicitly passing a `ChaosConfig`.
        """
        self.tracer = tracer
        self.agent_name = agent_name
        self._pending: dict[UUID, dict[str, Any]] = {}
        self._pending_memory: dict[UUID, dict[str, Any]] = {}
        self._step_index = 0
        self._chaos = ChaosMixin(chaos) if chaos is not None else None
        if graph is not None and graph_module is not None and graph_attr is not None:
            tracer.register_graph(graph, graph_module, graph_attr)

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
        tool_name = serialized.get("name", "unknown")
        self._pending[run_id] = {
            "start": time.time(),
            "tool_name": tool_name,
            "input": input_str,
        }

        if self._chaos is not None:
            if self._chaos.should_fail(tool_name):
                self._chaos.raise_configured_failure()
            delay_ms = self._chaos.latency_ms(tool_name)
            if delay_ms > 0:
                time.sleep(delay_ms / 1000)

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        pending = self._pending.pop(run_id, {})
        tool_name = pending.get("tool_name", "unknown")

        result = output
        if self._chaos is not None and self._chaos.should_malform():
            # Callback handlers can only observe a tool call, not rewrite what the
            # agent already received — this substitutes what gets *recorded*, so
            # the malformed response is still visible for chaos-testing analysis.
            result = self._chaos.config.malformed_response_value

        self.tracer.record_event(
            "tool_call",
            data={
                "tool_name": tool_name,
                "arguments": {"input": pending.get("input", "")},
                "result": str(result),
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
        return_values = getattr(finish, "return_values", None)
        self._capture_snapshot(return_values if isinstance(return_values, dict) else {})

    def on_chain_start(
        self, serialized: dict[str, Any], inputs: dict[str, Any], *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._pending_memory[run_id] = json_safe_dict(inputs)

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        before = self._pending_memory.pop(run_id, None)
        if before is not None:
            record_memory_update(self.tracer, self.agent_name, before, outputs)
        self._capture_snapshot(outputs)

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self.tracer.record_event(
            "error",
            data={"error_type": type(error).__name__},
            agent_name=self.agent_name,
            error=str(error),
        )

    def _capture_snapshot(self, graph_state: Any) -> None:
        """Builds and ships a `StateSnapshot` from a LangGraph output dict.

        Never raises: Chronicle must have zero impact on the agent even if
        the graph state can't be captured for some reason.
        """
        try:
            if not isinstance(graph_state, dict):
                return

            safe_state, state_warned = _json_safe(graph_state)
            messages, messages_warned = _json_safe(graph_state.get("messages", []))
            if not isinstance(messages, list):
                messages = []
            tool_results, tool_warned = _json_safe(graph_state.get("tool_results", []))
            if not isinstance(tool_results, list):
                tool_results = []

            metadata: dict[str, Any] = {}
            if state_warned or messages_warned or tool_warned:
                metadata["_serialization_warning"] = True

            snapshot = StateSnapshot(
                run_id=self.tracer.run_id,
                step_index=self._step_index,
                agent_name=self.agent_name,
                messages=messages,
                tool_results=tool_results,
                graph_state=safe_state if isinstance(safe_state, dict) else {},
                metadata=metadata,
            )
            self._step_index += 1
            self.tracer.record_snapshot(snapshot)
        except Exception:  # pragma: no cover - defensive: never crash the agent
            logger.warning("Chronicle: failed to capture state snapshot", exc_info=True)


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


def _json_safe(value: Any, _seen: frozenset[int] | None = None) -> tuple[Any, bool]:
    """Recursively converts `value` into something JSON-serializable.

    Dicts/lists/tuples are walked recursively; strings, numbers, bools, and
    `None` pass through unchanged. Anything else (LangChain message objects,
    datetimes, custom classes, ...) is converted via `str()`. Returns
    `(safe_value, encountered_non_serializable)` so callers can flag a
    `_serialization_warning` without needing a second pass.

    `_seen` tracks the `id()`s of containers currently being walked on the
    current recursion path (not a global visited set, so sibling branches that
    happen to share a sub-object aren't falsely flagged). Live graph state can
    contain genuine reference cycles - e.g. a LangChain message object with a
    `.parent`/back-reference - which would otherwise blow the stack with
    infinite recursion before this ever reaches JSON encoding. When a cycle is
    detected, the repeated container is replaced with a marker string instead
    of being walked again.
    """
    if isinstance(value, (dict, list, tuple)):
        if _seen is not None and id(value) in _seen:
            return "<circular reference>", True
        seen = (_seen or frozenset()) | {id(value)}

        if isinstance(value, dict):
            safe_dict: dict[str, Any] = {}
            warned = False
            for key, val in value.items():
                safe_val, val_warned = _json_safe(val, seen)
                safe_dict[str(key)] = safe_val
                warned = warned or val_warned
            return safe_dict, warned

        safe_list: list[Any] = []
        warned = False
        for item in value:
            safe_item, item_warned = _json_safe(item, seen)
            safe_list.append(safe_item)
            warned = warned or item_warned
        return safe_list, warned

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value, False

    return str(value), True
