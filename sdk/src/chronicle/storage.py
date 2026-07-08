"""Local JSON fallback storage used when the Chronicle server is unreachable."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

DEFAULT_LOCAL_DIR = Path("chronicle_runs")


class InvalidRunIdError(ValueError):
    """Raised when a `run_id` isn't a valid UUID and can't safely be used in a file path.

    `run_id` normally comes from `uuid.uuid4()` (see `ChronicleTracer.__init__`), but it's
    an overridable constructor parameter, so nothing upstream guarantees it's actually a
    UUID by the time it reaches here. Without this check, a `run_id` like
    `"../../etc/passwd"` would let `f"{run_id}.json"` escape `local_dir` entirely - this
    validates it's a plain UUID (hex digits and hyphens only) before it's ever
    interpolated into a filename.
    """


def _validate_run_id(run_id: str) -> None:
    try:
        uuid.UUID(run_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise InvalidRunIdError(
            f"Refusing to write a local fallback file for non-UUID run_id {run_id!r}"
        ) from exc


def _append_json_list(path: Path, items: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = json.loads(path.read_text()) if path.exists() else []
    existing.extend(items)
    path.write_text(json.dumps(existing, indent=2))
    return path


def write_local_events(
    run_id: str,
    events: list[dict[str, Any]],
    local_dir: Path | str = DEFAULT_LOCAL_DIR,
) -> Path:
    """Append events to `{local_dir}/{run_id}.json`, creating the file if needed."""
    _validate_run_id(run_id)
    return _append_json_list(Path(local_dir) / f"{run_id}.json", events)


def write_local_snapshots(
    run_id: str,
    snapshots: list[dict[str, Any]],
    local_dir: Path | str = DEFAULT_LOCAL_DIR,
) -> Path:
    """Append snapshots to `{local_dir}/{run_id}_snapshots.json`, creating the file if needed."""
    _validate_run_id(run_id)
    return _append_json_list(Path(local_dir) / f"{run_id}_snapshots.json", snapshots)
