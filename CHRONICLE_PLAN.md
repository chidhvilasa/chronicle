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

FastAPI app (`server/src/main.py`), run as `uvicorn src.main:app`, listening
on `127.0.0.1:7823` by default with CORS restricted to
`http://localhost:1420` (the Tauri dev server). Backed by SQLite via
`aiosqlite` (`server/src/database.py`).

### Schema

```sql
CREATE TABLE runs (
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

CREATE TABLE events (
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

CREATE INDEX idx_runs_run_id ON runs (run_id);
CREATE INDEX idx_events_run_id ON events (run_id);
CREATE INDEX idx_events_event_type ON events (event_type);
```

`runs` rows are never written incrementally: every `POST /events` batch
recomputes `started_at`/`finished_at`/`agent_count`/`total_tokens`/`status`
for each affected `run_id` directly from its rows in `events` (see
`Database._refresh_run_aggregates`), so aggregates can't drift out of sync.
`status` is `'error'` if any of the run's events are `error` events,
otherwise `'running'` — there's no explicit "run finished" signal yet (see
`KNOWN_ISSUES.md`). `total_cost_usd` and `framework` have no producer yet and
stay at their defaults (`0`, `null`) until a future phase populates them.

### Endpoints

| Method | Path                   | Description                                          |
| ------ | ---------------------- | ----------------------------------------------------- |
| GET    | `/health`              | Liveness check; returns `{status, version}`            |
| POST   | `/events`               | Ingest a batch of events; returns `{count}` written    |
| GET    | `/runs`                 | List all runs, newest first, with summary stats        |
| GET    | `/runs/{id}/events`     | List all events for a run, chronological                |
| GET    | `/runs/{id}/timeline`   | Per-agent lanes of segments, shaped by `server/src/timeline.py` |
| DELETE | `/runs/{id}`            | Delete a run and all its events                         |

`GET /runs/{id}/events`, `GET /runs/{id}/timeline`, and `DELETE /runs/{id}`
all 404 when the run doesn't exist. Every error response — 404s, 422
validation errors, everything else — has the same shape:
`{"error": "<short_code>", "detail": "<human-readable message>"}`, produced
by global `StarletteHTTPException`/`RequestValidationError` handlers in
`server/src/main.py`.

### Timeline shaping (`server/src/timeline.py`)

`build_timeline(events)` groups a run's events into one lane per
`agent_name` (events with no `agent_name` fall into an `"unknown"` lane).
Within each lane, `llm_call`/`tool_call`/`retry`/`error` events become
segments (`{type, start_time_ms, duration_ms, label, token_usage}`);
`start_time_ms` is relative to the run's earliest event. `retry` segments
label from `data["reason"]` (falling back to `"retry"`). Any positive gap
between two consecutive segments in the same lane becomes a synthetic
`waiting` segment filling that gap. `agent_message`/`memory_update` events
currently produce no segment (see `KNOWN_ISSUES.md`).

## 4. App design (`/app`)

Tauri + React + TypeScript desktop app, three-panel layout under a top nav:

- **Top nav** (`app/src/components/TopNav.tsx`): Chronicle brand, panel
  switcher tabs (Timeline / Inspector / Diff), a settings icon (no
  functionality yet), and a connection-status dot that polls `GET /health`
  every `HEALTH_CHECK_INTERVAL_MS`.
- **Left sidebar, 240px** (`app/src/components/RunList.tsx`): polls
  `GET /runs` every `RUN_LIST_POLL_INTERVAL_MS` (see `app/src/config`) and
  renders a card per run — truncated `run_id`, a status badge, relative
  start time, total tokens, and duration. Empty state: "No runs yet.
  Instrument your agent with the Chronicle SDK." Clicking a card selects
  the run.
- **Main panel** (`app/src/components/MainPanel.tsx`): renders whichever tab
  is active — `Timeline` (`app/src/components/Timeline/`, an ECharts
  swimlane chart of `GET /runs/{id}/timeline`), `InspectorPanel` (flat
  chronological event list from `GET /runs/{id}/events`), or `DiffPanel`
  (placeholder; real diffing is a later phase). Clicking a segment or event
  row sets it as the selected detail item.
- **Right panel, 320px, collapsible** (`app/src/components/DetailInspector.tsx`):
  shows the full JSON of whichever event or segment is currently selected.

State lives in a Zustand store (`app/src/store/useAppStore.ts`): `runs`,
`selectedRunId`, `loading`, `error`, `activePanel`, `selectedDetail`.

The app talks to the server exclusively over its REST API
(`app/src/api/client.ts`) — it holds no direct database access. Every fetch
has a `FETCH_TIMEOUT_MS` (5s) timeout via `AbortController`; failures surface
as `ChronicleApiError.message`, parsed from the server's
`{error, detail}` body when available, never a raw stack trace.

### Execution timeline (`app/src/components/Timeline/`)

- **`Timeline.tsx`**: fetches `GET /runs/{id}/timeline` for the selected run
  and owns loading/empty/error UI state, plus the segment-type filter
  ("all"/"llm"/"tools"/"errors") and zoom level. Loading renders skeleton
  lane bars; a run with no segments in any lane renders "No events recorded
  for this run."; a fetch failure renders `ChronicleApiError.message` with a
  Retry button that re-fetches.
- **`TimelineChart.tsx`**: the actual swimlane chart, built on an Apache
  ECharts `custom` series (not React Flow — a `renderItem` callback draws
  one rect per segment, the standard ECharts Gantt-chart pattern), with one
  `yAxis` category per agent lane and a `value`-type `xAxis` in milliseconds
  from the run's start. Segment colors: `llm_call` blue, `tool_call` orange,
  `waiting` translucent gray, `error` red, `retry` yellow. Hovering shows a
  tooltip (event type, agent, duration, tokens, and the tool/model name
  where applicable); clicking calls `onSegmentSelect(segment)`. Zoom is
  implemented via ECharts' `dataZoom`, dispatched imperatively when the
  `zoom` prop changes. `echarts.init`/`dispose` are scoped to mount/unmount
  so re-renders reuse the same chart instance via `setOption`.
- **`TokenUsageSummary.tsx`**: sums `token_usage.input_tokens`/
  `output_tokens` across every segment in every lane and renders total
  input/output tokens plus an estimated cost, using
  `COST_PER_INPUT_TOKEN_USD`/`COST_PER_OUTPUT_TOKEN_USD` (see
  `app/src/config`) — configurable constants, not hardcoded in the
  component.
- **`TimelineControls.tsx`**: zoom in/out/fit-to-screen buttons and the
  filter dropdown; purely presentational, driven by props from `Timeline.tsx`.

### TypeScript interfaces (`app/src/types/index.ts`)

```typescript
export type EventType =
  | "tool_call" | "llm_call" | "agent_message" | "memory_update" | "error" | "retry";

export interface Event {
  event_id: string; run_id: string; timestamp: number; event_type: EventType;
  agent_name: string | null; duration_ms: number | null;
  input_tokens: number | null; output_tokens: number | null;
  data: Record<string, unknown>; error: string | null;
}

export interface Run {
  run_id: string; started_at: number; finished_at: number;
  framework: string | null; agent_count: number; total_tokens: number;
  total_cost_usd: number; status: string; metadata: Record<string, unknown>;
}

export type TimelineSegmentType = "llm_call" | "tool_call" | "waiting" | "error" | "retry";

export interface TimelineSegment {
  type: TimelineSegmentType; start_time_ms: number; duration_ms: number;
  label: string; token_usage: { input_tokens: number | null; output_tokens: number | null } | null;
}

export interface TimelineLane {
  agent_name: string;
  segments: TimelineSegment[];
}
```

These mirror `server/src/models.py`'s `EventOut`/`RunOut`/
`TimelineSegmentOut`/`TimelineLaneOut` field-for-field.

### Tauri backend (`app/src-tauri/src/lib.rs`)

`start_chronicle_server`/`stop_chronicle_server` Tauri commands spawn/kill
the Chronicle server as a child process (`python -m uvicorn src.main:app`)
automatically on app launch (`.setup()`) and exit (`RunEvent::ExitRequested`).
On failure, the Rust side emits a `chronicle-server-error` event that
`app/src/hooks/useServerStartupError.ts` listens for and surfaces as a
banner. **This is not a bundled Tauri sidecar binary** — see
`KNOWN_ISSUES.md` for what that means in practice and the documented
fallback (run `chronicle-server` yourself; the app connects over HTTP
either way).

## 5. Phase-by-phase plan

- **Phase 1 — Scaffold + repo + plan**: monorepo structure, `chronicle-sdk`
  core (tracer, event schemas, local SQLite fallback, LangGraph handler),
  `chronicle-server` core (FastAPI + aiosqlite, the five endpoints above),
  `chronicle-app` shell (sidebar/timeline/inspector reading from the
  server), root docs, CI.
- **Phase 2 — Python SDK core + LangGraph adapter**:
  rebuilt the event model as `chronicle.models.ChronicleEvent`/`TokenUsage`
  dataclasses; `ChronicleTracer.record_event()` buffers events and flushes
  them to the server in batches via `POST /events`, falling back to
  `chronicle_runs/{run_id}.json` on failure; added
  `chronicle.adapters.langgraph.LangGraphAdapter` implementing
  `on_llm_start`/`on_llm_end`/`on_tool_start`/`on_tool_end`/
  `on_agent_action`/`on_agent_finish`/`on_chain_error` with duration and
  token-usage capture; expanded test coverage (models, tracer, adapter).
- **Phase 3 — Chronicle server + SQLite storage** *(this phase)*: rebuilt
  `/server` as a flat `src` package (`uvicorn src.main:app`) matching the
  Phase 2 SDK event model end-to-end — `POST /events` now accepts a batch
  and stores `event_id`/`data`/`agent_name`/`duration_ms`/`input_tokens`/
  `output_tokens`/`error` (closing the schema-drift gap from Phase 2); added
  the `runs.framework`/`agent_count`/`total_tokens`/`total_cost_usd`/
  `status`/`metadata` summary columns, recomputed from `events` on every
  write; added `server/src/timeline.py` to shape events into per-agent
  lanes of `llm_call`/`tool_call`/`waiting`/`error` segments for
  `GET /runs/{id}/timeline`; moved the default port to `7823` and restricted
  CORS to the Tauri dev origin; unified all error responses to
  `{error, detail}`.
- **Phase 4 — Tauri app shell + run list**: rebuilt
  `app/src/types/index.ts` and `app/src/api/client.ts` to match the Phase 3
  server response shapes field-for-field (closing the Phase 3 drift gap),
  with `AbortController`-based 5s timeouts on every request. Added the
  three-panel layout — `TopNav`, `RunList` (polling `GET /runs`), `MainPanel`
  (Timeline/Inspector/Diff tabs), `DetailInspector` (collapsible) — backed by
  a Zustand store (`app/src/store/useAppStore.ts`). Added
  `start_chronicle_server`/`stop_chronicle_server` Tauri commands that spawn
  and kill the server as a child process on launch/exit, with a
  `chronicle-server-error` event surfaced as a UI banner on failure (not a
  bundled sidecar binary — see `KNOWN_ISSUES.md`).
- **Phase 5 — Execution timeline UI** *(this phase)*: replaced the flat
  `TimelinePanel` list with `app/src/components/Timeline/` — an ECharts
  `custom`-series swimlane chart (one lane per agent, colored segments per
  type, hover tooltips, click-to-inspect), a `TokenUsageSummary` bar (total
  input/output tokens and an estimated cost via configurable
  `COST_PER_INPUT_TOKEN_USD`/`COST_PER_OUTPUT_TOKEN_USD` constants), and
  `TimelineControls` (zoom in/out/fit, an all/llm/tools/errors filter).
  Added `retry` as a fourth segment type end-to-end (`server/src/timeline.py`,
  `server/src/models.py`, `app/src/types`) so retries render as yellow
  segments instead of being silently dropped. Loading shows skeleton lane
  bars; a run with no segments shows "No events recorded for this run.";
  fetch failures show a human-readable message with a Retry button.
- **Phase 6 — Replay & live updates**: subscribe to a future WebSocket
  stream so the timeline updates live while an agent runs; step-by-step
  visual replay of a captured run; a real diff view comparing two runs
  (e.g. before/after a prompt change) to replace the Diff tab's placeholder;
  run search/filter in the sidebar.
- **Phase 7 — Analytics**: latency and error-rate aggregation (beyond the
  Phase 5 token/cost summary), both per-run and across all runs, surfaced
  as charts in the app.
- **Phase 8 — Packaging & distribution**: publish `chronicle-sdk` to PyPI,
  build signed Tauri installers for macOS/Windows/Linux with auto-update.
- **Phase 9 — Polish & hardening**: accessibility pass, human-readable error
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
- **The Tauri app doesn't bundle the server as a real sidecar (as of Phase
  4)**: `start_chronicle_server`/`stop_chronicle_server` spawn `python -m
  uvicorn` as a plain child process pointed at the sibling `/server` dev
  checkout, not a PyInstaller-built binary declared via `tauri.conf.json`'s
  `bundle.externalBin`. It only works in a dev checkout with `python` on
  `PATH` and `chronicle-server` installed; a packaged app would need a real
  bundled sidecar (future work). The documented fallback — run the server
  yourself and let the app connect over HTTP — always works regardless. See
  `KNOWN_ISSUES.md`.
- **Token cost estimates are a rough constant, not real pricing**: the
  timeline's cost estimate multiplies token counts by fixed
  `COST_PER_INPUT_TOKEN_USD`/`COST_PER_OUTPUT_TOKEN_USD` constants
  (`app/src/config`), not the actual per-model pricing of whatever LLM
  provider produced the tokens. Treat it as a ballpark, not a bill.
