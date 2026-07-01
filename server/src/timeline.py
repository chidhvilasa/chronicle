"""Shapes raw event rows into a per-agent lane timeline for the frontend.

Only `llm_call`, `tool_call`, `retry`, and `error` events become visible
segments; `agent_message` and `memory_update` events don't represent
durations of work and are currently omitted from the timeline (see
KNOWN_ISSUES.md). Gaps between consecutive segments in the same lane become
synthetic `waiting` segments.
"""

from __future__ import annotations

from typing import Any, TypedDict

_SEGMENT_EVENT_TYPES = {"llm_call", "tool_call", "retry", "error"}
# Timestamps are floats, so back-to-back events can produce a gap of a few
# nanoseconds of floating-point noise instead of exactly zero; ignore gaps
# below this threshold rather than rendering a near-invisible waiting segment.
_MIN_GAP_MS = 1e-6


class TimelineSegment(TypedDict):
    type: str
    start_time_ms: float
    duration_ms: float
    label: str
    token_usage: dict[str, int | None] | None


class TimelineLane(TypedDict):
    agent_name: str
    segments: list[TimelineSegment]


def build_timeline(events: list[dict[str, Any]]) -> list[TimelineLane]:
    """Group a run's events into per-agent lanes of llm_call/tool_call/error/waiting segments."""
    if not events:
        return []

    run_start = min(event["timestamp"] for event in events)
    by_agent: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        agent_name = event.get("agent_name") or "unknown"
        by_agent.setdefault(agent_name, []).append(event)

    lanes: list[TimelineLane] = []
    for agent_name in sorted(by_agent):
        agent_events = sorted(by_agent[agent_name], key=lambda e: e["timestamp"])
        lanes.append({"agent_name": agent_name, "segments": _build_segments(agent_events, run_start)})
    return lanes


def _build_segments(events: list[dict[str, Any]], run_start: float) -> list[TimelineSegment]:
    work_segments = [
        _event_to_segment(event, run_start)
        for event in events
        if event["event_type"] in _SEGMENT_EVENT_TYPES
    ]
    return _with_waiting_segments(work_segments)


def _event_to_segment(event: dict[str, Any], run_start: float) -> TimelineSegment:
    event_type = event["event_type"]
    data = event.get("data") or {}

    if event_type == "llm_call":
        label = data.get("model", "llm_call")
    elif event_type == "tool_call":
        label = data.get("tool_name", "tool_call")
    elif event_type == "retry":
        label = data.get("reason", "retry")
    else:
        label = event.get("error") or "error"

    token_usage = None
    if event_type == "llm_call" and (
        event.get("input_tokens") is not None or event.get("output_tokens") is not None
    ):
        token_usage = {
            "input_tokens": event.get("input_tokens"),
            "output_tokens": event.get("output_tokens"),
        }

    return {
        "type": event_type,
        "start_time_ms": (event["timestamp"] - run_start) * 1000,
        "duration_ms": event.get("duration_ms") or 0.0,
        "label": label,
        "token_usage": token_usage,
    }


def _with_waiting_segments(segments: list[TimelineSegment]) -> list[TimelineSegment]:
    """Insert a `waiting` segment for every meaningful gap between consecutive segments."""
    if not segments:
        return []

    ordered = sorted(segments, key=lambda s: s["start_time_ms"])
    result: list[TimelineSegment] = [ordered[0]]
    for prev, current in zip(ordered, ordered[1:]):
        prev_end = prev["start_time_ms"] + prev["duration_ms"]
        gap = current["start_time_ms"] - prev_end
        if gap > _MIN_GAP_MS:
            result.append(
                {
                    "type": "waiting",
                    "start_time_ms": prev_end,
                    "duration_ms": gap,
                    "label": "waiting",
                    "token_usage": None,
                }
            )
        result.append(current)
    return result
