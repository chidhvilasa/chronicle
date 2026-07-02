"""Local JSON fallback storage used when the Chronicle server is unreachable."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_LOCAL_DIR = Path("chronicle_runs")


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
    return _append_json_list(Path(local_dir) / f"{run_id}.json", events)


def write_local_snapshots(
    run_id: str,
    snapshots: list[dict[str, Any]],
    local_dir: Path | str = DEFAULT_LOCAL_DIR,
) -> Path:
    """Append snapshots to `{local_dir}/{run_id}_snapshots.json`, creating the file if needed."""
    return _append_json_list(Path(local_dir) / f"{run_id}_snapshots.json", snapshots)
