"""Zero-friction auto-instrumentation: `chronicle.instrument(obj)`.

Detects which framework `obj` belongs to (LangGraph, OpenAI Agents SDK, or
PydanticAI) and wires up the matching adapter automatically, starting the
Chronicle server in the background if one isn't already running. No manual
`ChronicleTracer`/adapter construction required — see `README.md`'s
Quickstart.
"""

from __future__ import annotations

import sys
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Literal

from chronicle.adapters.langgraph import LangGraphAdapter
from chronicle.adapters.openai_agents import ChronicleAgentHooks
from chronicle.adapters.pydanticai import ChronicleMiddleware
from chronicle.server_manager import ServerManager
from chronicle.tracer import ChronicleTracer

FrameworkName = Literal["langgraph", "openai_agents", "pydanticai", "unknown"]

_UNKNOWN_FRAMEWORK_MESSAGE = (
    "Chronicle: detected unknown framework type. LangGraph, OpenAI Agents SDK, "
    "and PydanticAI are supported. Manual adapter setup may be required."
)


def _detect_framework(obj: Any) -> FrameworkName:
    """Identifies which supported framework `obj` came from.

    Detection is by module path and class name only — it never imports
    `langgraph`, `agents`, or `pydantic_ai` to do this, so calling
    `instrument()` never raises `ImportError` for a framework that isn't
    installed (and works against plain mock objects in tests, which don't
    need the real frameworks installed either).
    """
    module_root = (type(obj).__module__ or "").split(".")[0]
    class_name = type(obj).__name__

    if module_root in ("langgraph", "langchain_core", "langchain"):
        return "langgraph"
    if module_root == "agents" and class_name == "Agent":
        return "openai_agents"
    if module_root == "pydantic_ai" and class_name == "Agent":
        return "pydanticai"
    return "unknown"


def _resolve_module_and_attr(obj: Any) -> tuple[str | None, str | None]:
    """Best-effort: finds the caller's module + top-level variable name bound to `obj`.

    Used to auto-call `tracer.register_graph()` without requiring the
    caller to pass `module_path`/`attr_name` explicitly (see
    `ChronicleTracer.register_graph`). Walks the call stack looking for the
    first frame outside `chronicle.auto` and matches `obj` by identity
    against that frame's module-level globals — this covers the common
    `graph = chronicle.instrument(graph)` pattern at module scope. Returns
    `(None, None)` (never raises) if nothing matches, e.g. because `obj`
    was built inside a function and isn't a module-level variable yet;
    replay registration is then simply skipped.
    """
    try:
        frame = sys._getframe(1)
        while frame is not None:
            if frame.f_globals.get("__name__") != __name__:
                for var_name, var_value in frame.f_globals.items():
                    if var_value is obj:
                        return frame.f_globals.get("__name__"), var_name
                return None, None
            frame = frame.f_back
    except Exception:  # pragma: no cover - defensive: frame introspection must never crash
        pass
    return None, None


class _InstrumentedGraph:
    """Thin proxy around a LangGraph graph that injects a Chronicle callback into every call.

    LangGraph has no persistent "attach a callback to this graph" hook —
    callbacks are passed per-invocation via `config={"callbacks": [...]}`.
    This proxy is the modified graph `instrument()` returns: every other
    attribute (including `.get_graph()`, `.nodes`, etc.) delegates straight
    through to the wrapped graph via `__getattr__`.
    """

    def __init__(self, graph: Any, adapter: LangGraphAdapter) -> None:
        self._graph = graph
        self._adapter = adapter

    def __getattr__(self, name: str) -> Any:
        return getattr(self._graph, name)

    def _with_callback(self, config: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(config) if config else {}
        callbacks = list(merged.get("callbacks") or [])
        if self._adapter not in callbacks:
            callbacks.append(self._adapter)
        merged["callbacks"] = callbacks
        return merged

    def invoke(self, input: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        return self._graph.invoke(input, self._with_callback(config), **kwargs)

    async def ainvoke(self, input: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        return await self._graph.ainvoke(input, self._with_callback(config), **kwargs)

    def stream(self, input: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        return self._graph.stream(input, self._with_callback(config), **kwargs)

    async def astream(self, input: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        async for chunk in self._graph.astream(input, self._with_callback(config), **kwargs):
            yield chunk


def _instrument_langgraph(graph: Any, tracer: ChronicleTracer, agent_name: str) -> Any:
    adapter = LangGraphAdapter(tracer, agent_name=agent_name)
    wrapped = _InstrumentedGraph(graph, adapter)
    module_name, attr_name = _resolve_module_and_attr(graph)
    if module_name and attr_name:
        tracer.register_graph(graph, module_name, attr_name)
    return wrapped


def _instrument_openai_agents(agent: Any, tracer: ChronicleTracer, agent_name: str) -> Any:
    hooks = ChronicleAgentHooks(tracer, agent_name=getattr(agent, "name", None) or agent_name)
    agent.hooks = hooks
    return agent


def _instrument_pydanticai(agent: Any, tracer: ChronicleTracer, agent_name: str) -> Any:
    return ChronicleMiddleware(agent, tracer, agent_name=agent_name)


def _build(obj: Any, agent_name: str | None) -> tuple[Any, ChronicleTracer]:
    """Shared wiring logic behind both `instrument()` and `instrument_context()`."""
    tracer = ChronicleTracer()
    resolved_name = agent_name or f"session-{uuid.uuid4().hex[:8]}"

    framework = _detect_framework(obj)
    if framework == "langgraph":
        result = _instrument_langgraph(obj, tracer, resolved_name)
    elif framework == "openai_agents":
        result = _instrument_openai_agents(obj, tracer, resolved_name)
    elif framework == "pydanticai":
        result = _instrument_pydanticai(obj, tracer, resolved_name)
    else:
        print(_UNKNOWN_FRAMEWORK_MESSAGE)
        result = obj

    return result, tracer


def instrument(obj: Any, *, agent_name: str | None = None) -> Any:
    """One-line auto-instrumentation. Detects `obj`'s framework, wires up Chronicle, returns `obj`.

    ```python
    import chronicle
    graph = chronicle.instrument(graph)
    ```

    Starts the Chronicle server in the background if it isn't already
    running on `localhost:7823` (see `ServerManager`); if that fails,
    tracing still works, falling back to local `chronicle_runs/*.json`
    files, exactly like `ChronicleTracer` always has. Never raises for an
    unsupported/undetected framework — `obj` is returned unmodified and a
    message is printed instead.
    """
    result, tracer = _build(obj, agent_name)

    if ServerManager().ensure_running():
        print(f"Chronicle: recording to {tracer.server_url} — open the desktop app to inspect")
    else:
        print("Chronicle: server unavailable, writing to chronicle_runs/ locally")

    return result


@contextmanager
def instrument_context(obj: Any, *, agent_name: str | None = None) -> Iterator[Any]:
    """Context-manager variant of `instrument()`.

    ```python
    with chronicle.instrument_context(graph) as instrumented_graph:
        result = instrumented_graph.invoke(input)
    ```

    On exit, flushes every buffered event and prints a one-line run summary
    instead of `instrument()`'s startup message.
    """
    result, tracer = _build(obj, agent_name)
    ServerManager().ensure_running()

    stats = {"events": 0, "tokens": 0}
    original_record_event = tracer.record_event

    def _counting_record_event(*args: Any, **kwargs: Any) -> Any:
        event = original_record_event(*args, **kwargs)
        stats["events"] += 1
        if event.token_usage is not None and event.token_usage.total_tokens is not None:
            stats["tokens"] += event.token_usage.total_tokens
        return event

    tracer.record_event = _counting_record_event  # type: ignore[method-assign]

    start = time.time()
    try:
        yield result
    finally:
        tracer.close()
        duration_ms = (time.time() - start) * 1000
        print(
            f"Chronicle: run complete — {stats['events']} events, {stats['tokens']} tokens, "
            f"{duration_ms:.0f}ms — run_id: {tracer.run_id}"
        )
