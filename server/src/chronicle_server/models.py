"""Pydantic request/response models for the Chronicle server API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

EventTypeLiteral = Literal[
    "tool_call", "llm_call", "agent_message", "memory_update", "error", "retry"
]


class EventIn(BaseModel):
    id: str
    run_id: str
    parent_id: str | None = None
    event_type: EventTypeLiteral
    timestamp: float
    payload: dict[str, Any]


class EventOut(EventIn):
    pass


class RunOut(BaseModel):
    id: str
    started_at: float
    ended_at: float
    event_count: int


class HealthOut(BaseModel):
    status: Literal["ok"]
