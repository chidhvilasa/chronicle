# Chronicle — Project Plan

Chronicle is the Chrome DevTools for AI agents: an open source engineering
platform for debugging, profiling, replaying, and understanding AI agent
systems.

## 1. Architecture

```
┌──────────────────┐        HTTP POST /events        ┌────────────────────┐
│  chronicle-sdk    │ ───────────────────────────────▶│  chronicle-server   │
│  (Python, runs    │                                  │  (FastAPI)          │
│  inside the       │  falls back to chronicle_runs/   │                     │
│  agent process)   │  {run_id}.json if unreachable     │  SQLite (aiosqlite) │
└──────────────────┘                                   └─────────┬──────────┘
                                                                  │ REST
                                                                  ▼
                                                        ┌────────────────────┐
                                                        │  chronicle-app      │
                                                        │  (Tauri + React +   │
                                                        │  TypeScript)        │
                                                        └────────────────────┘
```

1. Agent code is instrumented with `ChronicleTracer` (or a framework
   adapter, e.g. `LangGraphAdapter`).
2. Every significant thing the agent does — a tool call, an LLM call, a
   message, a memory write, an error, a retry — becomes a `ChronicleEvent`
   and is buffered by the tracer.
3. The tracer flushes buffered events to the local Chronicle server in
   batches via `POST /events`; the server persists them (and derives run
   metadata) in SQLite via `aiosqlite`.
4. The desktop app polls/queries the server's REST API and renders a run
   list, a timeline, and an inspector for the selected event.
5. If the server isn't running, the tracer writes the unsent events to
   `chronicle_runs/{run_id}.json` instead, so no traces are lost while the
   desktop app isn't running.

## 2. SDK design (`/sdk`)

### `ChronicleTracer`

The core class agents instrument with. One tracer instance represents one
run (`run_id`). See `sdk/src/chronicle/tracer.py`.

```python
class ChronicleTracer:
    def __init__(self, run_id=None, server_url=DEFAULT_SERVER_URL, batch_size=10, timeout=2.0, local_dir=DEFAULT_LOCAL_DIR): ...
    def record_event(self, event_type, data=None, agent_name=None, duration_ms=None, token_usage=None, error=None) -> ChronicleEvent: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...
```

`record_event` buffers a `ChronicleEvent` and auto-flushes once the buffer
reaches `batch_size`. `flush()` POSTs each buffered event to the Chronicle
server; the first `httpx.HTTPError` in a batch (server not running,
connection refused, timeout) stops further POSTs for that batch and writes
the remaining unsent events to `chronicle_runs/{run_id}.json` via
`sdk/src/chronicle/storage.py`'s `write_local_events`, so nothing already
sent is duplicated and nothing unsent is lost. `ChronicleTracer` is also a
context manager that flushes on `__exit__`.

### Event types

| Event type       | Meaning                                      |
| ---------------- | --------------------------------------------- |
| `tool_call`       | The agent invoked a tool/function              |
| `llm_call`        | A request/response to an LLM provider          |
| `agent_message`   | A message produced by the agent (or user)      |
| `memory_update`   | The agent's memory/state changed               |
| `error`           | An error occurred during the run               |
| `retry`           | An operation was retried                       |

### LangGraph / LangChain adapter

`chronicle.adapters.langgraph.LangGraphAdapter` forwards LangChain/LangGraph
lifecycle callbacks (`on_llm_start`, `on_llm_end`, `on_tool_start`,
`on_tool_end`, `on_agent_action`, `on_agent_finish`, `on_chain_error`) to a
`ChronicleTracer`. It correlates each `*_start`/`*_end` pair by LangChain's
own per-call `run_id` (a `uuid.UUID`, distinct from `ChronicleTracer.run_id`)
to compute `duration_ms`, and extracts `token_usage` from
`LLMResult.llm_output["token_usage"]` when the provider populates it. It
subclasses `langchain_core.callbacks.BaseCallbackHandler` when
`langchain_core` is installed, and degrades to a plain duck-typed object
otherwise, so `chronicle-sdk` has no hard dependency on LangChain.

### Python event model (dataclasses)

See `sdk/src/chronicle/models.py` for the source of truth. Summarized:

```python
EventType = Literal["tool_call", "llm_call", "agent_message", "memory_update", "error", "retry"]

@dataclass
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

@dataclass
class ChronicleEvent:
    run_id: str
    event_type: EventType
    agent_name: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    token_usage: TokenUsage | None = None
    error: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
```

`ChronicleEvent.to_dict()` / `TokenUsage.to_dict()` produce the JSON payload
sent to `POST /events` and written to `chronicle_runs/{run_id}.json`.

## 3. Server design (`/server`)

FastAPI app (`server/src/chronicle_server/main.py`) backed by SQLite via
`aiosqlite` (`server/src/chronicle_server/db.py`). Two tables: `runs`
(derived run metadata: `id`, `started_at`, `ended_at`, `event_count`) and
`events` (the full event log).

| Method | Path                   | Description                                          |
| ------ | ---------------------- | ----------------------------------------------------- |
| GET    | `/health`              | Liveness check                                        |
| POST   | `/events`               | Ingest one event; upserts the parent run's metadata    |
| GET    | `/runs`                 | List all runs, newest first                            |
| GET    | `/runs/{id}/events`     | List all events for a run, chronological                |
| GET    | `/runs/{id}/timeline`   | Chronological timeline for a run (same ordering, meant for the app's main panel — will diverge from `/events` once nesting/grouping is added) |
| DELETE | `/runs/{id}`            | Delete a run and all its events                         |

`GET /runs/{id}/events` and `GET /runs/{id}/timeline` both 404 with a
human-readable message when the run doesn't exist.

## 4. App design (`/app`)

Tauri + React + TypeScript desktop app. Layout: a left **sidebar** listing
runs (id, event count, start time), a main **timeline** panel showing the
selected run's events in order, and a right **inspector** panel showing the
full JSON payload of the selected event. See `app/src/components/`.

The app talks to the server exclusively over its REST API
(`app/src/api/client.ts`) — it holds no direct database access. Network and
server-down errors surface as a human-readable banner
(`ChronicleApiError.message`), never a raw stack trace.

### TypeScript interfaces (`app/src/types.ts`)

```typescript
export type EventType =
  | "tool_call"
  | "llm_call"
  | "agent_message"
  | "memory_update"
  | "error"
  | "retry";

export interface ChronicleEvent {
  id: string;
  run_id: string;
  parent_id: string | null;
  event_type: EventType;
  timestamp: number;
  payload: Record<string, unknown>;
}

export interface ChronicleRun {
  id: string;
  started_at: number;
  ended_at: number;
  event_count: number;
}
```

## 5. Phase-by-phase plan

- **Phase 1 — Scaffold + repo + plan**: monorepo structure, `chronicle-sdk`
  core (tracer, event schemas, local SQLite fallback, LangGraph handler),
  `chronicle-server` core (FastAPI + aiosqlite, the five endpoints above),
  `chronicle-app` shell (sidebar/timeline/inspector reading from the
  server), root docs, CI.
- **Phase 2 — Python SDK core + LangGraph adapter** *(this phase)*:
  rebuilt the event model as `chronicle.models.ChronicleEvent`/`TokenUsage`
  dataclasses; `ChronicleTracer.record_event()` buffers events and flushes
  them to the server in batches via `POST /events`, falling back to
  `chronicle_runs/{run_id}.json` on failure; added
  `chronicle.adapters.langgraph.LangGraphAdapter` implementing
  `on_llm_start`/`on_llm_end`/`on_tool_start`/`on_tool_end`/
  `on_agent_action`/`on_agent_finish`/`on_chain_error` with duration and
  token-usage capture; expanded test coverage (models, tracer, adapter).
- **Phase 3 — Server hardening**: reconcile `POST /events` and the `events`
  table with the Phase 2 event model (`event_id`/`data`/`agent_name`/
  `duration_ms`/`token_usage`/`error` instead of `id`/`payload`/`parent_id`),
  add a WebSocket endpoint for live event streaming to the app, run
  search/filtering/pagination, JSONL export and import, a background
  retention/cleanup job, consistent structured error responses.
- **Phase 4 — App: live timeline**: subscribe to the server's WebSocket
  stream so the timeline updates live while an agent runs, add run
  search/filter in the sidebar, an expandable tree view for parent/child
  events, and a syntax-highlighted JSON viewer in the inspector.
- **Phase 5 — Replay**: step-by-step visual replay of a captured run, and a
  diff view comparing two runs (e.g. before/after a prompt change).
- **Phase 6 — Analytics**: cost, latency, and error-rate aggregation, both
  per-run and across all runs, surfaced as charts in the app.
- **Phase 7 — Packaging & distribution**: publish `chronicle-sdk` to PyPI,
  build signed Tauri installers for macOS/Windows/Linux with auto-update.
- **Phase 8 — Polish & hardening**: accessibility pass, human-readable error
  handling audit across the whole app, full test coverage review,
  performance profiling of the app against large runs, a public docs site.

## 6. Known constraints

- **Rust/Tauri system dependencies**: building `/app` requires the Rust
  toolchain and platform WebView dependencies (WebView2 on Windows,
  WebKitGTK on Linux, the system WebView on macOS). See
  `KNOWN_ISSUES.md` and https://tauri.app/start/prerequisites/.
- **The SDK must work without the desktop app running**: `ChronicleTracer`
  always tries the local server first, but falls back to writing unsent
  events into `chronicle_runs/{run_id}.json` when the server is
  unreachable, so instrumentation never blocks or loses data because the
  UI happens to be closed.
- **SDK/server schema drift (as of Phase 2)**: the SDK's event model now
  sends `event_id`/`data`/`agent_name`/`duration_ms`/`token_usage`/`error`,
  but the server's `POST /events` still expects the Phase 1 shape
  (`id`/`payload`/`parent_id`). A live server will reject Phase 2 SDK
  traffic with a validation error until Phase 3 reconciles the two. See
  `KNOWN_ISSUES.md`.
