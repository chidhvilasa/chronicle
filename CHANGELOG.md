# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.4.0] - 2026-07-04

### Added

- `chronicle-sdk`: `chronicle.testing.models.ChronicleTest` and
  `ChronicleAssertion` — a test replays `source_run_id` from
  `source_snapshot_id` (defaulting to step 0) and checks the result
  against a list of assertions (`output_contains`/`output_not_contains`/
  `output_matches_regex`/`tool_called`/`tool_not_called`/
  `token_count_under`/`latency_under_ms`/`no_errors`, plus a `custom`
  type that always passes and just records that it ran), each scopeable
  to one `agent_name` and configurable to `on_fail: "fail"` or `"warn"`.
- `chronicle-sdk`: `chronicle.testing.runner.ChronicleTestRunner` — calls
  `POST /replay`, polls up to 5 minutes for the replay run to finish
  (returning `status: "error"`, reason `"replay timeout after 300s"` if it
  doesn't), evaluates every assertion via the pure `evaluate_assertion()`,
  and returns a `TestResult`. `run_suite()` runs a list of tests
  sequentially and aggregates pass/fail/error counts.
- `chronicle-sdk`: a pytest plugin (`chronicle.testing.pytest_plugin`,
  registered as a `pytest11` entry point) exposing the `chronicle_test`
  fixture — `chronicle_test.run("test name")` looks up a stored test by
  name and runs it, so regression tests can gate CI the same way any other
  pytest test does.
- `chronicle-sdk`: `chronicle test run [NAME]` and `chronicle test list`
  CLI commands. `chronicle test run` (no args) runs every stored test and
  exits `0` only if all of them pass, `1` otherwise — wired for CI.
- `chronicle-server`: `tests`/`test_results` SQLite tables and
  `POST/GET/DELETE /tests`, `GET /tests/{id}/history`, and
  `POST /tests/{id}/run` (awaits the replay to completion server-side and
  evaluates assertions in the same request, so the desktop app's "Run"
  button can show a spinner until a real result comes back). Every
  test-triggered replay run is stamped with
  `{triggered_by: "test", test_id}` in its metadata and never touches the
  source run.
- `chronicle-app`: a fourth top-nav tab, **Tests**. `TestList.tsx` polls
  `GET /tests` every 5s and shows a PASS/FAIL/ERROR/NEVER RUN badge, a Run
  button, and a delete confirmation per test. Every run card in
  `RunList.tsx` gained a "Create Test" button opening
  `CreateTestModal.tsx` (name, source run, snapshot picker, an assertions
  builder covering all assertion types). Clicking a test opens
  `TestResult.tsx`: a 10-run pass/fail/error history bar, the most recent
  result's per-assertion pass/fail and reason, a link to the replay run it
  created, and a "Run again" button.

## [0.3.0] - 2026-07-03

### Added

- `chronicle-sdk`: `chronicle.instrument(obj)` — one-line auto-instrumentation.
  Detects the caller's framework (`chronicle.auto._detect_framework`, by
  module path/class name only, no imports of any framework at module
  level) and wires up the matching adapter with no manual
  `ChronicleTracer`/adapter construction: a LangGraph graph is wrapped in a
  thin `_InstrumentedGraph` proxy that injects the Chronicle callback into
  every `invoke`/`ainvoke`/`stream`/`astream` call (and best-effort
  auto-calls `tracer.register_graph()` via call-stack introspection when
  `graph = chronicle.instrument(graph)` is written at module scope); an
  OpenAI Agents SDK `Agent` gets a `ChronicleAgentHooks` instance attached
  to `.hooks`; a PydanticAI `Agent` is wrapped in `ChronicleMiddleware`.
  Prints `"Chronicle: recording to http://localhost:7823 — open the
  desktop app to inspect"` on success, or `"Chronicle: server unavailable,
  writing to chronicle_runs/ locally"` if the server couldn't be reached
  or started. `chronicle.instrument_context(obj)` is the context-manager
  variant — flushes on exit and prints a one-line run summary (event
  count, total tokens, duration, `run_id`).
- `chronicle-sdk`: `chronicle.ServerManager` — auto-starts the Chronicle
  server as a subprocess (`python -m uvicorn src.main:app`, the same
  approach the Tauri app's `start_chronicle_server` uses) if
  `GET /health` isn't already reachable on `localhost:7823`, polling every
  500ms up to 5s before giving up and falling back to local file storage.
  The subprocess's PID is written to `~/.chronicle/server.pid` and
  terminated via `atexit` when the Python process exits.
- `chronicle-sdk`: the `chronicle` CLI (`chronicle start`/`stop`/`status`/
  `open`), registered as a console script (`sdk/src/chronicle/cli.py`,
  `pyproject.toml`'s `[project.scripts]`). `start` runs the server in the
  foreground; `stop` reads the pid file `ServerManager` writes and sends
  `SIGTERM`; `status` reports whether `GET /health` responds; `open`
  best-effort launches the desktop app by trying a few platform-specific
  commands.
- `chronicle-sdk`: `chronicle.adapters.openai_agents.ChronicleAgentHooks` —
  a duck-typed OpenAI Agents SDK hooks object (`on_agent_start`/
  `on_agent_end`/`on_tool_call`/`on_tool_result`/`on_handoff`), recorded as
  `agent_message`/`tool_call` events (discriminated by `data["event"]`)
  rather than introducing new server-side event types.
- `chronicle-sdk`: `chronicle.adapters.pydanticai.ChronicleMiddleware` — wraps
  a PydanticAI `Agent`'s `run_sync()`, capturing model name, prompt,
  response, tool calls (via `ToolCallPart` introspection), token usage,
  duration, and errors as one `llm_call`/`error` event per call. Async
  `run`/`run_stream` pass through unwrapped (see `KNOWN_ISSUES.md`).
- README: quickstart reduced to `pip install chronicle-sdk` +
  `chronicle.instrument(graph)`; added a Framework support table
  (LangGraph/OpenAI Agents SDK/PydanticAI supported, CrewAI/AutoGen
  planned for v0.4.0).

### Changed

- README: quickstart no longer shows manual `ChronicleTracer`/
  `LangGraphAdapter` wiring as the primary path (still available, and
  still exercised directly in `Getting started (development)`) — the
  one-line `chronicle.instrument()` API is now the documented entry point.

## [0.2.0] - 2026-07-02

### Added

- `chronicle-sdk`: `chronicle.models.StateSnapshot` and
  `ChronicleTracer.record_snapshot()`, for the future replay engine.
  Snapshots ship to `POST /snapshots` on a background `threading.Thread`
  (never blocking the agent), falling back to
  `chronicle_runs/{run_id}_snapshots.json` if the server is unreachable.
  `LangGraphAdapter` now captures a snapshot after every `on_chain_end` and
  `on_agent_finish`, with a new `_json_safe()` helper that recursively
  converts non-JSON-serializable graph-state values to strings (flagging
  `metadata["_serialization_warning"]`) instead of crashing the agent.
- `chronicle-server`: a `snapshots` table (indexed on `run_id` and
  `step_index`) and a write-only `POST /snapshots` endpoint accepting a
  batch of snapshots; `DELETE /runs/{id}` now also deletes the run's
  snapshots.
- `chronicle-server`: the replay engine. `GET /runs/{id}/snapshots` (summary,
  step-ordered) and `GET /runs/{id}/snapshots/{snapshot_id}` (full detail).
  `server/src/registry.py`'s `GraphRegistry` + `POST /register` /
  `GET /registry` register a LangGraph graph by `{graph_module, graph_attr}`
  — imported, never pickled. `server/src/replay.py`'s `ReplayEngine` +
  `POST /replay` load a snapshot, apply `modifications` to its
  `graph_state`, and schedule the re-invocation as a `BackgroundTasks` job
  (so the response returns a new `run_id` immediately); the replayed graph
  is instrumented with `chronicle-sdk`'s own `ChronicleTracer`/
  `LangGraphAdapter`, stamping `runs.metadata` with `{is_replay: true,
  source_run_id, source_snapshot_id, step_index}` and a final
  `"complete"`/`"failed"` status via two new `Database` methods
  (`set_run_metadata`, `set_run_status`). `chronicle-sdk` is now an
  optional runtime dependency of `chronicle-server` (lazily imported; CI's
  `server-tests` job installs both).
- `chronicle-sdk`: `ChronicleTracer.register_graph()` (`POST /register`,
  module-path only, never pickled) and auto-registration via
  `LangGraphAdapter(tracer, graph=, graph_module=, graph_attr=)`.
- `chronicle-app`: the replay UI. Hovering a timeline segment that has a
  captured snapshot (`Timeline.tsx` fetches `GET /runs/{id}/snapshots` and
  matches on `event_id`) shows a floating "Replay from here" button
  (`TimelineChart.tsx`'s `mouseover`/`mouseout` on the series, with a short
  hide delay so the cursor can reach the button before it disappears).
  Clicking it opens `app/src/components/Replay/ReplayModal.tsx`: step
  index/timestamp/agent name/graph-state summary from `GET
  /runs/{id}/snapshots/{snapshot_id}`, an optional JSON "Modifications"
  textarea, and "Replay as-is"/"Replay with modifications" buttons that call
  `POST /replay` and poll `GET /runs` for the new run to leave `"running"`
  (`REPLAY_POLL_INTERVAL_MS`/`REPLAY_POLL_TIMEOUT_MS`), showing "Replaying
  from step N..." meanwhile. `RunList.tsx` shows a purple `REPLAY` badge
  (tooltip: source run + step) for any run whose metadata has `is_replay:
  true`, via the new `getReplayMetadata()` helper in `app/src/types`. New
  `useAppStore` fields `diffPrefill`/`toast` (plus a new `Toast.tsx`
  component) wire the modal's completion to the rest of the app: on success
  it selects the new run and shows a toast — "Replay complete. Compare with
  original?" — whose action sets `diffPrefill` and switches to the Diff tab
  with Run A/B pre-filled to the original/replay run, consumed once by
  `Diff.tsx` and cleared.

### Fixed

- `chronicle-sdk`: `ChronicleTracer.flush()` was POSTing a bare event object
  to `/events` (`json=event.to_dict()`) instead of the single-item list the
  server's `list[EventIn]` body expects — every real (non-fallback) event
  delivery would have 422'd. Found while touching `tracer.py` for this
  phase; no prior test caught it since every SDK test points at an
  unreachable server. Fixed to `json=[event.to_dict()]`.

## [0.1.0] - 2026-07-02

First public release. Chronicle instruments a LangGraph agent, ships trace
events to a local FastAPI server, and gives you a Tauri desktop app to browse
runs, replay the execution timeline, inspect individual events/agents/tools,
and diff two runs against each other.

### Summary

- **`chronicle-sdk`**: `ChronicleTracer` captures `tool_call`/`llm_call`/
  `agent_message`/`memory_update`/`error`/`retry` events, batches them to the
  server over HTTP, and falls back to `chronicle_runs/{run_id}.json` when the
  server isn't reachable. `LangGraphAdapter` instruments a LangGraph/LangChain
  graph's callbacks automatically, capturing duration and token usage.
- **`chronicle-server`**: FastAPI + SQLite (`aiosqlite`) app exposing
  `POST /events`, `GET /runs`, `GET /runs/{id}/events`,
  `GET /runs/{id}/timeline`, and `DELETE /runs/{id}`, with run-level stats
  (tokens, agent count, status) recomputed from events on every write and a
  consistent `{error, detail}` error shape.
- **`chronicle-app`**: a Tauri + React + TypeScript desktop app with a run
  sidebar, an ECharts-based execution timeline (per-agent lanes, colored
  segments, zoom/filter, token/cost summary), an Event/Agent/Tools inspector,
  and a run-to-run diff view (summary deltas, positional event diff,
  character-level prompt diff). The app starts/stops the local server
  automatically and shows a human-readable banner if that fails.
- Security: server CORS restricted to the Tauri dev origin, no secrets in the
  repo or bundles, production builds strip `console.*`/`debugger`.
- CI runs Python tests for `/sdk` and `/server` and TypeScript type-checking
  plus Vitest for `/app` on every push; a tag-triggered release workflow
  builds the desktop app for Windows/macOS/Linux and the `chronicle-sdk`
  wheel.

The detailed phase-by-phase history below has the full list of changes.

### Added

- Initial monorepo scaffold: `/sdk` (chronicle-sdk Python package), `/server`
  (FastAPI server), `/app` (Tauri + React + TypeScript desktop app), `/docs`.
- `chronicle-sdk`: `ChronicleTracer`, event schemas (`tool_call`, `llm_call`,
  `agent_message`, `memory_update`, `error`, `retry`), local SQLite fallback
  storage, and a LangGraph/LangChain callback handler.
- `chronicle-server`: FastAPI app with `POST /events`, `GET /runs`,
  `GET /runs/{id}/events`, `GET /runs/{id}/timeline`, `DELETE /runs/{id}`,
  backed by SQLite via `aiosqlite`.
- `chronicle-app`: Tauri desktop shell with a run sidebar, event timeline, and
  event inspector panel.
- CI workflow running Python tests for `/sdk` and `/server`, and TypeScript
  type-checking plus Vitest for `/app`.

### Changed

- `chronicle-sdk`: reworked the event model into
  `chronicle.models.ChronicleEvent`/`TokenUsage` dataclasses
  (`event_id`/`data`/`agent_name`/`duration_ms`/`token_usage`/`error`).
  `ChronicleTracer` now exposes `record_event()`/`flush()`, buffers events,
  and flushes them to the server in batches, falling back to
  `chronicle_runs/{run_id}.json` (instead of a local SQLite database) when
  the server is unreachable. Replaced the LangChain callback handler with
  `chronicle.adapters.langgraph.LangGraphAdapter`, which adds
  `on_agent_finish` handling and captures per-call duration and token usage.
  Requires Python 3.10+.
- `chronicle-server`: rebuilt as a flat `src` package (`uvicorn src.main:app`)
  matching the Phase 2 SDK event model end-to-end. `POST /events` now
  accepts a batch of events and stores `event_id`/`data`/`agent_name`/
  `duration_ms`/`input_tokens`/`output_tokens`/`error`. Added `runs` summary
  columns (`framework`, `agent_count`, `total_tokens`, `total_cost_usd`,
  `status`, `metadata`), recomputed from `events` on every write. Added
  `server/src/timeline.py`, which shapes `GET /runs/{id}/timeline` into
  per-agent lanes of `llm_call`/`tool_call`/`waiting`/`error` segments.
  Moved the default port to `7823` (was `8765`) and restricted CORS to
  `http://localhost:1420`. All error responses are now shaped
  `{error, detail}`. Requires Python 3.10+.
- `chronicle-app`: rebuilt as a three-panel layout — top nav (brand, panel
  switcher tabs, connection-status dot, settings icon), a `RunList` sidebar
  polling `GET /runs` every `RUN_LIST_POLL_INTERVAL_MS`, a `MainPanel` with
  Timeline/Inspector/Diff tabs, and a collapsible `DetailInspector`. Added a
  Zustand store (`useAppStore`) for `runs`/`selectedRunId`/`loading`/`error`/
  `activePanel`/`selectedDetail`. Rewrote `app/src/types/index.ts` and
  `app/src/api/client.ts` to match the Phase 3 server response shapes
  field-for-field, with `AbortController`-based 5s timeouts and
  `{error, detail}`-aware human-readable error messages. Added
  `start_chronicle_server`/`stop_chronicle_server` Tauri commands
  (`app/src-tauri/src/lib.rs`) that spawn/kill the Chronicle server as a
  child process on app launch/exit, surfacing startup failures as a UI
  banner via a `chronicle-server-error` event — not a bundled Tauri
  sidecar binary (see `KNOWN_ISSUES.md`).
- `chronicle-server`/`chronicle-app`: added `retry` as a fourth timeline
  segment type end-to-end (`server/src/timeline.py`, `server/src/models.py`,
  `app/src/types`) so retries render instead of being silently dropped.
- `chronicle-app`: replaced the flat `TimelinePanel` event list with
  `app/src/components/Timeline/` — an ECharts `custom`-series swimlane
  chart (`TimelineChart.tsx`, one lane per agent, colored
  `llm_call`/`tool_call`/`waiting`/`error`/`retry` segments, hover
  tooltips, click-to-inspect), a `TokenUsageSummary` bar (total
  input/output tokens and an estimated cost via configurable
  `COST_PER_INPUT_TOKEN_USD`/`COST_PER_OUTPUT_TOKEN_USD` constants), and
  `TimelineControls` (zoom in/out/fit, an all/llm/tools/errors filter).
  Loading shows skeleton lane bars; a run with no segments shows "No events
  recorded for this run."; fetch failures show a human-readable message
  with a Retry button. Added `echarts` as a dependency.
- `chronicle-server`: added `event_id` to `GET /runs/{id}/timeline` segments
  (`server/src/timeline.py`, `server/src/models.py`) so the app can resolve
  a clicked segment back to its full event.
- `chronicle-app`: rebuilt the right panel as `app/src/components/Inspector/`
  with an Event/Agent/Tools tab bar that preserves each tab's last selection
  independently (`useAppStore`'s `inspectorTab`/`selectedAgentName`/
  `selectedToolName`). `EventInspector.tsx` shows full detail per event type
  (prompt/response for `llm_call`, arguments/result/status for `tool_call`,
  message/traceback/agent for `error`). Clicking an agent's lane header in
  the Timeline chart (new `TimelineChart` `yAxis` `triggerEvent` +
  `onAgentSelect`) opens `AgentInspector.tsx` (call counts, tokens, errors,
  average LLM latency, tool usage). `ToolInspector.tsx` lists every tool
  used in the run with success rate/latency/tokens and an expandable
  per-call list. Both are computed by pure functions in
  `Inspector/summarize.ts`. Removed `DetailInspector.tsx` (superseded).
- `chronicle-app`: replaced the Diff tab's placeholder with
  `app/src/components/Diff/`. `RunSelector.tsx` offers two dropdowns (each
  disables the other's current selection). `DiffSummary.tsx` compares total
  duration/tokens/cost/errors/tool calls side by side, coloring the B-minus-A
  delta green (improvement) or red (regression). `EventDiffList.tsx` diffs
  both runs' events by sequence position — same rows unhighlighted,
  differing-field rows yellow, rows missing from one side red — and
  `PromptDiff.tsx` renders a character-level diff (via the new `diff`
  dependency's `diffChars`) of same-position `llm_call` prompts. All
  diffing runs client-side in `computeDiff.ts`; a pair of runs where either
  side has more than 500 events shows a warning banner but still renders in
  full. Removed `panels/DiffPanel.tsx` (superseded).
- Release prep: unified `chronicle-sdk`, `chronicle-server`, `chronicle-app`,
  and the Tauri bundle at version `0.1.0`. Added `.github/workflows/release.yml`
  (tag-triggered, builds Windows/macOS/Linux Tauri bundles plus the
  `chronicle-sdk` wheel and uploads both to a GitHub Release). Configured
  `vite.config.ts` to strip `console.*`/`debugger` from production builds.
