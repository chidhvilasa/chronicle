"""Async SQLite persistence layer for the Chronicle server, backed by aiosqlite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

DEFAULT_DB_PATH = Path.home() / ".chronicle" / "chronicle.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    finished_at REAL NOT NULL,
    framework TEXT,
    agent_count INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost_usd REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    agent_name TEXT,
    duration_ms REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    data TEXT NOT NULL DEFAULT '{}',
    error TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_id TEXT,
    step_index INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    agent_name TEXT,
    graph_state TEXT NOT NULL DEFAULT '{}',
    messages TEXT NOT NULL DEFAULT '[]',
    tool_results TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_runs_run_id ON runs (run_id);
CREATE INDEX IF NOT EXISTS idx_events_run_id ON events (run_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_snapshots_run_id ON snapshots (run_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_step_index ON snapshots (step_index);
"""


class Database:
    """Async wrapper around the SQLite tables Chronicle needs.

    Run-level aggregates (`started_at`, `finished_at`, `agent_count`,
    `total_tokens`, `status`) are recomputed from the `events` table itself
    every time a batch is inserted, rather than updated incrementally, so
    they can never drift out of sync with the underlying events.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path: Path | str = db_path if str(db_path) == ":memory:" else Path(db_path)

    async def connect(self) -> None:
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        await self._conn.close()

    async def insert_events(self, events: list[dict[str, Any]]) -> int:
        """Insert a batch of events and refresh aggregate stats for each affected run."""
        if not events:
            return 0
        await self._conn.executemany(
            "INSERT OR REPLACE INTO events "
            "(event_id, run_id, timestamp, event_type, agent_name, duration_ms, "
            "input_tokens, output_tokens, data, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    e["event_id"],
                    e["run_id"],
                    e["timestamp"],
                    e["event_type"],
                    e.get("agent_name"),
                    e.get("duration_ms"),
                    e.get("input_tokens"),
                    e.get("output_tokens"),
                    json.dumps(e.get("data") or {}),
                    e.get("error"),
                )
                for e in events
            ],
        )
        for run_id in {e["run_id"] for e in events}:
            await self._refresh_run_aggregates(run_id)
        await self._conn.commit()
        return len(events)

    async def _refresh_run_aggregates(self, run_id: str) -> None:
        cursor = await self._conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp), COUNT(DISTINCT agent_name), "
            "SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)), "
            "SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END) "
            "FROM events WHERE run_id = ?",
            (run_id,),
        )
        started_at, finished_at, agent_count, total_tokens, error_count = await cursor.fetchone()
        status = "error" if error_count else "running"
        await self._conn.execute(
            "INSERT INTO runs (run_id, started_at, finished_at, agent_count, total_tokens, status) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET "
            "started_at = excluded.started_at, "
            "finished_at = excluded.finished_at, "
            "agent_count = excluded.agent_count, "
            "total_tokens = excluded.total_tokens, "
            "status = excluded.status",
            (run_id, started_at, finished_at, agent_count, total_tokens or 0, status),
        )

    async def insert_snapshots(self, snapshots: list[dict[str, Any]]) -> int:
        """Insert a batch of state snapshots. Snapshots don't affect run aggregates."""
        if not snapshots:
            return 0
        await self._conn.executemany(
            "INSERT OR REPLACE INTO snapshots "
            "(snapshot_id, run_id, event_id, step_index, timestamp, agent_name, "
            "graph_state, messages, tool_results, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    s["snapshot_id"],
                    s["run_id"],
                    s.get("event_id"),
                    s["step_index"],
                    s["timestamp"],
                    s.get("agent_name"),
                    json.dumps(s.get("graph_state") or {}),
                    json.dumps(s.get("messages") or []),
                    json.dumps(s.get("tool_results") or []),
                    json.dumps(s.get("metadata") or {}),
                )
                for s in snapshots
            ],
        )
        await self._conn.commit()
        return len(snapshots)

    async def list_runs(self) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            "SELECT run_id, started_at, finished_at, framework, agent_count, "
            "total_tokens, total_cost_usd, status, metadata FROM runs "
            "ORDER BY started_at DESC"
        )
        rows = await cursor.fetchall()
        return [_row_to_run(row) for row in rows]

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        cursor = await self._conn.execute(
            "SELECT run_id, started_at, finished_at, framework, agent_count, "
            "total_tokens, total_cost_usd, status, metadata FROM runs WHERE run_id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        return _row_to_run(row) if row else None

    async def list_events(self, run_id: str) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            "SELECT event_id, run_id, timestamp, event_type, agent_name, duration_ms, "
            "input_tokens, output_tokens, data, error FROM events "
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
        await self._conn.execute("DELETE FROM snapshots WHERE run_id = ?", (run_id,))
        await self._conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        await self._conn.commit()
        return True


def _row_to_run(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "framework": row["framework"],
        "agent_count": row["agent_count"],
        "total_tokens": row["total_tokens"],
        "total_cost_usd": row["total_cost_usd"],
        "status": row["status"],
        "metadata": json.loads(row["metadata"]),
    }


def _row_to_event(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "run_id": row["run_id"],
        "timestamp": row["timestamp"],
        "event_type": row["event_type"],
        "agent_name": row["agent_name"],
        "duration_ms": row["duration_ms"],
        "input_tokens": row["input_tokens"],
        "output_tokens": row["output_tokens"],
        "data": json.loads(row["data"]),
        "error": row["error"],
    }
