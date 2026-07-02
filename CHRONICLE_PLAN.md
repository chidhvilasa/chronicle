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
    def record_snapshot(self, snapshot: StateSnapshot) -> threading.Thread: ...
    def register_graph(self, graph, module_path: str, attr_name: str) -> bool: ...
    def flush(self) -> None: ...
    def close(self) -> None: ...
```

`register_graph` calls `POST /register` with `{graph_module, graph_attr}`
only — `graph` itself is accepted for a natural call site but never sent
over the wire (no pickling; the server re-imports the graph itself). Returns
`True`/`False` for whether the server acknowledged it; never raises.
`LangGraphAdapter(tracer, graph=..., graph_module=..., graph_attr=...)`
calls this automatically at construction time when all three are given.

`record_event` buffers a `ChronicleEvent` and auto-flushes once the buffer
reaches `batch_size`. `flush()` POSTs each buffered event to the Chronicle
server as a single-item batch (`POST /events` always takes a list); the
first `httpx.HTTPError` in a batch (server not running, connection refused,
timeout) stops further POSTs for that batch and writes the remaining unsent
events to `chronicle_runs/{run_id}.json` via `sdk/src/chronicle/storage.py`'s
`write_local_events`, so nothing already sent is duplicated and nothing
unsent is lost. `ChronicleTracer` is also a context manager that flushes on
`__exit__`.

`record_snapshot` is the one exception to "buffer, then flush synchronously":
state snapshots can be large (see `StateSnapshot` below), so they're always
shipped on a background `threading.Thread` — the call returns the `Thread`
immediately without waiting for the HTTP request, so capturing a snapshot
never blocks the agent. On failure it falls back to
`chronicle_runs/{run_id}_snapshots.json` (via `write_local_snapshots`),
guarded by an internal lock since multiple snapshot threads can be in
flight at once.

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
`on_tool_end`, `on_agent_action`, `on_agent_finish`, `on_chain_end`,
`on_chain_error`) to a `ChronicleTracer`. It correlates each `*_start`/
`*_end` pair by LangChain's own per-call `run_id` (a `uuid.UUID`, distinct
from `ChronicleTracer.run_id`) to compute `duration_ms`, and extracts
`token_usage` from `LLMResult.llm_output["token_usage"]` when the provider
populates it. It subclasses `langchain_core.callbacks.BaseCallbackHandler`
when `langchain_core` is installed, and degrades to a plain duck-typed
object otherwise, so `chronicle-sdk` has no hard dependency on LangChain.

**State snapshots** (for the future replay engine): every `on_chain_end`
call, and every `on_agent_finish` call (via `finish.return_values`, when
present), also captures a `StateSnapshot` of the graph state at that step —
`self._step_index` increments once per snapshot, giving each one a stable
0-based position in the run. Before building the snapshot, the adapter runs
the raw LangGraph output dict through `_json_safe()`, a recursive helper
that walks dicts/lists and converts any non-JSON-native leaf (LangChain
message objects, datetimes, arbitrary classes, ...) to its `str()` form,
setting `metadata["_serialization_warning"] = True` if it had to convert
anything. `_capture_snapshot()` wraps all of this in a broad
`try/except Exception` and only logs a warning on failure — a broken or
unusual graph state can never crash the agent, per Chronicle's zero-impact
design.

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

### State snapshots (dataclass)

```python
@dataclass
class StateSnapshot:
    run_id: str
    step_index: int
    event_id: str | None = None
    agent_name: str | None = None
    messages: list[Any] = field(default_factory=list)
    tool_results: list[Any] = field(default_factory=list)
    graph_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
```

`StateSnapshot.to_dict()` produces the JSON payload sent to `POST
/snapshots` and written to `chronicle_runs/{run_id}_snapshots.json`. By the
time a `StateSnapshot` is constructed, `graph_state`/`messages`/
`tool_results` are already guaranteed JSON-safe (see the LangGraph adapter's
`_json_safe()` above) — the model itself does no serialization-safety work.

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

CREATE TABLE snapshots (
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

CREATE INDEX idx_runs_run_id ON runs (run_id);
CREATE INDEX idx_events_run_id ON events (run_id);
CREATE INDEX idx_events_event_type ON events (event_type);
CREATE INDEX idx_snapshots_run_id ON snapshots (run_id);
CREATE INDEX idx_snapshots_step_index ON snapshots (step_index);
```

`runs` rows are never written incrementally: every `POST /events` batch
recomputes `started_at`/`finished_at`/`agent_count`/`total_tokens`/`status`
for each affected `run_id` directly from its rows in `events` (see
`Database._refresh_run_aggregates`), so aggregates can't drift out of sync.
`status` is `'error'` if any of the run's events are `error` events,
otherwise `'running'` — there's no explicit "run finished" signal yet (see
`KNOWN_ISSUES.md`). `total_cost_usd` and `framework` have no producer yet and
stay at their defaults (`0`, `null`) until a future phase populates them.
`snapshots` rows don't affect run aggregates at all — they're pure ingestion
for now, with no read/query endpoint yet (see Phase 10).

### Endpoints

| Method | Path                   | Description                                          |
| ------ | ---------------------- | ----------------------------------------------------- |
| GET    | `/health`              | Liveness check; returns `{status, version}`            |
| POST   | `/events`               | Ingest a batch of events; returns `{count}` written    |
| POST   | `/snapshots`            | Ingest a batch of state snapshots; returns `{count}` written |
| POST   | `/register`             | Register a LangGraph graph by `{graph_module, graph_attr}` for replay |
| GET    | `/registry`             | List registered graph names                              |
| POST   | `/replay`               | Start a replay from a snapshot; returns `{run_id}` of the new run immediately |
| GET    | `/runs`                 | List all runs, newest first, with summary stats        |
| GET    | `/runs/{id}/events`     | List all events for a run, chronological                |
| GET    | `/runs/{id}/timeline`   | Per-agent lanes of segments, shaped by `server/src/timeline.py` |
| GET    | `/runs/{id}/snapshots`  | List a run's snapshots (summary only), ordered by `step_index` |
| GET    | `/runs/{id}/snapshots/{snapshot_id}` | Full snapshot detail, incl. `graph_state`/`messages`/`tool_results` |
| DELETE | `/runs/{id}`            | Delete a run and all its events and snapshots            |

`GET /runs/{id}/events`, `GET /runs/{id}/timeline`, `GET /runs/{id}/snapshots`,
and `DELETE /runs/{id}` all 404 when the run doesn't exist.
`GET /runs/{id}/snapshots/{snapshot_id}` 404s if the snapshot doesn't exist
*or* belongs to a different run. `POST /replay` 400s with "No graph
registered. Call tracer.register_graph() before replaying." if nothing has
been registered yet. Every error response has the same shape:
`{"error": "<short_code>", "detail": "<human-readable message>"}`, produced
by global `StarletteHTTPException`/`RequestValidationError` handlers in
`server/src/main.py`.

### Replay engine (`server/src/replay.py`, `server/src/registry.py`)

`GraphRegistry` holds at most a handful of graph objects in memory, keyed by
`"{graph_module}.{graph_attr}"`; `get_active()` returns the most recently
registered one, which is what `POST /replay` uses (there's no per-run
graph selection yet — one server process is expected to have one agent's
graph registered at a time). `ReplayEngine.start_replay(snapshot,
modifications, new_run_id, source_run_id)`:

1. Stamps the new run's `metadata` (`is_replay`/`source_run_id`/
   `source_snapshot_id`/`step_index`) immediately, before doing anything
   slow, so the run shows up in `GET /runs` right away.
2. Copies the snapshot's `graph_state` and applies `modifications` on top
   (a shallow `dict.update`) — no deep-merge, so a modification key
   replaces that key's entire value rather than merging into it.
3. Lazily imports `chronicle` (the SDK); if it isn't installed, marks the
   run `"failed"` and returns instead of crashing the server.
4. Builds a fresh `ChronicleTracer(run_id=new_run_id)` and
   `LangGraphAdapter`, then calls `graph.invoke(state, config={"callbacks":
   [adapter]})` inside `asyncio.to_thread` — every event and snapshot the
   replayed graph produces is recorded under `new_run_id` through the exact
   same instrumentation path a live agent uses.
5. Flushes the tracer, then writes the final `"complete"`/`"failed"`
   status — in that order, so the status write is never clobbered by the
   aggregate refresh that flushing triggers.

### Timeline shaping (`server/src/timeline.py`)

`build_timeline(events)` groups a run's events into one lane per
`agent_name` (events with no `agent_name` fall into an `"unknown"` lane).
Within each lane, `llm_call`/`tool_call`/`retry`/`error` events become
segments (`{type, start_time_ms, duration_ms, label, token_usage, event_id}`);
`start_time_ms` is relative to the run's earliest event. `retry` segments
label from `data["reason"]` (falling back to `"retry"`). Any positive gap
between two consecutive segments in the same lane becomes a synthetic
`waiting` segment filling that gap (`event_id: null`, since it isn't backed
by a real event). Every other segment carries its source event's `event_id`
so the app can look up the full event for the Inspector's Event tab.
`agent_message`/`memory_update` events currently produce no segment (see
`KNOWN_ISSUES.md`).

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
`selectedRunId`, `loading`, `error`, `activePanel`, `selectedDetail`, plus
(as of the replay UI) `diffPrefill` and `toast` — see "Replay UI" below.

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

### Inspector (`app/src/components/Inspector/`)

The collapsible right panel. `Inspector.tsx` fetches `GET /runs/{id}/events`
for the selected run and renders an Event/Agent/Tools tab bar; each tab's
selection lives in its own store field (`selectedDetail`/`selectedAgentName`/
`selectedToolName`) so switching tabs never loses the other tabs' state.
`EventInspector.tsx` renders full detail for the selected event or timeline
segment (segments resolve to their source event via `event_id`, falling back
to the segment's own summary if the event can't be found — e.g. synthetic
`waiting` segments have no `event_id`). `AgentInspector.tsx` and
`ToolInspector.tsx` render aggregate stats computed by pure functions in
`summarize.ts` (`summarizeAgent`, `summarizeTools`) over the run's full event
list — no additional server endpoints needed. Prompt/response and JSON
payloads render in a plain scrollable monospace `.code-block`, not a real
syntax-highlighted code view (no highlighting library is included yet; see
`KNOWN_ISSUES.md`).

### Diff (`app/src/components/Diff/`)

The Diff tab. `Diff.tsx` owns two `RunSelector.tsx` dropdowns (each disables
the run picked in the other, so the same run can't be selected twice), fetches
`GET /runs/{id}/events` for both selected runs in parallel, and renders
`DiffSummary.tsx` plus `EventDiffList.tsx`. All diffing is pure, synchronous,
client-side logic in `computeDiff.ts` — no diff-specific server endpoint.
`computeRunStats(run, events)` derives duration (from `Run.started_at`/
`finished_at`), tokens (`Run.total_tokens`), an estimated cost (summed from
events' `input_tokens`/`output_tokens`, same constants as `TokenUsageSummary`),
error count, and tool-call count; `DiffSummary.tsx` colors the B-minus-A delta
green when B is lower (faster/cheaper/fewer) and red otherwise.
`buildEventDiffRows(eventsA, eventsB)` zips both event lists **by index**
(sequence position, not content matching) up to
`Math.max(eventsA.length, eventsB.length)`; a row is `"missing_a"`/
`"missing_b"` when only one side has an event at that position, otherwise
`"same"` or `"different"` based on whether duration/tokens/tool
name/error differ. `EventDiffList.tsx` colors `different` rows yellow and
`missing_*` rows red. For a row where both sides are `llm_call`,
`PromptDiff.tsx` renders a character-level diff of `data.prompt` via the
`diff` package's `diffChars` (additions green, removals red-strikethrough,
unchanged gray). If either selected run has more than 500 events, `Diff.tsx`
shows a warning banner but still renders the full comparison.

### Replay UI (`app/src/components/Replay/`)

`Timeline.tsx` fetches `GET /runs/{id}/snapshots` alongside the timeline
itself and builds an `event_id -> snapshot_id` map. `TimelineChart.tsx`
tracks a hovered segment via ECharts' `mouseover`/`mouseout` events (not a
pixel-perfect canvas overlay — see "Known constraints") and shows a
floating "Replay from here" button when the hovered segment's `event_id`
has a matching snapshot, with a short (`250ms`) hide delay so the cursor
can travel from the segment to the button without it disappearing.
Clicking it opens `Replay/ReplayModal.tsx`, which:

1. Fetches the full snapshot via `GET /runs/{id}/snapshots/{snapshot_id}`
   and shows its step index, timestamp, agent name, and a graph-state
   summary (message count, last tool result).
2. Offers a plain-`<textarea>` "Modifications" JSON editor (placeholder
   `{ "override_key": "new_value" }`) and two buttons, "Replay as-is" and
   "Replay with modifications" — the latter parses the textarea as JSON
   client-side and shows a red validation error without calling the server
   if it doesn't parse.
3. Calls `POST /replay`, which returns the new run's `run_id` immediately
   (the server replays in a `BackgroundTasks` job), then polls `GET /runs`
   every `REPLAY_POLL_INTERVAL_MS` until that run leaves `"running"` status
   (or `REPLAY_POLL_TIMEOUT_MS` elapses), showing "Replaying from step
   N..." meanwhile.
4. On completion, selects the new run, closes the modal, and calls
   `useAppStore`'s `showToast()` with "Replay complete. Compare with
   original?"; the toast's action sets `diffPrefill` (`{runAId, runBId}`)
   and switches to the Diff tab, which `Diff.tsx` consumes once on mount
   and clears. On failure, shows the server's error message in red instead
   of closing.

`RunList.tsx`'s `RunCard` reads `getReplayMetadata(run)` (in
`app/src/types`, parsing `metadata.is_replay`/`source_run_id`/
`source_snapshot_id`/`step_index`) and renders a purple `REPLAY` badge with
a `title` tooltip ("Replayed from run {source_run_id} at step
{step_index}") next to the run ID when present. `Toast.tsx` is a generic
bottom-of-screen notification reading `useAppStore`'s `toast` field,
auto-dismissing after `TOAST_DURATION_MS`.

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
  event_id: string | null;
}

export interface TimelineLane {
  agent_name: string;
  segments: TimelineSegment[];
}

export interface SnapshotSummary {
  snapshot_id: string; step_index: number; timestamp: number;
  agent_name: string | null; event_id: string | null;
}

export interface Snapshot extends SnapshotSummary {
  run_id: string; graph_state: Record<string, unknown>;
  messages: unknown[]; tool_results: unknown[]; metadata: Record<string, unknown>;
}
```

These mirror `server/src/models.py`'s `EventOut`/`RunOut`/
`TimelineSegmentOut`/`TimelineLaneOut`/`SnapshotSummaryOut`/`SnapshotOut`
field-for-field. `getReplayMetadata(run: Run)` reads a replay run's
`is_replay`/`source_run_id`/`source_snapshot_id`/`step_index` out of
`Run.metadata`, returning `null` if the shape doesn't match.

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
- **Phase 6 — Agent inspector + tool inspector**: rebuilt the right panel as
  `app/src/components/Inspector/` with an Event/Agent/Tools tab bar
  (`Inspector.tsx`) that preserves the last selection per tab
  (`useAppStore`'s `inspectorTab`/`selectedDetail`/`selectedAgentName`/
  `selectedToolName`). `EventInspector.tsx` shows full detail for the
  selected timeline segment or event row — prompt/response for `llm_call`,
  arguments/result/status for `tool_call`, message/traceback/agent for
  `error` — resolving a clicked segment to its full event via the new
  `event_id` field threaded through `server/src/timeline.py`. Clicking an
  agent's lane header in the Timeline (`TimelineChart.tsx`'s `yAxis`
  `triggerEvent`) opens `AgentInspector.tsx` (LLM/tool call counts, total
  tokens, error count, average LLM latency, tool usage breakdown).
  `ToolInspector.tsx` shows every tool used in the run (call count, success
  rate, avg latency, tokens) with a click-through per-call list. Both are
  driven by pure functions in `Inspector/summarize.ts`.
- **Phase 7 — Execution diff**: `app/src/components/Diff/` replaces the Diff
  tab's placeholder — two run-selector dropdowns (can't pick the same run
  twice), a side-by-side summary (duration/tokens/cost/errors/tool calls,
  deltas colored green/red), a positional event-by-event diff list
  (same/different/missing-in-other-run rows), and a character-level prompt
  diff (via the `diff` package) for `llm_call` events at the same position
  in both runs. All diffing happens client-side; a run pair with either run
  over 500 events shows a warning banner but still renders.
- **Phase 8 — Release v0.1.0**: unified all package versions at `0.1.0`;
  added `.github/workflows/release.yml` (tag-triggered Tauri builds for
  Windows/macOS/Linux plus a `chronicle-sdk` wheel, uploaded to a GitHub
  Release); security review (no secrets, CORS restricted, prod console
  stripped); README/CHANGELOG/KNOWN_ISSUES brought up to date for a public
  v0.1.0 tag.
- **Phase 9 — State snapshots in the SDK**: added
  `chronicle.models.StateSnapshot` and `ChronicleTracer.record_snapshot()`
  (background-thread delivery, `chronicle_runs/{run_id}_snapshots.json`
  fallback). `LangGraphAdapter` now captures a snapshot after every
  `on_chain_end` and `on_agent_finish`, converting non-JSON-serializable
  graph-state values to strings via a new `_json_safe()` helper rather than
  crashing the agent. Added the server's `snapshots` table and a
  write-only `POST /snapshots`. Incidentally fixed a real bug found while
  touching `tracer.py`: `flush()` was POSTing a bare event object to
  `/events` instead of a single-item list, which the server's
  `list[EventIn]` body would have rejected with a 422 against any real
  (non-fallback) delivery — no existing test caught it because every SDK
  test points at an unreachable server.
- **Phase 10 — Replay engine in the server** *(this phase)*: added
  `GET /runs/{id}/snapshots` (step-ordered summaries) and
  `GET /runs/{id}/snapshots/{snapshot_id}` (full detail, incl.
  `graph_state`). Added `server/src/registry.py`'s `GraphRegistry` —
  `POST /register` imports a graph by `{graph_module, graph_attr}` (never
  pickled: unpickling a request body would be remote code execution) and
  holds it in memory for the server process's lifetime; `GET /registry`
  lists registered names. Added `server/src/replay.py`'s `ReplayEngine`:
  `POST /replay` loads a snapshot, applies `modifications` to its
  `graph_state`, and schedules `ReplayEngine.start_replay` as a
  `BackgroundTasks` job so the HTTP response returns immediately with the
  new run's `run_id`. The replay itself instruments the re-invoked graph
  with `chronicle-sdk`'s own `ChronicleTracer`/`LangGraphAdapter` — the
  server briefly acts as the "agent process" — recording every event under
  the new run, stamping `runs.metadata` with `{is_replay: true,
  source_run_id, source_snapshot_id, step_index}` up front via the new
  `Database.set_run_metadata`, and setting the final `runs.status` to
  `"complete"`/`"failed"` via the new `Database.set_run_status` (called
  *after* the tracer flushes, so it isn't overwritten by the normal
  events-derived aggregate refresh). `chronicle.invoke()` runs inside
  `asyncio.to_thread` so a slow/blocking graph never stalls the event
  loop. `chronicle-sdk` is now an optional *runtime* dependency of
  `chronicle-server` — a new architectural coupling that didn't exist
  before this phase (see "Known constraints" below). Added
  `ChronicleTracer.register_graph()` and auto-registration via
  `LangGraphAdapter(..., graph=, graph_module=, graph_attr=)`.
- **Phase 11 — Replay UI + release v0.2.0** *(this phase)*: added
  `app/src/components/Replay/ReplayModal.tsx` and a "Replay from here"
  hover button on timeline segments backed by a snapshot
  (`TimelineChart.tsx`'s `mouseover`/`mouseout`, with a short hide delay).
  The modal shows snapshot detail, an optional JSON modifications
  textarea, calls `POST /replay`, and polls `GET /runs` until the new run
  finishes. Added a purple `REPLAY` badge with a source-run/step tooltip to
  `RunList.tsx` (via the new `getReplayMetadata()` helper), and a
  `Toast.tsx` component wired to new `useAppStore` fields
  (`diffPrefill`/`toast`) so a completed replay can offer a one-click
  "Compare with original?" shortcut into the Diff tab with both runs
  pre-selected. Unified all package versions at `0.2.0`.
- **Future work**: run search/filter in the sidebar, latency/error-rate
  analytics dashboards, CrewAI/AutoGen adapters, an accessibility pass, and
  a public docs site remain unscheduled.

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
- **`chronicle-server` now optionally depends on `chronicle-sdk` at runtime
  (as of Phase 10)**: this is a new architectural coupling — before the
  replay engine, `/server` and `/sdk` were fully independent packages.
  `server/src/replay.py` lazily imports `chronicle` so the rest of the
  server keeps working even if it isn't installed (replay just fails
  cleanly, marking the run `"failed"`); CI's `server-tests` job now
  installs `sdk` before `server` so this path is actually exercised, and a
  real deployment needs both installed in the same Python environment for
  replay to work.
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
- **The "Replay from here" button is a floating DOM overlay, not a
  canvas-anchored element (as of Phase 11)**: `TimelineChart.tsx` is an
  ECharts canvas, which can't render real DOM buttons inside it. Rather
  than a pixel-perfect overlay tracking the canvas's internal coordinate
  system, the button is positioned via the raw `offsetX`/`offsetY` from
  ECharts' `mouseover` event and shown/hidden with a `250ms` delay so the
  cursor can reach it — a deliberately simple approach over a fragile
  cursor-following one.
