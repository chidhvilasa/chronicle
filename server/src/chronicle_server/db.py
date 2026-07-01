"""SQLite persistence layer for the Chronicle server, backed by aiosqlite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

DEFAULT_DB_PATH = Path.home() / ".chronicle" / "chronicle.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 0
);

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


class Database:
    """Thin async wrapper around the SQLite tables Chronicle needs."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        await self._conn.close()

    async def insert_event(self, event: dict[str, Any]) -> None:
        """Insert an event and update the parent run's window/count."""
        await self._conn.execute(
            "INSERT OR REPLACE INTO events (id, run_id, parent_id, event_type, timestamp, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event["id"],
                event["run_id"],
                event.get("parent_id"),
                event["event_type"],
                event["timestamp"],
                json.dumps(event["payload"]),
            ),
        )
        await self._conn.execute(
            "INSERT INTO runs (id, started_at, ended_at, event_count) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(id) DO UPDATE SET "
            "started_at = MIN(started_at, excluded.started_at), "
            "ended_at = MAX(ended_at, excluded.ended_at), "
            "event_count = event_count + 1",
            (event["run_id"], event["timestamp"], event["timestamp"]),
        )
        await self._conn.commit()

    async def list_runs(self) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            "SELECT id, started_at, ended_at, event_count FROM runs ORDER BY started_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        cursor = await self._conn.execute(
            "SELECT id, started_at, ended_at, event_count FROM runs WHERE id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_events(self, run_id: str) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            "SELECT id, run_id, parent_id, event_type, timestamp, payload FROM events "
            "WHERE run_id = ? ORDER BY timestamp ASC",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_event(row) for row in rows]

    async def delete_run(self, run_id: str) -> bool:
        run = await self.get_run(run_id)
        if run is None:
            return False
        await self._conn.execute("DELETE FROM events WHERE run_id = ?", (run_id,))
        await self._conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        await self._conn.commit()
        return True


def _row_to_event(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "parent_id": row["parent_id"],
        "event_type": row["event_type"],
        "timestamp": row["timestamp"],
        "payload": json.loads(row["payload"]),
    }
