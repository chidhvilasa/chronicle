"""Shared memory-diffing helper used by every adapter's `memory_update` capture.

Any adapter that observes a `state`/`memory` dict at the start and end of an
agent's turn calls `record_memory_update()` to diff them and (if they differ)
record a `memory_update` event. `data["memory_before"]`/`data["memory_after"]`
carry the full before/after dicts; `data["keys_added"]`/`data["keys_removed"]`/
`data["keys_changed"]` carry the top-level key diff, computed here as a
convenience for anyone reading the raw event JSON directly - the server's
`GET /runs/{id}/memory` independently recomputes the same diff from
`memory_before`/`memory_after` rather than trusting these fields, so this
computation doesn't need to be perfectly in sync with the server's.
"""

from __future__ import annotations

from typing import Any

from chronicle.tracer import ChronicleTracer


def diff_memory_keys(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[str]]:
    """Top-level key diff between two dicts. A nested-value change surfaces as a changed
    top-level key (Python's `!=` on dicts/lists is already a deep structural comparison).
    """
    keys_added = [key for key in after if key not in before]
    keys_removed = [key for key in before if key not in after]
    keys_changed = [key for key in before if key in after and before[key] != after[key]]
    return {"keys_added": keys_added, "keys_removed": keys_removed, "keys_changed": keys_changed}


def json_safe_dict(value: Any) -> dict[str, Any]:
    """Recursively converts `value` into a JSON-serializable dict, or `{}` if it isn't dict-like.

    Building a brand-new dict/list at every level also has the side effect of decoupling
    the result from the original object, so capturing a "before" snapshot this way survives
    later in-place mutation of the original by the agent.
    """
    if not isinstance(value, dict):
        return {}
    return {str(key): _json_safe(val) for key, val in value.items()}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def record_memory_update(tracer: ChronicleTracer, agent_name: str, before: Any, after: Any) -> None:
    """Diffs `before`/`after` (coerced to JSON-safe dicts) and records a `memory_update`
    event if they differ. A no-op if neither side is dict-like, or if nothing changed.
    """
    safe_before = json_safe_dict(before)
    safe_after = json_safe_dict(after)
    if not safe_before and not safe_after:
        return
    if safe_before == safe_after:
        return
    diff = diff_memory_keys(safe_before, safe_after)
    tracer.record_event(
        "memory_update",
        data={"memory_before": safe_before, "memory_after": safe_after, **diff},
        agent_name=agent_name,
    )
