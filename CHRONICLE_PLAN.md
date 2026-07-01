# Chronicle — Project Plan

Chronicle is the Chrome DevTools for AI agents: an open source engineering
platform for debugging, profiling, replaying, and understanding AI agent
systems.

## 1. Architecture

```
┌──────────────────┐        HTTP POST /events        ┌────────────────────┐
│  chronicle-sdk    │ ───────────────────────────────▶│  chronicle-server   │
│  (Python, runs    │                                  │  (FastAPI)          │
│  inside the       │   falls back to local SQLite     │                     │
│  agent process)   │   if the server is unreachable   │  SQLite (aiosqlite) │
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
   integration, e.g. the LangGraph callback handler).
2. Every significant thing the agent does — a tool call, an LLM call, a
   message, a memory write, an error, a retry — becomes a `ChronicleEvent`
   and is POSTed to the local Chronicle server.
3. The server persists events (and derives run metadata) in SQLite via
   `aiosqlite`.
4. The desktop app polls/queries the server's REST API and renders a run
   list, a timeline, and an inspector for the selected event.
5. If the server isn't running, the SDK writes events directly to the same
   local SQLite file so no traces are lost — the desktop app will pick them
   up next time it queries that database.

## 2. SDK design (`/sdk`)

### `ChronicleTracer`

The core class agents instrument with. One tracer instance represents one
run (`run_id`). See `sdk/src/chronicle/tracer.py`.

```python
class ChronicleTracer:
    def __init__(self, run_id=None, server_url=DEFAULT_SERVER_URL, timeout=2.0, local_db_path=DEFAULT_DB_PATH): ...
    def log_event(self, event_type, payload, parent_id=None) -> ChronicleEvent: ...
    def tool_call(self, tool_name, arguments, **extra) -> ChronicleEvent: ...
    def llm_call(self, model, **extra) -> ChronicleEvent: ...
    def agent_message(self, role, content, **extra) -> ChronicleEvent: ...
    def memory_update(self, key, new_value, **extra) -> ChronicleEvent: ...
    def error(self, message, **extra) -> ChronicleEvent: ...
    def retry(self, attempt, max_attempts, **extra) -> ChronicleEvent: ...
    def close(self) -> None: ...
```

On every call, the tracer POSTs the event to the Chronicle server; on any
`httpx.HTTPError` (server not running, connection refused, timeout) it falls
back to `LocalStorage`, which writes the same event directly into the local
SQLite database (see `sdk/src/chronicle/storage.py`).

### Event types

| Event type       | Meaning                                      |
| ---------------- | --------------------------------------------- |
| `tool_call`       | The agent invoked a tool/function              |
| `llm_call`        | A request/response to an LLM provider          |
| `agent_message`   | A message produced by the agent (or user)      |
| `memory_update`   | The agent's memory/state changed               |
| `error`           | An error occurred during the run               |
| `retry`           | An operation was retried                       |

### LangGraph / LangChain callback handler

`chronicle.integrations.langgraph.ChronicleCallbackHandler` forwards
LangChain/LangGraph lifecycle callbacks (`on_tool_start`, `on_tool_end`,
`on_llm_start`, `on_llm_end`, `on_chain_error`, `on_agent_action`) to a
`ChronicleTracer`. It subclasses `langchain_core.callbacks.BaseCallbackHandler`
when `langchain_core` is installed, and degrades to a plain duck-typed object
otherwise, so `chronicle-sdk` has no hard dependency on LangChain.

### Python event schemas (TypedDict)

See `sdk/src/chronicle/events.py` for the source of truth. Summarized:

```python
class ChronicleEvent(TypedDict):
    id: str
    run_id: str
    parent_id: str | None
    event_type: Literal["tool_call", "llm_call", "agent_message", "memory_update", "error", "retry"]
    timestamp: float
    payload: dict[str, Any]

class ToolCallPayload(TypedDict, total=False):
    tool_name: str
    arguments: dict[str, Any]
    result: Any
    duration_ms: float
    success: bool

class LLMCallPayload(TypedDict, total=False):
    model: str
    provider: str
    prompt: str
    messages: list[dict[str, Any]]
    completion: str
    prompt_tokens: int
    completion_tokens: int
    duration_ms: float
    cost_usd: float

class AgentMessagePayload(TypedDict, total=False):
    role: str
    content: str
    agent_name: str

class MemoryUpdatePayload(TypedDict, total=False):
    key: str
    old_value: Any
    new_value: Any
    operation: str

class ErrorPayload(TypedDict, total=False):
    message: str
    error_type: str
    traceback: str

class RetryPayload(TypedDict, total=False):
    attempt: int
    max_attempts: int
    reason: str
```

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

- **Phase 1 — Scaffold + repo + plan** *(this phase)*: monorepo structure,
  `chronicle-sdk` core (tracer, event schemas, local SQLite fallback,
  LangGraph handler), `chronicle-server` core (FastAPI + aiosqlite, the five
  endpoints above), `chronicle-app` shell (sidebar/timeline/inspector reading
  from the server), root docs, CI.
- **Phase 2 — SDK hardening**: async HTTP client with event batching and
  retry/backoff, context-manager based spans for automatic parent/child
  event nesting, thin instrumentation wrappers for the OpenAI and Anthropic
  Python SDKs, a `chronicle doctor` CLI command to check server
  reachability, expanded test coverage.
- **Phase 3 — Server hardening**: a WebSocket endpoint for live event
  streaming to the app, run search/filtering/pagination, JSONL export and
  import, a background retention/cleanup job, consistent structured error
  responses.
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
  always tries the local server first, but falls back to writing events
  directly into the local SQLite database (`~/.chronicle/chronicle.db` by
  default) when the server is unreachable, so instrumentation never blocks
  or loses data because the UI happens to be closed.
