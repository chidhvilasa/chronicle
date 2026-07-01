"""Event schemas shared by every Chronicle SDK integration."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Literal, TypedDict


class EventType(str, Enum):
    TOOL_CALL = "tool_call"
    LLM_CALL = "llm_call"
    AGENT_MESSAGE = "agent_message"
    MEMORY_UPDATE = "memory_update"
    ERROR = "error"
    RETRY = "retry"


EventTypeLiteral = Literal[
    "tool_call", "llm_call", "agent_message", "memory_update", "error", "retry"
]


class ToolCallPayload(TypedDict, total=False):
    tool_name: str
    arguments: dict[str, Any]
    result: Any
    duration_ms: float
    success: bool


class LLMCallPayload(TypedDict, total=False):
    model: str
    provider: str
    prompt: str
    messages: list[dict[str, Any]]
    completion: str
    prompt_tokens: int
    completion_tokens: int
    duration_ms: float
    cost_usd: float


class AgentMessagePayload(TypedDict, total=False):
    role: str
    content: str
    agent_name: str


class MemoryUpdatePayload(TypedDict, total=False):
    key: str
    old_value: Any
    new_value: Any
    operation: str


class ErrorPayload(TypedDict, total=False):
    message: str
    error_type: str
    traceback: str


class RetryPayload(TypedDict, total=False):
    attempt: int
    max_attempts: int
    reason: str


class ChronicleEvent(TypedDict):
    """The envelope sent to `POST /events` on the Chronicle server."""

    id: str
    run_id: str
    parent_id: str | None
    event_type: EventTypeLiteral
    timestamp: float
    payload: dict[str, Any]


def new_event(
    run_id: str,
    event_type: EventTypeLiteral,
    payload: dict[str, Any],
    parent_id: str | None = None,
) -> ChronicleEvent:
    """Build a `ChronicleEvent` envelope with a fresh id and timestamp."""
    return ChronicleEvent(
        id=str(uuid.uuid4()),
        run_id=run_id,
        parent_id=parent_id,
        event_type=event_type,
        timestamp=time.time(),
        payload=payload,
    )
