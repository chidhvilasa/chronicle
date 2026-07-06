"""Async SQLite persistence layer for the Chronicle server, backed by aiosqlite."""

from __future__ import annotations

import json
import time
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

CREATE TABLE IF NOT EXISTS tests (
    test_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    source_snapshot_id TEXT,
    assertions TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    last_run_at REAL,
    last_result TEXT
);

CREATE TABLE IF NOT EXISTS test_results (
    result_id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL,
    replay_run_id TEXT,
    status TEXT NOT NULL,
    passed INTEGER NOT NULL,
    assertion_results TEXT NOT NULL DEFAULT '[]',
    duration_ms REAL,
    token_usage TEXT,
    error_reason TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_run_id ON runs (run_id);
CREATE INDEX IF NOT EXISTS idx_events_run_id ON events (run_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_snapshots_run_id ON snapshots (run_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_step_index ON snapshots (step_index);
CREATE INDEX IF NOT EXISTS idx_tests_created_at ON tests (created_at);
CREATE INDEX IF NOT EXISTS idx_test_results_test_id ON test_results (test_id);
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

    async def set_run_metadata(self, run_id: str, metadata: dict[str, Any]) -> None:
        """Creates a run row (if needed) and sets its metadata.

        Used to stamp a freshly-created replay run with
        `{is_replay, source_run_id, source_snapshot_id, step_index}` before
        any events have arrived for it. Safe to call on an existing run too:
        only `metadata` is overwritten, so this can't clobber aggregates
        computed from `events`.
        """
        now = time.time()
        await self._conn.execute(
            "INSERT INTO runs (run_id, started_at, finished_at, metadata) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET metadata = excluded.metadata",
            (run_id, now, now, json.dumps(metadata)),
        )
        await self._conn.commit()

    async def set_run_status(self, run_id: str, status: str) -> None:
        """Directly sets a run's status, bypassing the events-derived aggregate logic.

        Used to mark a replay run `"complete"`/`"failed"` once it finishes —
        call this *after* the tracer for that run has flushed its events, so
        it isn't immediately overwritten by `_refresh_run_aggregates`.
        """
        await self._conn.execute("UPDATE runs SET status = ? WHERE run_id = ?", (status, run_id))
        await self._conn.commit()

    async def list_snapshots_summary(self, run_id: str) -> list[dict[str, Any]]:
        """Lists snapshots for a run without the (potentially large) state fields."""
        cursor = await self._conn.execute(
            "SELECT snapshot_id, step_index, timestamp, agent_name, event_id FROM snapshots "
            "WHERE run_id = ? ORDER BY step_index ASC",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_snapshot_summary(row) for row in rows]

    async def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """Fetches one snapshot's full detail, including `graph_state`/`messages`/`tool_results`."""
        cursor = await self._conn.execute(
            "SELECT snapshot_id, run_id, event_id, step_index, timestamp, agent_name, "
            "graph_state, messages, tool_results, metadata FROM snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        row = await cursor.fetchone()
        return _row_to_snapshot(row) if row else None

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

    async def create_test(
        self,
        test_id: str,
        name: str,
        source_run_id: str,
        source_snapshot_id: str | None,
        assertions: list[dict[str, Any]],
        created_at: float,
    ) -> None:
        await self._conn.execute(
            "INSERT INTO tests (test_id, name, source_run_id, source_snapshot_id, assertions, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (test_id, name, source_run_id, source_snapshot_id, json.dumps(assertions), created_at),
        )
        await self._conn.commit()

    async def list_tests(self) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            "SELECT test_id, name, source_run_id, source_snapshot_id, assertions, "
            "created_at, last_run_at, last_result FROM tests ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [_row_to_test(row) for row in rows]

    async def get_test(self, test_id: str) -> dict[str, Any] | None:
        cursor = await self._conn.execute(
            "SELECT test_id, name, source_run_id, source_snapshot_id, assertions, "
            "created_at, last_run_at, last_result FROM tests WHERE test_id = ?",
            (test_id,),
        )
        row = await cursor.fetchone()
        return _row_to_test(row) if row else None

    async def delete_test(self, test_id: str) -> bool:
        test = await self.get_test(test_id)
        if test is None:
            return False
        await self._conn.execute("DELETE FROM test_results WHERE test_id = ?", (test_id,))
        await self._conn.execute("DELETE FROM tests WHERE test_id = ?", (test_id,))
        await self._conn.commit()
        return True

    async def update_test_last_result(self, test_id: str, last_result: str, last_run_at: float) -> None:
        await self._conn.execute(
            "UPDATE tests SET last_result = ?, last_run_at = ? WHERE test_id = ?",
            (last_result, last_run_at, test_id),
        )
        await self._conn.commit()

    async def insert_test_result(
        self,
        result_id: str,
        test_id: str,
        replay_run_id: str | None,
        status: str,
        passed: bool,
        assertion_results: list[dict[str, Any]],
        duration_ms: float | None,
        token_usage: dict[str, Any] | None,
        error_reason: str | None,
        created_at: float,
    ) -> None:
        await self._conn.execute(
            "INSERT INTO test_results (result_id, test_id, replay_run_id, status, passed, "
            "assertion_results, duration_ms, token_usage, error_reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result_id,
                test_id,
                replay_run_id,
                status,
                1 if passed else 0,
                json.dumps(assertion_results),
                duration_ms,
                json.dumps(token_usage) if token_usage is not None else None,
                error_reason,
                created_at,
            ),
        )
        await self._conn.commit()

    async def list_test_results(self, test_id: str, limit: int = 20) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            "SELECT result_id, test_id, replay_run_id, status, passed, assertion_results, "
            "duration_ms, token_usage, error_reason, created_at FROM test_results "
            "WHERE test_id = ? ORDER BY created_at DESC LIMIT ?",
            (test_id, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_test_result(row) for row in rows]


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


def _row_to_snapshot_summary(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "snapshot_id": row["snapshot_id"],
        "step_index": row["step_index"],
        "timestamp": row["timestamp"],
        "agent_name": row["agent_name"],
        "event_id": row["event_id"],
    }


def _row_to_snapshot(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "snapshot_id": row["snapshot_id"],
        "run_id": row["run_id"],
        "event_id": row["event_id"],
        "step_index": row["step_index"],
        "timestamp": row["timestamp"],
        "agent_name": row["agent_name"],
        "graph_state": json.loads(row["graph_state"]),
        "messages": json.loads(row["messages"]),
        "tool_results": json.loads(row["tool_results"]),
        "metadata": json.loads(row["metadata"]),
    }


def _row_to_test(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "test_id": row["test_id"],
        "name": row["name"],
        "source_run_id": row["source_run_id"],
        "source_snapshot_id": row["source_snapshot_id"],
        "assertions": json.loads(row["assertions"]),
        "created_at": row["created_at"],
        "last_run_at": row["last_run_at"],
        "last_result": row["last_result"],
    }


def _row_to_test_result(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "result_id": row["result_id"],
        "test_id": row["test_id"],
        "replay_run_id": row["replay_run_id"],
        "status": row["status"],
        "passed": bool(row["passed"]),
        "assertion_results": json.loads(row["assertion_results"]),
        "duration_ms": row["duration_ms"],
        "token_usage": json.loads(row["token_usage"]) if row["token_usage"] else None,
        "error_reason": row["error_reason"],
        "created_at": row["created_at"],
    }
