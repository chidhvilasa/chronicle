"""Core event model shared by the tracer and every adapter."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

EventType = Literal[
    "tool_call", "llm_call", "agent_message", "memory_update", "error", "retry"
]


@dataclass
class TokenUsage:
    """Token accounting for a single LLM call."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class ChronicleEvent:
    """A single captured event for a run."""

    run_id: str
    event_type: EventType
    agent_name: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    token_usage: TokenUsage | None = None
    error: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict for HTTP/local-file storage."""
        return {
            "run_id": self.run_id,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "agent_name": self.agent_name,
            "data": self.data,
            "duration_ms": self.duration_ms,
            "token_usage": self.token_usage.to_dict() if self.token_usage else None,
            "error": self.error,
        }
