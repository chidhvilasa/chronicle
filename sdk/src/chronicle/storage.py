"""Local SQLite fallback storage used when the Chronicle server is unreachable."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from chronicle.events import ChronicleEvent

DEFAULT_DB_PATH = Path.home() / ".chronicle" / "chronicle.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    parent_id TEXT,
    event_type TEXT NOT NULL,
    timestamp REAL NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_run_id ON events (run_id);
"""


class LocalStorage:
    """Writes events directly to a local SQLite file when the server is offline."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def write_event(self, event: ChronicleEvent) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO events (id, run_id, parent_id, event_type, timestamp, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event["id"],
                event["run_id"],
                event["parent_id"],
                event["event_type"],
                event["timestamp"],
                json.dumps(event["payload"]),
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
