"""Local JSON fallback storage used when the Chronicle server is unreachable."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_LOCAL_DIR = Path("chronicle_runs")


def write_local_events(
    run_id: str,
    events: list[dict[str, Any]],
    local_dir: Path | str = DEFAULT_LOCAL_DIR,
) -> Path:
    """Append events to `{local_dir}/{run_id}.json`, creating the file if needed."""
    directory = Path(local_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}.json"
    existing: list[dict[str, Any]] = json.loads(path.read_text()) if path.exists() else []
    existing.extend(events)
    path.write_text(json.dumps(existing, indent=2))
    return path
