# Known Issues

## v0.1.0 scope

- **Replay engine is not implemented yet**: as of Phase 9, `chronicle-sdk`
  captures the state snapshots a replay engine would need (see "State
  snapshots" below), and the server stores them, but there is still no
  step-by-step "replay" of a captured run — no query endpoint to read
  snapshots back, and no UI to re-execute or step through an agent's saved
  states. See `CHRONICLE_PLAN.md`'s Phase 10; this is planned future work.
- **Only a LangGraph/LangChain adapter is available**: `chronicle-sdk` ships
  `chronicle.adapters.langgraph.LangGraphAdapter`. There is no CrewAI or
  AutoGen adapter yet — instrumenting agents built on those frameworks
  requires calling `ChronicleTracer.record_event()` directly rather than an
  automatic callback integration.
- **The desktop app doesn't bundle the server as a real sidecar**: see
  "The Chronicle server is not a real bundled Tauri sidecar" below for the
  full explanation and the documented workaround.

## Platform / build constraints

- **Tauri/Rust system dependencies**: Building `/app` requires the Rust
  toolchain plus the platform WebView dependencies Tauri needs (WebView2 on
  Windows, WebKitGTK on Linux, or the system WebView on macOS). CI installs
  these explicitly; local contributors need them too. See
  https://tauri.app/start/prerequisites/ for the current list per OS.
- **First `npm run tauri dev` is slow**: The initial Rust build compiles all
  Tauri crates from scratch and can take several minutes. Subsequent builds
  are incremental and much faster.

## SDK / server

- **No authentication**: The Chronicle server has no auth layer. It's meant
  to run on `127.0.0.1` alongside the agent process being traced (see
  `SECURITY.md`).
- **The server's default port changed to `7823`** (from `8765` in Phases
  1–2) to match this phase's spec; `chronicle-sdk`'s
  `ChronicleTracer.DEFAULT_SERVER_URL` and the app's
  `DEFAULT_SERVER_URL` were both updated to match.
- **`runs.status` has no "completed" state yet**: a run's `status` is
  `'error'` if any of its events are `error` events, otherwise `'running'`
  forever — there's no explicit "run finished" event/signal yet, so a
  completed-but-error-free run still reports `status: "running"`.
- **Timeline segments only cover `llm_call`/`tool_call`/`retry`/`error`**:
  `agent_message` and `memory_update` events are not represented as
  segments in `GET /runs/{id}/timeline` yet — they're silently omitted
  from the per-agent lanes (see `server/src/timeline.py`).
- **Local JSON fallback is not concurrency-safe**: when the SDK falls back
  to writing `chronicle_runs/{run_id}.json` (server not running), it does a
  read-modify-write of the whole file. Multiple processes writing to the
  same `run_id` concurrently can race and drop events. Fine for local,
  single-process development; not safe for concurrent writers.
- **No schema migrations yet**: The server's SQLite schema is created with
  `CREATE TABLE IF NOT EXISTS` and has no migration system. Schema changes
  between versions may require deleting the local database file.
- **`POST /snapshots` has no read counterpart yet (as of Phase 9)**: the
  `snapshots` table fills up, but there's no `GET /runs/{id}/snapshots` or
  similar to read them back — nothing in the server or app can query
  captured state snapshots yet. That's Phase 10, alongside the replay
  engine itself.
- **State snapshots are not concurrency-safe locally, and can be lost on
  process exit (as of Phase 9)**: `ChronicleTracer.record_snapshot()` ships
  each snapshot on its own daemon `threading.Thread`, guarded by a lock only
  around the local-file fallback write (not the HTTP attempt). If the
  process exits immediately after the last snapshot is captured, that
  thread may not finish before the interpreter shuts down, and the snapshot
  can be silently dropped. `ChronicleTracer.close()` does not wait for
  outstanding snapshot threads — only for buffered events.
- **Graph-state extraction assumes the LangGraph convention of
  `state["messages"]`/`state["tool_results"]` (as of Phase 9)**: the
  LangGraph adapter's snapshot capture looks for those two keys specifically
  and defaults to `[]` if they're missing or not lists. A graph state that
  keeps messages/tool results under different keys will still be captured
  in full inside `graph_state`, but `StateSnapshot.messages`/`tool_results`
  will be empty.

## App

- **The Chronicle server is not a real bundled Tauri sidecar (as of Phase
  4)**: `app/src-tauri/src/lib.rs`'s `start_chronicle_server`/
  `stop_chronicle_server` commands shell out to `python -m uvicorn
  src.main:app` in the sibling `/server` checkout (`../../server` relative
  to `src-tauri`) as a plain child process on app launch, and kill it on
  exit. This is **not** a PyInstaller-bundled binary declared via
  `tauri.conf.json`'s `bundle.externalBin` / `tauri-plugin-shell`'s sidecar
  API — building and cross-compiling a standalone `chronicle-server`
  executable per platform is future work. Practical implications:
  - Requires `python` on `PATH` and `chronicle-server` installed in that
    Python environment (`pip install -e .` in `/server`).
  - The relative path to `/server` only resolves in a dev checkout; it will
    not resolve inside a packaged/distributed app bundle.
  - If auto-start fails for any reason, the app emits
    `chronicle-server-error` and shows the message as a banner (see
    `app/src/hooks/useServerStartupError.ts`) — but per this phase's spec,
    the app still works if you start the server yourself
    (`cd server && uvicorn src.main:app --port 7823`) and just let the app
    connect to `http://127.0.0.1:7823` like any other client.
- **Settings icon has no functionality yet**: it's present in the top nav
  per this phase's spec but doesn't open anything.
- **Token cost estimate is a flat-rate approximation (as of Phase 5)**: the
  timeline's `TokenUsageSummary` multiplies token counts by fixed
  `COST_PER_INPUT_TOKEN_USD`/`COST_PER_OUTPUT_TOKEN_USD` constants
  (`app/src/config`), not the real pricing of whichever model actually
  produced the tokens — it's a rough ballpark, not an accurate bill.
- **Timeline zoom is a fixed step, not free drag-zoom**: the zoom in/out/fit
  buttons dispatch a centered ECharts `dataZoom` window based on a
  multiplier (`TIMELINE_ZOOM_STEP`/`TIMELINE_MAX_ZOOM`); mouse-wheel zoom on
  the chart itself works too (ECharts' built-in `inside` `dataZoom`), but
  there's no click-drag-to-select-range zoom UI yet.
- **echarts is bundled in full**: `TimelineChart.tsx` does
  `import * as echarts from "echarts"` rather than the tree-shaken
  `echarts/core` + explicit chart/component imports, so the production
  bundle includes chart types Chronicle doesn't use. `npm run build` warns
  about the resulting >500kB chunk. Fine for a desktop app; worth trimming
  if `/app` ever ships as a web build.
- **No real syntax highlighting (as of Phase 6)**: the Inspector's Event tab
  renders LLM prompts/responses and tool call JSON in a plain scrollable
  monospace `<pre>` (`.code-block`), not a tokenized/highlighted code view —
  no highlighting library was added. Readable, but not colorized.
- **Agent/tool summaries treat "success" as "no `error` field" (as of Phase
  6)**: `Inspector/summarize.ts` counts a `tool_call` as failed only when
  the event's top-level `error` field is set; it doesn't inspect
  `data.success` or similar SDK-side conventions, since the event schema
  doesn't guarantee that shape. A tool that "succeeds" at the transport
  level but reports failure only inside `data` will be counted as a
  success.
- **Execution diff is positional, not content-aligned (as of Phase 7)**:
  `Diff/computeDiff.ts`'s `buildEventDiffRows` zips both runs' events by
  index — event 5 in Run A is always compared to event 5 in Run B. If one
  run has one extra event early on (e.g. an extra retry), every later event
  shifts by one position and shows up as "different" or "missing" even
  though the same logical steps occurred, just offset. A real sequence
  alignment (like a text diff's LCS) would handle insertions/deletions more
  gracefully; this is simpler and matches the phase's "diff by sequence
  position" spec.
- **Prompt diff only reads `data.prompt` (as of Phase 7)**: `PromptDiff`
  compares `event.data.prompt` for same-position `llm_call` events on both
  sides; if a value isn't a string there (or is stored under a different
  key), it's treated as an empty prompt rather than diffed.
- **Diff summary's delta coloring applies uniformly to tool-call count**:
  `DiffSummary.tsx` colors every stat's B-minus-A delta green when B is
  lower, red when higher — including "Total tool calls," where fewer calls
  isn't necessarily better. Kept for visual consistency across the table
  rather than special-casing that one row.

This list will grow as the project matures. If you hit something not listed
here, please open an issue.
