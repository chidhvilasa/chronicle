"""OpenAI Agents SDK adapter: forwards agent/tool/handoff hooks to a ChronicleTracer.

`ChronicleAgentHooks` is a duck-typed implementation of the OpenAI Agents
SDK's hooks interface — not a subclass of `agents.AgentHooks`, so
`openai-agents` is never imported here and never becomes a hard dependency.
Any object exposing `on_agent_start`/`on_agent_end`/`on_tool_call`/
`on_tool_result`/`on_handoff` can be assigned to an SDK `Agent`'s `hooks`.
"""

from __future__ import annotations

import time
from typing import Any

from chronicle.memory_diff import json_safe_dict, record_memory_update
from chronicle.tracer import ChronicleTracer


def _extract_state(kwargs: dict[str, Any]) -> Any:
    """Looks for a `state`/`memory` dict passed to a hook call, per the SDK's memory-capture
    convention (see `chronicle.memory_diff`) - none of these hooks are guaranteed to receive
    one, so this returns `None` when neither is present.
    """
    for name in ("state", "memory"):
        value = kwargs.get(name)
        if isinstance(value, dict):
            return value
    return None


class ChronicleAgentHooks:
    """Records OpenAI Agents SDK lifecycle hooks as Chronicle events.

    Maps onto the existing `agent_message`/`tool_call` event types (rather
    than introducing new ones) so events from this adapter render in the
    desktop app's timeline exactly like LangGraph events do, with the hook
    name captured in `data["event"]`.
    """

    def __init__(self, tracer: ChronicleTracer, agent_name: str = "agent") -> None:
        self.tracer = tracer
        self.agent_name = agent_name
        self._start_times: dict[str, float] = {}
        self._pending_memory: dict[str, Any] = {}

    def on_agent_start(self, agent: Any = None, input: Any = None, **kwargs: Any) -> None:
        name = _agent_name(agent, self.agent_name)
        self._start_times["agent"] = time.time()
        state = _extract_state(kwargs)
        if state is not None:
            self._pending_memory["agent"] = json_safe_dict(state)
        self.tracer.record_event(
            "agent_message",
            data={"event": "agent_start", "agent_name": name, "input": str(input)},
            agent_name=name,
        )

    def on_agent_end(self, agent: Any = None, output: Any = None, **kwargs: Any) -> None:
        name = _agent_name(agent, self.agent_name)
        start = self._start_times.pop("agent", None)
        before = self._pending_memory.pop("agent", None)
        if before is not None:
            record_memory_update(self.tracer, name, before, _extract_state(kwargs))
        self.tracer.record_event(
            "agent_message",
            data={"event": "agent_end", "agent_name": name, "output": str(output)},
            agent_name=name,
            duration_ms=_elapsed_ms(start),
        )

    def on_tool_call(
        self, tool_name: str = "", arguments: Any = None, agent: Any = None, **kwargs: Any
    ) -> None:
        name = _agent_name(agent, self.agent_name)
        self._start_times[f"tool:{tool_name}"] = time.time()
        self.tracer.record_event(
            "tool_call",
            data={"event": "tool_call", "tool_name": tool_name, "arguments": arguments or {}},
            agent_name=name,
        )

    def on_tool_result(
        self, tool_name: str = "", result: Any = None, agent: Any = None, **kwargs: Any
    ) -> None:
        name = _agent_name(agent, self.agent_name)
        start = self._start_times.pop(f"tool:{tool_name}", None)
        self.tracer.record_event(
            "tool_call",
            data={"event": "tool_result", "tool_name": tool_name, "result": str(result)},
            agent_name=name,
            duration_ms=_elapsed_ms(start),
        )

    def on_handoff(self, source: Any = None, target: Any = None, **kwargs: Any) -> None:
        source_name = _agent_name(source, self.agent_name)
        target_name = _agent_name(target, "unknown")
        self.tracer.record_event(
            "agent_message",
            data={"event": "handoff", "source_agent": source_name, "target_agent": target_name},
            agent_name=source_name,
        )


def _agent_name(agent: Any, default: str) -> str:
    return getattr(agent, "name", None) or default


def _elapsed_ms(start: float | None) -> float | None:
    if start is None:
        return None
    return (time.time() - start) * 1000
