# Known Issues

## v0.3.0 scope

- **Auto server startup requires `uvicorn` in the same Python environment**:
  `chronicle.instrument()`/`ServerManager.ensure_running()` spawns `python
  -m uvicorn src.main:app`, which only works if `chronicle-server` (and its
  `uvicorn` dependency) is installed in the same Python environment as the
  agent process. If it isn't, the subprocess fails to spawn and Chronicle
  falls back to writing `chronicle_runs/*.json` locally — tracing still
  works, just without the server/desktop app until it's installed and
  started (`pip install chronicle-server` or `chronicle start`).
- **`chronicle open` requires the desktop app to be installed separately**:
  the CLI's `open` command tries a few platform-specific launch commands
  (`chronicle-app`, `open -a Chronicle`, `cmd /c start Chronicle`) but has
  no way to install the app itself — see [Download](./README.md#download)
  for the desktop app installers. On macOS in particular, `open -a
  Chronicle` can appear to succeed (the `open` binary launches
  successfully) even when the app isn't installed, since that failure
  happens asynchronously after the CLI has already returned.
- **PydanticAI middleware wraps synchronous runs only, async support in
  v0.4.0**: `chronicle.adapters.pydanticai.ChronicleMiddleware` only
  instruments `run_sync()`. Async `run()`/`run_stream()` calls pass
  straight through to the wrapped agent unwrapped, via `__getattr__` — a
  PydanticAI agent driven only through `await agent.run(...)` won't
  produce any Chronicle events yet.
- **Replay requires graph registered via `tracer.register_graph()`**:
  `POST /replay` 400s with "No graph registered. Call
  tracer.register_graph() before replaying." if nothing has been
  registered in the current server process. There's also only ever one
  "active" registered graph — the most recently registered one — so a
  server tracing multiple distinct agents at once can only replay
  whichever was registered last.
- **Replay does not support agents with external side effects (DB writes,
  real API calls) without user caution**: `ReplayEngine` just calls
  `graph.invoke()` again. If the original run's tools made real API calls,
  sent messages, or wrote to a database, replaying it will do those things
  again — there's no dry-run mode or side-effect detection. Only replay
  runs you're comfortable re-executing for real.
- **Modifications editor is plain JSON, no schema validation yet**: the
  Replay modal's "Modifications" field is a plain textarea that's parsed
  as JSON client-side (rejecting malformed JSON before submitting), but
  there's no check that the keys/shapes make sense for the target graph's
  state schema — a bad modification just surfaces as whatever error the
  graph itself raises, and the replay run is marked `"failed"`.
- **CrewAI and AutoGen adapters are not available yet**: `chronicle-sdk`
  ships adapters for LangGraph, OpenAI Agents SDK, and PydanticAI (see the
  README's Framework support table). CrewAI/AutoGen are planned for
  v0.4.0; instrumenting agents built on those frameworks today requires
  calling `ChronicleTracer.record_event()` directly rather than
  `chronicle.instrument()`.
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
- **`chronicle-server` now has an optional runtime dependency on
  `chronicle-sdk` (as of Phase 10)**: `server/src/replay.py` imports
  `chronicle` to instrument replayed runs. It's a lazy import (guarded by
  `try/except ImportError`, marking the replay run `"failed"` rather than
  crashing the server), but both packages must be installed in the same
  Python environment for replay to actually work — `pip install -e ./sdk`
  alongside `pip install -e ./server`. CI's `server-tests` job does this;
  a from-source deployment needs to as well.
- **Replay's "invoke or stream" choice always uses `.invoke()` (as of Phase
  10)**: the Phase 10 spec calls for detecting whether the original run
  used `graph.invoke()` or `graph.stream()` (from run metadata) and
  matching it, but nothing currently records which one a live run used, so
  `ReplayEngine` always calls `.invoke()`.
- **Replay modifications are a shallow overlay on `graph_state` (as of
  Phase 10)**: `ReplayEngine` does `dict.update(modifications)` — a
  modification key replaces that key's entire value. There's no deep-merge
  for nested structures (e.g. overriding one message in a `messages` list
  requires supplying the whole new list).
- **No schema validation on replay `modifications` (as of Phase 10)**:
  `POST /replay`'s `modifications` field accepts any JSON object; there's
  no check that the keys/shapes make sense for the target graph's state
  schema before invoking it. A bad modification just surfaces as whatever
  error the graph itself raises, and the replay run is marked `"failed"`.

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
