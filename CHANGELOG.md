# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
