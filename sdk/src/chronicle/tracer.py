"""ChronicleTracer: captures agent run events and ships them to the Chronicle server."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from chronicle.events import (
    ChronicleEvent,
    EventTypeLiteral,
    new_event,
)
from chronicle.storage import DEFAULT_DB_PATH, LocalStorage

DEFAULT_SERVER_URL = "http://127.0.0.1:8765"


class ChronicleTracer:
    """Captures events for a single agent run and sends them to the Chronicle server.

    If the server is unreachable, events fall back to a local SQLite database
    so no traces are lost while the desktop app isn't running.
    """

    def __init__(
        self,
        run_id: str | None = None,
        server_url: str = DEFAULT_SERVER_URL,
        timeout: float = 2.0,
        local_db_path: Path | str = DEFAULT_DB_PATH,
    ) -> None:
        self.run_id = run_id or str(uuid.uuid4())
        self.server_url = server_url.rstrip("/")
        self._local_db_path = local_db_path
        self._client = httpx.Client(timeout=timeout)
        self._local_storage: LocalStorage | None = None

    def _fallback_storage(self) -> LocalStorage:
        if self._local_storage is None:
            self._local_storage = LocalStorage(db_path=self._local_db_path)
        return self._local_storage

    def _send(self, event: ChronicleEvent) -> None:
        try:
            response = self._client.post(f"{self.server_url}/events", json=event)
            response.raise_for_status()
        except httpx.HTTPError:
            self._fallback_storage().write_event(event)

    def log_event(
        self,
        event_type: EventTypeLiteral,
        payload: dict[str, Any],
        parent_id: str | None = None,
    ) -> ChronicleEvent:
        """Build, send, and return a `ChronicleEvent` for this run."""
        event = new_event(self.run_id, event_type, payload, parent_id=parent_id)
        self._send(event)
        return event

    def tool_call(self, tool_name: str, arguments: dict[str, Any], **extra: Any) -> ChronicleEvent:
        return self.log_event("tool_call", {"tool_name": tool_name, "arguments": arguments, **extra})

    def llm_call(self, model: str, **extra: Any) -> ChronicleEvent:
        return self.log_event("llm_call", {"model": model, **extra})

    def agent_message(self, role: str, content: str, **extra: Any) -> ChronicleEvent:
        return self.log_event("agent_message", {"role": role, "content": content, **extra})

    def memory_update(self, key: str, new_value: Any, **extra: Any) -> ChronicleEvent:
        return self.log_event("memory_update", {"key": key, "new_value": new_value, **extra})

    def error(self, message: str, **extra: Any) -> ChronicleEvent:
        return self.log_event("error", {"message": message, **extra})

    def retry(self, attempt: int, max_attempts: int, **extra: Any) -> ChronicleEvent:
        return self.log_event(
            "retry", {"attempt": attempt, "max_attempts": max_attempts, **extra}
        )

    def close(self) -> None:
        self._client.close()
        if self._local_storage is not None:
            self._local_storage.close()

    def __enter__(self) -> "ChronicleTracer":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
