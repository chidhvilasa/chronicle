"""Pydantic request/response models for the Chronicle server API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

EventTypeLiteral = Literal[
    "tool_call", "llm_call", "agent_message", "memory_update", "error", "retry"
]


class TokenUsageIn(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class EventIn(BaseModel):
    """Shape of one event as sent by chronicle-sdk's `ChronicleTracer`."""

    event_id: str
    run_id: str
    timestamp: float
    event_type: EventTypeLiteral
    agent_name: str | None = None
    data: dict[str, Any] = {}
    duration_ms: float | None = None
    token_usage: TokenUsageIn | None = None
    error: str | None = None

    def to_row(self) -> dict[str, Any]:
        """Flatten into the column shape `Database.insert_events` expects."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "agent_name": self.agent_name,
            "duration_ms": self.duration_ms,
            "input_tokens": self.token_usage.input_tokens if self.token_usage else None,
            "output_tokens": self.token_usage.output_tokens if self.token_usage else None,
            "data": self.data,
            "error": self.error,
        }


class EventOut(BaseModel):
    """Shape of one event as stored and read back from SQLite."""

    event_id: str
    run_id: str
    timestamp: float
    event_type: str
    agent_name: str | None
    duration_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    data: dict[str, Any]
    error: str | None


class RunOut(BaseModel):
    """Summary stats for one run, derived from its events."""

    run_id: str
    started_at: float
    finished_at: float
    framework: str | None
    agent_count: int
    total_tokens: int
    total_cost_usd: float
    status: str
    metadata: dict[str, Any]


class TimelineSegmentOut(BaseModel):
    type: Literal["llm_call", "tool_call", "waiting", "error", "retry"]
    start_time_ms: float
    duration_ms: float
    label: str
    token_usage: dict[str, int | None] | None = None
    event_id: str | None = None


class TimelineLaneOut(BaseModel):
    agent_name: str
    segments: list[TimelineSegmentOut]


class TimelineOut(BaseModel):
    run_id: str
    lanes: list[TimelineLaneOut]


class HealthOut(BaseModel):
    status: Literal["ok"]
    version: str
