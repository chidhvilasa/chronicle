"""CrewAI adapter: forwards crew/agent/task/tool lifecycle callbacks to a ChronicleTracer.

`ChronicleCrewAICallbackHandler` is a duck-typed implementation of CrewAI's
callback handler interface — not a subclass of `crewai.BaseCallbackHandler`,
so `crewai` is never imported here and never becomes a hard dependency. Any
object exposing `on_crew_start`/`on_crew_end`/`on_agent_start`/`on_agent_end`/
`on_task_start`/`on_task_end`/`on_tool_start`/`on_tool_end`/`on_tool_error`
can be appended to a `Crew`'s `callbacks` list.
"""

from __future__ import annotations

import time
from typing import Any

from chronicle.memory_diff import json_safe_dict, record_memory_update
from chronicle.models import TokenUsage
from chronicle.tracer import ChronicleTracer


def _extract_state(kwargs: dict[str, Any]) -> Any:
    """Looks for a `state`/`memory` dict passed to a hook call, per the SDK's memory-capture
    convention (see `chronicle.memory_diff`).
    """
    for name in ("state", "memory"):
        value = kwargs.get(name)
        if isinstance(value, dict):
            return value
    return None


class ChronicleCrewAICallbackHandler:
    """Records CrewAI lifecycle callbacks as Chronicle events.

    Maps onto the existing `agent_message`/`tool_call`/`error` event types
    (rather than introducing new ones) so CrewAI runs render in the desktop
    app exactly like every other adapter's events do, with the specific
    lifecycle hook captured in `data["event"]`.
    """

    def __init__(self, tracer: ChronicleTracer, agent_name: str = "agent") -> None:
        self.tracer = tracer
        self.agent_name = agent_name
        self._start_times: dict[str, float] = {}
        self._pending_memory: dict[str, Any] = {}

    def on_crew_start(self, crew: Any = None, inputs: dict[str, Any] | None = None, **kwargs: Any) -> None:
        self._start_times["crew"] = time.time()
        state = _extract_state(kwargs)
        if state is not None:
            self._pending_memory["crew"] = json_safe_dict(state)
        self.tracer.record_event(
            "agent_message",
            data={
                "event": "crew_start",
                "crew_name": _crew_name(crew),
                "agent_names": _crew_agent_names(crew),
                "task_names": _crew_task_names(crew),
                "inputs": inputs or {},
            },
            agent_name=self.agent_name,
        )

    def on_crew_end(self, crew: Any = None, output: Any = None, **kwargs: Any) -> None:
        start = self._start_times.pop("crew", None)
        before = self._pending_memory.pop("crew", None)
        if before is not None:
            record_memory_update(self.tracer, self.agent_name, before, _extract_state(kwargs))
        self.tracer.record_event(
            "agent_message",
            data={"event": "crew_end", "crew_name": _crew_name(crew), "output": str(output)},
            agent_name=self.agent_name,
            duration_ms=_elapsed_ms(start),
        )

    def on_agent_start(self, agent: Any = None, task: Any = None, **kwargs: Any) -> None:
        role = _agent_role(agent, self.agent_name)
        self._start_times[f"agent:{role}"] = time.time()
        self.tracer.record_event(
            "agent_message",
            data={
                "event": "agent_start",
                "role": role,
                "goal": _agent_goal(agent),
                "task_name": _task_description(task),
            },
            agent_name=role,
        )

    def on_agent_end(self, agent: Any = None, output: Any = None, **kwargs: Any) -> None:
        role = _agent_role(agent, self.agent_name)
        start = self._start_times.pop(f"agent:{role}", None)
        self.tracer.record_event(
            "agent_message",
            data={"event": "agent_end", "role": role, "output": str(output)},
            agent_name=role,
            duration_ms=_elapsed_ms(start),
        )

    def on_task_start(self, task: Any = None, **kwargs: Any) -> None:
        assigned_agent = _task_agent_name(task, self.agent_name)
        self._start_times[f"task:{_task_description(task)}"] = time.time()
        self.tracer.record_event(
            "agent_message",
            data={
                "event": "task_start",
                "description": _task_description(task),
                "expected_output": _task_expected_output(task),
                "assigned_agent": assigned_agent,
            },
            agent_name=assigned_agent,
        )

    def on_task_end(self, task: Any = None, output: Any = None, **kwargs: Any) -> None:
        assigned_agent = _task_agent_name(task, self.agent_name)
        start = self._start_times.pop(f"task:{_task_description(task)}", None)
        self.tracer.record_event(
            "agent_message",
            data={"event": "task_end", "description": _task_description(task), "output": str(output)},
            agent_name=assigned_agent,
            duration_ms=_elapsed_ms(start),
            token_usage=_extract_token_usage(output),
        )

    def on_tool_start(self, tool_name: str = "", input: Any = None, agent: Any = None, **kwargs: Any) -> None:
        name = _agent_role(agent, self.agent_name)
        self._start_times[f"tool:{tool_name}"] = time.time()
        self.tracer.record_event(
            "tool_call",
            data={"event": "tool_call", "tool_name": tool_name, "input": input},
            agent_name=name,
        )

    def on_tool_end(self, tool_name: str = "", output: Any = None, agent: Any = None, **kwargs: Any) -> None:
        name = _agent_role(agent, self.agent_name)
        start = self._start_times.pop(f"tool:{tool_name}", None)
        self.tracer.record_event(
            "tool_call",
            data={"event": "tool_result", "tool_name": tool_name, "output": str(output)},
            agent_name=name,
            duration_ms=_elapsed_ms(start),
        )

    def on_tool_error(
        self, tool_name: str = "", error: BaseException | str | None = None, agent: Any = None, **kwargs: Any
    ) -> None:
        name = _agent_role(agent, self.agent_name)
        start = self._start_times.pop(f"tool:{tool_name}", None)
        self.tracer.record_event(
            "error",
            data={"event": "tool_error", "tool_name": tool_name},
            agent_name=name,
            duration_ms=_elapsed_ms(start),
            error=str(error),
        )


def _crew_name(crew: Any) -> str:
    return getattr(crew, "name", None) or "crew"


def _crew_agent_names(crew: Any) -> list[str]:
    agents = getattr(crew, "agents", None) or []
    return [_agent_role(agent, "unknown") for agent in agents]


def _crew_task_names(crew: Any) -> list[str]:
    tasks = getattr(crew, "tasks", None) or []
    return [_task_description(task) for task in tasks]


def _agent_role(agent: Any, default: str) -> str:
    return getattr(agent, "role", None) or default


def _agent_goal(agent: Any) -> str:
    return getattr(agent, "goal", None) or ""


def _task_description(task: Any) -> str:
    return getattr(task, "description", None) or "unknown"


def _task_expected_output(task: Any) -> str:
    return getattr(task, "expected_output", None) or ""


def _task_agent_name(task: Any, default: str) -> str:
    agent = getattr(task, "agent", None)
    return _agent_role(agent, default) if agent is not None else default


def _extract_token_usage(output: Any) -> TokenUsage | None:
    usage = getattr(output, "token_usage", None) or getattr(output, "usage", None)
    if usage is None:
        return None
    return TokenUsage(
        input_tokens=getattr(usage, "prompt_tokens", None),
        output_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )


def _elapsed_ms(start: float | None) -> float | None:
    if start is None:
        return None
    return (time.time() - start) * 1000
