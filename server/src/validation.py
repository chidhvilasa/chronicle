"""Shared request-validation helpers for endpoints that accept attacker-influenced
nested JSON or numeric fields — primarily `POST /events`.

Limits chosen per the v0.8.0 security audit (see `SECURITY_AUDIT.md`):
- payload size (event count per request, bytes per event) guards against a single
  request exhausting memory/disk,
- JSON nesting depth guards against pathological structures that could blow the
  recursion limit of naive recursive processing elsewhere,
- integer clamping guards downstream consumers (the app's TypeScript/JS number type,
  chart libraries, etc.) from unbounded values,
- the timestamp window rejects obviously-wrong client clocks/malicious backdating
  without being so strict it breaks legitimate replay/import use cases.
"""

from __future__ import annotations

import time
from typing import Any

MAX_EVENTS_PER_REQUEST = 1000
MAX_EVENT_PAYLOAD_BYTES = 1_000_000
MAX_JSON_DEPTH = 20
MAX_TIMESTAMP_FUTURE_SECONDS = 3600
MAX_TIMESTAMP_PAST_SECONDS = 30 * 86400
INT32_MAX = 2**31 - 1
INT32_MIN = -(2**31)


def json_depth(value: Any) -> int:
    """Iterative max container-nesting-depth of a JSON-like value.

    A bare scalar has depth 0 (no nesting at all); a dict/list of only scalars has
    depth 1; each additional level of dict/list nesting adds 1 — e.g.
    `{"a": {"b": 1}}` is depth 2, `[1, [2, [3]]]` is depth 3.

    Deliberately iterative (an explicit stack, not recursion) so that checking the
    depth of a pathologically-nested payload can never itself trigger a
    `RecursionError` — the exact failure mode this function exists to guard against
    elsewhere in the code.
    """
    stack: list[tuple[Any, int]] = [(value, 0)]
    max_seen = 0
    while stack:
        current, depth = stack.pop()
        if isinstance(current, dict):
            max_seen = max(max_seen, depth + 1)
            if depth > MAX_JSON_DEPTH + 5:
                # Already far deeper than anything we need to report precisely;
                # stop early rather than keep walking an arbitrarily deep structure.
                break
            for v in current.values():
                stack.append((v, depth + 1))
        elif isinstance(current, list):
            max_seen = max(max_seen, depth + 1)
            if depth > MAX_JSON_DEPTH + 5:
                break
            for v in current:
                stack.append((v, depth + 1))
    return max_seen


def clamp_int32(value: int | None) -> int | None:
    """Clamps an integer field to a signed 32-bit range before it's written to SQLite."""
    if value is None:
        return None
    return max(INT32_MIN, min(INT32_MAX, value))


def clamp_duration_ms(value: float | None) -> float | None:
    """Clamps a millisecond duration field to `[0, 2**31 - 1]` before it's stored."""
    if value is None:
        return None
    return max(0.0, min(float(INT32_MAX), value))


def validate_timestamp(timestamp: float, *, now: float | None = None) -> str | None:
    """Returns a human-readable rejection reason if `timestamp` is outside the
    acceptable ingestion window, or `None` if it's fine. Never raises.
    """
    reference = now if now is not None else time.time()
    if timestamp > reference + MAX_TIMESTAMP_FUTURE_SECONDS:
        return "timestamp is more than 1 hour in the future"
    if timestamp < reference - MAX_TIMESTAMP_PAST_SECONDS:
        return "timestamp is more than 30 days in the past"
    return None
