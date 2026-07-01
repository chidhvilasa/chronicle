"""ChronicleTracer: captures agent run events and ships them to the Chronicle server."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from chronicle.models import ChronicleEvent, EventType, TokenUsage
from chronicle.storage import DEFAULT_LOCAL_DIR, write_local_events

DEFAULT_SERVER_URL = "http://127.0.0.1:8765"
DEFAULT_BATCH_SIZE = 10


class ChronicleTracer:
    """Captures events for a single agent run and ships them to the Chronicle server.

    Events are buffered and flushed to the server in batches via
    `POST /events`. If the server is unreachable, the remaining events in the
    batch are written to `chronicle_runs/{run_id}.json` instead, so no traces
    are lost while the desktop app isn't running.
    """

    def __init__(
        self,
        run_id: str | None = None,
        server_url: str = DEFAULT_SERVER_URL,
        batch_size: int = DEFAULT_BATCH_SIZE,
        timeout: float = 2.0,
        local_dir: Path | str = DEFAULT_LOCAL_DIR,
    ) -> None:
        self.run_id = run_id or str(uuid.uuid4())
        self.server_url = server_url.rstrip("/")
        self.batch_size = batch_size
        self.local_dir = local_dir
        self._client = httpx.Client(timeout=timeout)
        self._buffer: list[ChronicleEvent] = []

    def record_event(
        self,
        event_type: EventType,
        data: dict[str, Any] | None = None,
        agent_name: str | None = None,
        duration_ms: float | None = None,
        token_usage: TokenUsage | None = None,
        error: str | None = None,
    ) -> ChronicleEvent:
        """Buffer a new event for this run, flushing if the batch is full."""
        event = ChronicleEvent(
            run_id=self.run_id,
            event_type=event_type,
            agent_name=agent_name,
            data=data or {},
            duration_ms=duration_ms,
            token_usage=token_usage,
            error=error,
        )
        self._buffer.append(event)
        if len(self._buffer) >= self.batch_size:
            self.flush()
        return event

    def flush(self) -> None:
        """Send buffered events to the server; fall back to local JSON on failure."""
        if not self._buffer:
            return
        batch, self._buffer = self._buffer, []

        for index, event in enumerate(batch):
            try:
                response = self._client.post(f"{self.server_url}/events", json=event.to_dict())
                response.raise_for_status()
            except httpx.HTTPError:
                unsent = batch[index:]
                write_local_events(
                    self.run_id,
                    [e.to_dict() for e in unsent],
                    local_dir=self.local_dir,
                )
                break

    def close(self) -> None:
        self.flush()
        self._client.close()

    def __enter__(self) -> "ChronicleTracer":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
