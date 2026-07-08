"""Tamper-evident hash chain for stored events.

Every event gets an `event_hash` - a SHA-256 digest of its own immutable
fields (`event_id`, `run_id`, `timestamp`, `event_type`, `agent_name`, `data`
with sorted keys) - computed and stored the moment it's written. Events are
then chained in their canonical order (`timestamp ASC, event_id ASC`, the
same order used everywhere else events are listed): each event's
`chain_hash` is SHA-256(previous event's `chain_hash` + this event's
`event_hash`), seeded from `GENESIS_CHAIN_HASH` for the first event in a run.

Verifying a run recomputes both values from the stored row data and compares
them against what's actually in the `event_hash`/`chain_hash` columns:
- A mismatched `event_hash` means that specific row's content changed after
  it was written (a direct DB edit, disk corruption, a bug).
- A mismatched `chain_hash` with a *matching* `event_hash` means the row
  itself wasn't touched, but something earlier in the chain was - reordered,
  deleted, or inserted - since `chain_hash` also encodes every prior event.

This catches accidental or local corruption and makes tampering detectable;
it is not a defense against a determined attacker with direct write access to
the database file, who could recompute and rewrite the whole chain. It's an
integrity checksum for a local trace store, not a cryptographic audit log.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

GENESIS_CHAIN_HASH = ""


def compute_event_hash(event: dict[str, Any]) -> str:
    """SHA-256 hex digest of an event's immutable identity + content fields."""
    canonical = json.dumps(
        {
            "event_id": event["event_id"],
            "run_id": event["run_id"],
            "timestamp": event["timestamp"],
            "event_type": event["event_type"],
            "agent_name": event.get("agent_name"),
            "data": event.get("data") or {},
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_chain_hash(event_hash: str, previous_chain_hash: str) -> str:
    """SHA-256 hex digest binding `event_hash` to everything before it in the chain."""
    return hashlib.sha256((previous_chain_hash + event_hash).encode("utf-8")).hexdigest()


def build_chain(events: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Computes `(event_hash, chain_hash)` for each event, in the order given.

    Callers must already have `events` sorted in canonical chain order
    (`timestamp ASC, event_id ASC`) - this function trusts the given order
    and does not re-sort.
    """
    chain: list[tuple[str, str]] = []
    previous_chain_hash = GENESIS_CHAIN_HASH
    for event in events:
        event_hash = compute_event_hash(event)
        chain_hash = compute_chain_hash(event_hash, previous_chain_hash)
        chain.append((event_hash, chain_hash))
        previous_chain_hash = chain_hash
    return chain


@dataclass
class IntegrityViolation:
    event_id: str
    reason: str


@dataclass
class VerifyResult:
    run_id: str
    event_count: int
    violations: list[IntegrityViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def verify_run_events(run_id: str, events: list[dict[str, Any]]) -> VerifyResult:
    """Recomputes the hash chain for `events` and compares it against their stored
    `event_hash`/`chain_hash` columns.

    `events` must already be sorted in canonical chain order and each dict must
    include `event_hash` and `chain_hash` as stored in the database.
    """
    violations: list[IntegrityViolation] = []
    previous_chain_hash = GENESIS_CHAIN_HASH
    for event in events:
        expected_event_hash = compute_event_hash(event)
        stored_event_hash = event.get("event_hash") or ""
        if stored_event_hash != expected_event_hash:
            violations.append(
                IntegrityViolation(
                    event_id=event["event_id"],
                    reason="event_hash mismatch: this event's content changed after it was recorded",
                )
            )

        expected_chain_hash = compute_chain_hash(expected_event_hash, previous_chain_hash)
        stored_chain_hash = event.get("chain_hash") or ""
        if stored_chain_hash != expected_chain_hash and stored_event_hash == expected_event_hash:
            violations.append(
                IntegrityViolation(
                    event_id=event["event_id"],
                    reason="chain_hash mismatch: an earlier event was reordered, deleted, or inserted",
                )
            )
        previous_chain_hash = expected_chain_hash

    return VerifyResult(run_id=run_id, event_count=len(events), violations=violations)
