"""Async SQLite persistence layer for the Chronicle server, backed by aiosqlite."""

from __future__ import annotations

import datetime
import json
import statistics
import time
from pathlib import Path
from typing import Any

import aiosqlite

from src import integrity

DEFAULT_DB_PATH = Path.home() / ".chronicle" / "chronicle.db"


class CorruptedDataError(Exception):
    """Raised when a stored JSON column can't be parsed back into JSON.

    Normal writes always go through `json.dumps()`, so this should only ever be reached
    for data written or altered outside the normal API (direct SQLite edits, disk
    corruption, a bug in a future migration). Callers turn this into a clean 400
    response rather than letting a raw `json.JSONDecodeError` propagate into a 500.
    """


def _safe_json_loads(raw: str, context: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise CorruptedDataError(f"Corrupted {context}: not valid JSON") from exc


def _lenient_json_loads(raw: str) -> dict[str, Any]:
    """Like `_safe_json_loads`, but for aggregate queries scanning every row in a table
    (`get_tool_metrics`/`get_model_metrics`): one corrupted historical row shouldn't fail
    the whole aggregation, so this returns `{}` instead of raising.
    """
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}

# Cost estimation constants for `run_metrics.estimated_cost_usd` and the
# `/metrics/*` endpoints. These are flat per-token prices, not real
# per-model billing - see KNOWN_ISSUES.md. Events whose `data["model"]`
# contains "gpt-4" are priced at the GPT-4 rate; everything else (including
# events with no captured model name) falls back to the default rate.
GPT4_INPUT_COST_PER_TOKEN = 0.00001
GPT4_OUTPUT_COST_PER_TOKEN = 0.00003
DEFAULT_INPUT_COST_PER_TOKEN = 0.000003
DEFAULT_OUTPUT_COST_PER_TOKEN = 0.000015

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
    error TEXT,
    event_hash TEXT NOT NULL DEFAULT '',
    chain_hash TEXT NOT NULL DEFAULT ''
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

CREATE TABLE IF NOT EXISTS run_metrics (
    run_id TEXT PRIMARY KEY,
    total_duration_ms REAL NOT NULL DEFAULT 0,
    total_input_tokens INTEGER NOT NULL DEFAULT 0,
    total_output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL NOT NULL DEFAULT 0,
    llm_call_count INTEGER NOT NULL DEFAULT 0,
    tool_call_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    avg_llm_latency_ms REAL,
    p95_llm_latency_ms REAL,
    avg_tool_latency_ms REAL,
    p95_tool_latency_ms REAL,
    framework TEXT,
    agent_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_run_id ON runs (run_id);
CREATE INDEX IF NOT EXISTS idx_events_run_id ON events (run_id);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events (event_type);
-- Composite: covers "WHERE run_id = ? ORDER BY timestamp ASC" (list_events,
-- list_events_with_hashes, timeline/graph building, hash-chain recompute) in a
-- single index scan instead of a filter + separate sort.
CREATE INDEX IF NOT EXISTS idx_events_run_id_timestamp ON events (run_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_snapshots_run_id ON snapshots (run_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_step_index ON snapshots (step_index);
-- Composite: covers "WHERE run_id = ? ORDER BY step_index ASC" (list_snapshots_summary).
CREATE INDEX IF NOT EXISTS idx_snapshots_run_id_step_index ON snapshots (run_id, step_index);
CREATE INDEX IF NOT EXISTS idx_tests_created_at ON tests (created_at);
CREATE INDEX IF NOT EXISTS idx_test_results_test_id ON test_results (test_id);
-- Composite: covers "WHERE test_id = ? ORDER BY created_at DESC LIMIT ?" (list_test_results).
CREATE INDEX IF NOT EXISTS idx_test_results_test_id_created_at ON test_results (test_id, created_at);
CREATE INDEX IF NOT EXISTS idx_run_metrics_created_at ON run_metrics (created_at);
CREATE INDEX IF NOT EXISTS idx_run_metrics_framework ON run_metrics (framework);
"""


def _percentile(values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile (numpy's default method). `pct` is 0-1."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _event_cost_usd(event: dict[str, Any]) -> float:
    """Estimates one event's cost from its token counts and (if present) its model name.

    Always an estimate, never real per-model billing - see KNOWN_ISSUES.md.
    """
    input_tokens = event.get("input_tokens") or 0
    output_tokens = event.get("output_tokens") or 0
    model = str((event.get("data") or {}).get("model", "")).lower()
    if "gpt-4" in model:
        return input_tokens * GPT4_INPUT_COST_PER_TOKEN + output_tokens * GPT4_OUTPUT_COST_PER_TOKEN
    return input_tokens * DEFAULT_INPUT_COST_PER_TOKEN + output_tokens * DEFAULT_OUTPUT_COST_PER_TOKEN


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
        # Every write goes through json.dumps(), which always produces valid UTF-8, so
        # a TEXT column should never actually contain invalid UTF-8 bytes in practice.
        # This is a defensive backstop for the case where it somehow does anyway (a
        # direct SQLite edit, disk corruption): replace the invalid bytes with U+FFFD
        # rather than let sqlite3's default strict decoding raise and crash the request.
        await self._conn.execute("PRAGMA encoding = 'UTF-8'")
        self._conn.text_factory = lambda b: b.decode("utf-8", errors="replace") if isinstance(b, bytes) else b
        await self._conn.executescript(_SCHEMA)
        await self._migrate_schema()
        await self._conn.commit()

    async def _migrate_schema(self) -> None:
        """Adds columns to pre-existing tables that `CREATE TABLE IF NOT EXISTS` can't add.

        `event_hash`/`chain_hash` were introduced after some databases may already
        exist on disk without them; this brings any such database up to date in place.
        """
        cursor = await self._conn.execute("PRAGMA table_info(events)")
        existing_columns = {row[1] for row in await cursor.fetchall()}
        if "event_hash" not in existing_columns:
            await self._conn.execute("ALTER TABLE events ADD COLUMN event_hash TEXT NOT NULL DEFAULT ''")
        if "chain_hash" not in existing_columns:
            await self._conn.execute("ALTER TABLE events ADD COLUMN chain_hash TEXT NOT NULL DEFAULT ''")

    async def close(self) -> None:
        await self._conn.close()

    async def insert_events(self, events: list[dict[str, Any]]) -> int:
        """Insert a batch of events, refresh aggregate stats, and recompute the hash chain
        for each affected run.
        """
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
            await self._recompute_event_chain(run_id)
        await self._conn.commit()
        return len(events)

    async def _recompute_event_chain(self, run_id: str) -> None:
        """Recomputes `event_hash`/`chain_hash` for every event in `run_id`, in canonical
        order (`timestamp ASC, event_id ASC`).

        Recomputed from scratch (rather than incrementally extended) every time any event
        for this run is inserted, the same way `_refresh_run_aggregates` recomputes run
        aggregates from scratch: events can arrive out of order or be re-sent
        (`INSERT OR REPLACE`), so an incremental update could leave a stale chain for
        events after the inserted one. This mirrors the codebase's existing
        recompute-from-source-of-truth pattern rather than introducing a new one.
        """
        cursor = await self._conn.execute(
            "SELECT event_id, run_id, timestamp, event_type, agent_name, data FROM events "
            "WHERE run_id = ? ORDER BY timestamp ASC, event_id ASC",
            (run_id,),
        )
        rows = await cursor.fetchall()
        events = [
            {
                "event_id": row["event_id"],
                "run_id": row["run_id"],
                "timestamp": row["timestamp"],
                "event_type": row["event_type"],
                "agent_name": row["agent_name"],
                "data": _lenient_json_loads(row["data"]),
            }
            for row in rows
        ]
        chain = integrity.build_chain(events)
        await self._conn.executemany(
            "UPDATE events SET event_hash = ?, chain_hash = ? WHERE event_id = ?",
            [
                (event_hash, chain_hash, event["event_id"])
                for event, (event_hash, chain_hash) in zip(events, chain, strict=True)
            ],
        )

    async def list_events_with_hashes(self, run_id: str) -> list[dict[str, Any]]:
        """Lists a run's events in canonical chain order, including their stored
        `event_hash`/`chain_hash` - used by `chronicle verify`, not exposed over the
        regular events API.
        """
        cursor = await self._conn.execute(
            "SELECT event_id, run_id, timestamp, event_type, agent_name, data, "
            "event_hash, chain_hash FROM events WHERE run_id = ? "
            "ORDER BY timestamp ASC, event_id ASC",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "event_id": row["event_id"],
                "run_id": row["run_id"],
                "timestamp": row["timestamp"],
                "event_type": row["event_type"],
                "agent_name": row["agent_name"],
                "data": _lenient_json_loads(row["data"]),
                "event_hash": row["event_hash"],
                "chain_hash": row["chain_hash"],
            }
            for row in rows
        ]

    async def _refresh_run_aggregates(self, run_id: str) -> None:
        cursor = await self._conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp), COUNT(DISTINCT agent_name), "
            "SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)), "
            "SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END) "
            "FROM events WHERE run_id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        assert row is not None  # aggregate query with no GROUP BY always returns exactly one row
        started_at, finished_at, agent_count, total_tokens, error_count = row
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
        """Insert a batch of state snapshots. Snapshots don't affect run aggregates.

        `graph_state`/`messages`/`tool_results`/`metadata` always arrive here already
        parsed from a JSON request body by Pydantic, so they can never actually contain
        a Python-level reference cycle (JSON text itself is acyclic). The try/except
        below is defense-in-depth for internal callers that might one day construct a
        snapshot dict directly (e.g. the replay engine): `json.dumps` raises `ValueError`
        on a circular reference, which we turn into a clean, well-typed error instead of
        letting it surface as an unhandled 500.
        """
        if not snapshots:
            return 0
        try:
            rows = [
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
            ]
        except (ValueError, TypeError) as exc:
            raise CorruptedDataError(f"Snapshot state is not JSON-serializable: {exc}") from exc
        await self._conn.executemany(
            "INSERT OR REPLACE INTO snapshots "
            "(snapshot_id, run_id, event_id, step_index, timestamp, agent_name, "
            "graph_state, messages, tool_results, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
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

    async def compute_run_metrics(self, run_id: str) -> dict[str, Any] | None:
        """Aggregates one run's events into a `run_metrics` row and upserts it.

        Returns the computed row, or `None` if the run doesn't exist. Safe to
        call repeatedly (e.g. from the backfill endpoint) - each call fully
        recomputes the row from `events`/`runs`, so it can never drift.
        """
        run = await self.get_run(run_id)
        if run is None:
            return None
        events = await self.list_events(run_id)

        llm_events = [e for e in events if e["event_type"] == "llm_call"]
        tool_events = [e for e in events if e["event_type"] == "tool_call"]
        llm_durations = [e["duration_ms"] for e in llm_events if e["duration_ms"] is not None]
        tool_durations = [e["duration_ms"] for e in tool_events if e["duration_ms"] is not None]

        total_input_tokens = sum(e["input_tokens"] or 0 for e in events)
        total_output_tokens = sum(e["output_tokens"] or 0 for e in events)

        row = {
            "run_id": run_id,
            "total_duration_ms": max(0.0, (run["finished_at"] - run["started_at"]) * 1000),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "estimated_cost_usd": sum(_event_cost_usd(e) for e in events),
            "llm_call_count": len(llm_events),
            "tool_call_count": len(tool_events),
            "error_count": sum(1 for e in events if e["event_type"] == "error"),
            "retry_count": sum(1 for e in events if e["event_type"] == "retry"),
            "avg_llm_latency_ms": statistics.fmean(llm_durations) if llm_durations else None,
            "p95_llm_latency_ms": _percentile(llm_durations, 0.95),
            "avg_tool_latency_ms": statistics.fmean(tool_durations) if tool_durations else None,
            "p95_tool_latency_ms": _percentile(tool_durations, 0.95),
            "framework": run["framework"],
            "agent_count": run["agent_count"],
            "created_at": time.time(),
        }

        await self._conn.execute(
            "INSERT INTO run_metrics (run_id, total_duration_ms, total_input_tokens, "
            "total_output_tokens, total_tokens, estimated_cost_usd, llm_call_count, "
            "tool_call_count, error_count, retry_count, avg_llm_latency_ms, "
            "p95_llm_latency_ms, avg_tool_latency_ms, p95_tool_latency_ms, framework, "
            "agent_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET "
            "total_duration_ms = excluded.total_duration_ms, "
            "total_input_tokens = excluded.total_input_tokens, "
            "total_output_tokens = excluded.total_output_tokens, "
            "total_tokens = excluded.total_tokens, "
            "estimated_cost_usd = excluded.estimated_cost_usd, "
            "llm_call_count = excluded.llm_call_count, "
            "tool_call_count = excluded.tool_call_count, "
            "error_count = excluded.error_count, "
            "retry_count = excluded.retry_count, "
            "avg_llm_latency_ms = excluded.avg_llm_latency_ms, "
            "p95_llm_latency_ms = excluded.p95_llm_latency_ms, "
            "avg_tool_latency_ms = excluded.avg_tool_latency_ms, "
            "p95_tool_latency_ms = excluded.p95_tool_latency_ms, "
            "framework = excluded.framework, "
            "agent_count = excluded.agent_count, "
            "created_at = excluded.created_at",
            (
                row["run_id"],
                row["total_duration_ms"],
                row["total_input_tokens"],
                row["total_output_tokens"],
                row["total_tokens"],
                row["estimated_cost_usd"],
                row["llm_call_count"],
                row["tool_call_count"],
                row["error_count"],
                row["retry_count"],
                row["avg_llm_latency_ms"],
                row["p95_llm_latency_ms"],
                row["avg_tool_latency_ms"],
                row["p95_tool_latency_ms"],
                row["framework"],
                row["agent_count"],
                row["created_at"],
            ),
        )
        await self._conn.commit()
        return row

    async def get_metrics_overview(self) -> dict[str, Any]:
        """Aggregate stats across every run that has a `run_metrics` row."""
        cursor = await self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(total_tokens), 0), COALESCE(SUM(estimated_cost_usd), 0), "
            "COALESCE(AVG(total_duration_ms), 0), COALESCE(SUM(error_count), 0) FROM run_metrics"
        )
        overview_row = await cursor.fetchone()
        assert overview_row is not None  # aggregate query with no GROUP BY always returns exactly one row
        total_runs, total_tokens, total_cost_usd, avg_run_duration_ms, total_errors = overview_row

        cutoff = time.time() - 7 * 86400
        cursor = await self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(total_tokens), 0), COALESCE(SUM(estimated_cost_usd), 0) "
            "FROM run_metrics WHERE created_at >= ?",
            (cutoff,),
        )
        last_7_days_row = await cursor.fetchone()
        assert last_7_days_row is not None  # aggregate query with no GROUP BY always returns exactly one row
        runs_last_7_days, tokens_last_7_days, cost_last_7_days = last_7_days_row

        cursor = await self._conn.execute(
            "SELECT run_id FROM run_metrics ORDER BY estimated_cost_usd DESC LIMIT 1"
        )
        most_expensive = await cursor.fetchone()

        cursor = await self._conn.execute(
            "SELECT run_id FROM run_metrics ORDER BY total_duration_ms DESC LIMIT 1"
        )
        slowest = await cursor.fetchone()

        return {
            "total_runs": total_runs,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
            "avg_run_duration_ms": avg_run_duration_ms,
            "total_errors": total_errors,
            "runs_last_7_days": runs_last_7_days,
            "tokens_last_7_days": tokens_last_7_days,
            "cost_last_7_days": cost_last_7_days,
            "most_expensive_run_id": most_expensive["run_id"] if most_expensive else None,
            "slowest_run_id": slowest["run_id"] if slowest else None,
        }

    async def list_run_metrics(
        self,
        limit: int = 50,
        offset: int = 0,
        from_date: float | None = None,
        to_date: float | None = None,
        framework: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT rm.run_id, rm.total_duration_ms, rm.total_input_tokens, "
            "rm.total_output_tokens, rm.total_tokens, rm.estimated_cost_usd, "
            "rm.llm_call_count, rm.tool_call_count, rm.error_count, rm.retry_count, "
            "rm.avg_llm_latency_ms, rm.p95_llm_latency_ms, rm.avg_tool_latency_ms, "
            "rm.p95_tool_latency_ms, rm.framework, rm.agent_count, rm.created_at "
            "FROM run_metrics rm"
        )
        joins = ""
        conditions = []
        params: list[Any] = []
        if status is not None:
            joins = " JOIN runs r ON rm.run_id = r.run_id"
            conditions.append("r.status = ?")
            params.append(status)
        if from_date is not None:
            conditions.append("rm.created_at >= ?")
            params.append(from_date)
        if to_date is not None:
            conditions.append("rm.created_at <= ?")
            params.append(to_date)
        if framework is not None:
            conditions.append("rm.framework = ?")
            params.append(framework)

        query += joins
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY rm.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await self._conn.execute(query, params)
        rows = await cursor.fetchall()
        return [_row_to_run_metrics(row) for row in rows]

    async def get_metrics_trends(
        self, period: str, metric: str, stat: str = "avg"
    ) -> list[dict[str, Any]]:
        """Buckets `run_metrics` rows by day/week/month and aggregates one metric per bucket."""
        cursor = await self._conn.execute(
            "SELECT created_at, total_tokens, estimated_cost_usd, error_count, "
            "avg_llm_latency_ms, p95_llm_latency_ms FROM run_metrics ORDER BY created_at ASC"
        )
        rows = await cursor.fetchall()

        buckets: dict[str, list[float]] = {}
        order: list[str] = []
        for row in rows:
            key = _bucket_key(row["created_at"], period)
            if key not in buckets:
                buckets[key] = []
                order.append(key)

            if metric == "tokens":
                value = row["total_tokens"]
            elif metric == "cost":
                value = row["estimated_cost_usd"]
            elif metric == "errors":
                value = row["error_count"]
            elif metric == "latency":
                value = row["p95_llm_latency_ms"] if stat == "p95" else row["avg_llm_latency_ms"]
            else:
                value = None

            if value is not None:
                buckets[key].append(value)

        aggregator = sum if metric in ("tokens", "cost", "errors") else statistics.fmean
        return [
            {"bucket": key, "value": aggregator(buckets[key]) if buckets[key] else 0.0}
            for key in order
        ]

    async def get_tool_metrics(self) -> list[dict[str, Any]]:
        """Aggregate tool performance across every run, ordered by call count desc."""
        cursor = await self._conn.execute(
            "SELECT data, duration_ms, input_tokens, output_tokens, error FROM events "
            "WHERE event_type = 'tool_call'"
        )
        rows = await cursor.fetchall()

        by_tool: dict[str, dict[str, Any]] = {}
        for row in rows:
            data = _lenient_json_loads(row["data"])
            tool_name = data.get("tool_name") or "unknown"
            bucket = by_tool.setdefault(
                tool_name,
                {"durations": [], "errors": 0, "total_tokens": 0, "call_count": 0},
            )
            bucket["call_count"] += 1
            if row["duration_ms"] is not None:
                bucket["durations"].append(row["duration_ms"])
            if row["error"] is not None:
                bucket["errors"] += 1
            bucket["total_tokens"] += (row["input_tokens"] or 0) + (row["output_tokens"] or 0)

        results = [
            {
                "tool_name": tool_name,
                "call_count": bucket["call_count"],
                "avg_latency_ms": statistics.fmean(bucket["durations"]) if bucket["durations"] else None,
                "p95_latency_ms": _percentile(bucket["durations"], 0.95),
                "error_rate": bucket["errors"] / bucket["call_count"] if bucket["call_count"] else 0.0,
                "total_tokens": bucket["total_tokens"],
            }
            for tool_name, bucket in by_tool.items()
        ]
        return sorted(results, key=lambda r: r["call_count"], reverse=True)

    async def get_model_metrics(self) -> list[dict[str, Any]]:
        """Per-model breakdown across every run's `llm_call` events, ordered by call count desc."""
        cursor = await self._conn.execute(
            "SELECT data, duration_ms, input_tokens, output_tokens FROM events "
            "WHERE event_type = 'llm_call'"
        )
        rows = await cursor.fetchall()

        by_model: dict[str, dict[str, Any]] = {}
        for row in rows:
            data = _lenient_json_loads(row["data"])
            model_name = data.get("model") or "unknown"
            bucket = by_model.setdefault(
                model_name,
                {"durations": [], "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "call_count": 0},
            )
            bucket["call_count"] += 1
            if row["duration_ms"] is not None:
                bucket["durations"].append(row["duration_ms"])
            bucket["input_tokens"] += row["input_tokens"] or 0
            bucket["output_tokens"] += row["output_tokens"] or 0
            bucket["cost_usd"] += _event_cost_usd(
                {"input_tokens": row["input_tokens"], "output_tokens": row["output_tokens"], "data": data}
            )

        results = [
            {
                "model_name": model_name,
                "call_count": bucket["call_count"],
                "avg_latency_ms": statistics.fmean(bucket["durations"]) if bucket["durations"] else None,
                "total_input_tokens": bucket["input_tokens"],
                "total_output_tokens": bucket["output_tokens"],
                "total_cost_usd": bucket["cost_usd"],
            }
            for model_name, bucket in by_model.items()
        ]
        return sorted(results, key=lambda r: r["call_count"], reverse=True)

    async def backfill_run_metrics(self) -> int:
        """Computes `run_metrics` for every complete run that doesn't have a row yet."""
        cursor = await self._conn.execute(
            "SELECT run_id FROM runs WHERE status = 'complete' "
            "AND run_id NOT IN (SELECT run_id FROM run_metrics)"
        )
        rows = await cursor.fetchall()
        count = 0
        for row in rows:
            if await self.compute_run_metrics(row["run_id"]) is not None:
                count += 1
        return count

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


def _bucket_key(created_at: float, period: str) -> str:
    """Formats an epoch timestamp into an ISO bucket key for day/week/month grouping."""
    dt = datetime.datetime.fromtimestamp(created_at, tz=datetime.timezone.utc)
    if period == "week":
        week_start = dt - datetime.timedelta(days=dt.weekday())
        return week_start.strftime("%Y-%m-%d")
    if period == "month":
        return dt.strftime("%Y-%m-01")
    return dt.strftime("%Y-%m-%d")


def _row_to_run_metrics(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "total_duration_ms": row["total_duration_ms"],
        "total_input_tokens": row["total_input_tokens"],
        "total_output_tokens": row["total_output_tokens"],
        "total_tokens": row["total_tokens"],
        "estimated_cost_usd": row["estimated_cost_usd"],
        "llm_call_count": row["llm_call_count"],
        "tool_call_count": row["tool_call_count"],
        "error_count": row["error_count"],
        "retry_count": row["retry_count"],
        "avg_llm_latency_ms": row["avg_llm_latency_ms"],
        "p95_llm_latency_ms": row["p95_llm_latency_ms"],
        "avg_tool_latency_ms": row["avg_tool_latency_ms"],
        "p95_tool_latency_ms": row["p95_tool_latency_ms"],
        "framework": row["framework"],
        "agent_count": row["agent_count"],
        "created_at": row["created_at"],
    }


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
        "metadata": _safe_json_loads(row["metadata"], "run metadata"),
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
        "data": _safe_json_loads(row["data"], "event data"),
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
        "graph_state": _safe_json_loads(row["graph_state"], "snapshot graph_state"),
        "messages": _safe_json_loads(row["messages"], "snapshot messages"),
        "tool_results": _safe_json_loads(row["tool_results"], "snapshot tool_results"),
        "metadata": _safe_json_loads(row["metadata"], "snapshot metadata"),
    }


def _row_to_test(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "test_id": row["test_id"],
        "name": row["name"],
        "source_run_id": row["source_run_id"],
        "source_snapshot_id": row["source_snapshot_id"],
        "assertions": _safe_json_loads(row["assertions"], "test assertions"),
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
        "assertion_results": _safe_json_loads(row["assertion_results"], "test_result assertion_results"),
        "duration_ms": row["duration_ms"],
        "token_usage": _safe_json_loads(row["token_usage"], "test_result token_usage") if row["token_usage"] else None,
        "error_reason": row["error_reason"],
        "created_at": row["created_at"],
    }
