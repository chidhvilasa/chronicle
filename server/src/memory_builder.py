"""Extracts memory diffs from a run's `memory_update` events, for the Memory Inspector.

`memory_update.data` is expected to carry `memory_before`/`memory_after` dicts
(see `chronicle.memory_diff.record_memory_update` in the SDK, which every
adapter's memory capture goes through). The before/after key diff is always
recomputed here from the two dicts directly rather than trusted from
`data["keys_added"]`/etc. (which the SDK also populates, redundantly, for
anyone reading the raw event JSON) - that keeps this endpoint correct even
against events recorded by a future SDK version with a different diff bug.

Python's `!=` on dicts is a deep structural comparison, so a change nested
several levels down under `memory_after["user"]["profile"]["age"]` still
correctly marks the top-level key `"user"` as changed - no separate recursive
diff algorithm is needed to satisfy "a nested change surfaces as a top-level
key change."
"""

from __future__ import annotations

from typing import Any, TypedDict


class MemorySnapshot(TypedDict):
    event_id: str
    step_index: int
    agent_name: str | None
    timestamp: float
    memory_before: dict[str, Any]
    memory_after: dict[str, Any]
    keys_added: list[str]
    keys_removed: list[str]
    keys_changed: list[str]


def _diff_keys(before: dict[str, Any], after: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    keys_added = [key for key in after if key not in before]
    keys_removed = [key for key in before if key not in after]
    keys_changed = [key for key in before if key in after and before[key] != after[key]]
    return keys_added, keys_removed, keys_changed


def build_memory_snapshots(events: list[dict[str, Any]]) -> list[MemorySnapshot]:
    memory_events = sorted(
        (e for e in events if e["event_type"] == "memory_update"), key=lambda e: e["timestamp"]
    )
    snapshots: list[MemorySnapshot] = []
    for index, event in enumerate(memory_events):
        data = event.get("data") or {}
        before = data.get("memory_before")
        after = data.get("memory_after")
        before = before if isinstance(before, dict) else {}
        after = after if isinstance(after, dict) else {}
        keys_added, keys_removed, keys_changed = _diff_keys(before, after)
        snapshots.append(
            {
                "event_id": event["event_id"],
                "step_index": index,
                "agent_name": event.get("agent_name"),
                "timestamp": event["timestamp"],
                "memory_before": before,
                "memory_after": after,
                "keys_added": keys_added,
                "keys_removed": keys_removed,
                "keys_changed": keys_changed,
            }
        )
    return snapshots
