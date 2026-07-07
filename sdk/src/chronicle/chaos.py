"""Chaos testing: synthetic failure injection for testing agent resilience.

`ChaosConfig` describes a set of chaos rules (tool failures, injected
latency, malformed tool responses); `ChaosMixin.wrap_tool_call()` applies
them around one tool invocation. Chaos is strictly opt-in — `chronicle.instrument()`
only activates it when a caller explicitly passes `chaos=ChaosConfig(...)`;
there is no default chaos configuration and no global on/off switch anywhere
in the SDK.

Chaos only ever applies to tool calls, never LLM calls: injecting LLM
failures would make a run unreplayable (Chronicle's replay engine depends on
being able to deterministically re-invoke the same graph) and would defeat
the purpose of using Chronicle to observe what actually happened.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_DEFAULT_EXCEPTION: type[BaseException] = RuntimeError


@dataclass
class ChaosConfig:
    """Describes which synthetic failures to inject into tool calls.

    Every rate is a probability in `[0.0, 1.0]`, checked independently via a
    fresh `random.random()` call each time it's needed — no seeded or shared
    RNG state, so concurrent chaos-enabled runs never interfere with each
    other.
    """

    tool_failure_rate: float = 0.0
    tool_failure_tools: list[str] = field(default_factory=list)
    tool_failure_exception: type[BaseException] = _DEFAULT_EXCEPTION
    tool_failure_message: str = "Chronicle chaos: simulated tool failure"
    latency_injection_ms: int = 0
    latency_injection_tools: list[str] = field(default_factory=list)
    malformed_response_rate: float = 0.0
    malformed_response_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe summary for `runs.metadata["chaos_config"]`.

        `tool_failure_exception` is stored by name, not the class itself —
        classes aren't JSON-serializable, and neither the server nor the app
        need the real type, only what it's called.
        """
        return {
            "tool_failure_rate": self.tool_failure_rate,
            "tool_failure_tools": list(self.tool_failure_tools),
            "tool_failure_exception": self.tool_failure_exception.__name__,
            "tool_failure_message": self.tool_failure_message,
            "latency_injection_ms": self.latency_injection_ms,
            "latency_injection_tools": list(self.latency_injection_tools),
            "malformed_response_rate": self.malformed_response_rate,
            "malformed_response_value": _json_safe(self.malformed_response_value),
        }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def chaos(**overrides: Any) -> ChaosConfig:
    """Convenience factory: a `ChaosConfig` with sensible defaults (20% tool failure
    rate, applied to every tool), overridable via keyword arguments.

    ```python
    chronicle.instrument(graph, chaos=chronicle.chaos())
    chronicle.instrument(graph, chaos=chronicle.chaos(tool_failure_rate=0.5))
    ```
    """
    defaults: dict[str, Any] = {"tool_failure_rate": 0.2}
    defaults.update(overrides)
    return ChaosConfig(**defaults)


class ChaosMixin:
    """Wraps one tool invocation with the rules from a `ChaosConfig`.

    Not tied to any specific adapter's callback shape — `wrap_tool_call()`
    takes the tool's real call as a zero-argument callable, so any adapter
    with a direct reference to the tool function can use this, not just
    `LangGraphAdapter`. (Callback-only adapters, e.g. hooks that only observe
    a tool call's start/end without holding the callable itself, can still
    apply the failure/latency rules; response malformation can only rewrite
    what's recorded in the Chronicle event, not what the agent already
    received back from the real call — see `KNOWN_ISSUES.md`.)
    """

    def __init__(self, config: ChaosConfig) -> None:
        self.config = config

    def _targets(self, tool_name: str, targets: list[str]) -> bool:
        return not targets or tool_name in targets

    def should_fail(self, tool_name: str) -> bool:
        config = self.config
        return self._targets(tool_name, config.tool_failure_tools) and random.random() < config.tool_failure_rate

    def raise_configured_failure(self) -> None:
        config = self.config
        raise config.tool_failure_exception(config.tool_failure_message)

    def latency_ms(self, tool_name: str) -> int:
        config = self.config
        if config.latency_injection_ms > 0 and self._targets(tool_name, config.latency_injection_tools):
            return config.latency_injection_ms
        return 0

    def should_malform(self) -> bool:
        return random.random() < self.config.malformed_response_rate

    def wrap_tool_call(self, tool_name: str, call: Callable[[], T]) -> T:
        """Applies failure/latency/malformation rules around `call()`.

        Raises `config.tool_failure_exception` before ever invoking `call`
        if the failure roll triggers; sleeps for `config.latency_injection_ms`
        first if targeted; otherwise calls `call()` and, if the malformed-
        response roll triggers, returns `config.malformed_response_value`
        instead of the real result.
        """
        if self.should_fail(tool_name):
            self.raise_configured_failure()

        delay_ms = self.latency_ms(tool_name)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)

        result = call()

        if self.should_malform():
            return self.config.malformed_response_value  # type: ignore[return-value]

        return result
