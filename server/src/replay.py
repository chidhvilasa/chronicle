"""Replay engine: re-executes a registered LangGraph graph from a captured state snapshot.

This is the piece that makes Chronicle more than an observability tool: it
takes a `StateSnapshot` captured by `chronicle-sdk` mid-run, optionally
overrides part of that state, and re-invokes the same graph from that exact
point forward, recording the replay as a brand-new run.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.database import Database

logger = logging.getLogger("chronicle")


class ReplayEngine:
    """Re-invokes a registered LangGraph graph from a snapshot, recording events under a new run.

    Instruments the replayed invocation with `chronicle-sdk`'s
    `ChronicleTracer`/`LangGraphAdapter` — the exact same mechanism a live
    agent process uses — so the server briefly acts as the "agent process"
    for the duration of the replay. `chronicle-sdk` is an optional runtime
    dependency of the server: if it isn't installed, the replay run is
    marked `"failed"` with a warning logged, rather than crashing the server.
    """

    def __init__(self, db: Database, graph: Any) -> None:
        self.db = db
        self.graph = graph

    async def start_replay(
        self,
        snapshot: dict[str, Any],
        modifications: dict[str, Any] | None,
        new_run_id: str,
        source_run_id: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Applies `modifications` to the snapshot's graph state and re-invokes the graph.

        Meant to be scheduled as a FastAPI `BackgroundTasks` callback so it
        runs after the `POST /replay` response is already sent. The graph
        invocation itself runs in a worker thread (`asyncio.to_thread`) so a
        slow or blocking `graph.invoke()` never stalls the event loop.

        `extra_metadata` is merged on top of the standard replay metadata —
        used by the regression test engine to stamp
        `{triggered_by: "test", test_id}` onto test-triggered replay runs.
        """
        await self.db.set_run_metadata(
            new_run_id,
            {
                "is_replay": True,
                "source_run_id": source_run_id,
                "source_snapshot_id": snapshot["snapshot_id"],
                "step_index": snapshot["step_index"],
                **(extra_metadata or {}),
            },
        )

        try:
            from chronicle import ChronicleTracer
            from chronicle.adapters.langgraph import LangGraphAdapter
        except ImportError:
            logger.warning(
                "Chronicle: replay failed because chronicle-sdk is not installed "
                "in this environment", exc_info=True
            )
            await self.db.set_run_status(new_run_id, "failed")
            return

        state: dict[str, Any] = dict(snapshot["graph_state"])
        state.update(modifications or {})

        tracer = ChronicleTracer(run_id=new_run_id)
        adapter = LangGraphAdapter(tracer, agent_name=snapshot.get("agent_name") or "agent")

        try:
            await asyncio.to_thread(self.graph.invoke, state, config={"callbacks": [adapter]})
            final_status = "complete"
        except Exception:
            logger.warning("Chronicle: replay execution failed", exc_info=True)
            final_status = "failed"
        finally:
            # Flush any buffered events before declaring a final status, so
            # the status write below isn't clobbered by the aggregate
            # refresh that flushing an event batch triggers.
            await asyncio.to_thread(tracer.close)

        await self.db.set_run_status(new_run_id, final_status)
        if final_status == "complete":
            await self.db.compute_run_metrics(new_run_id)
