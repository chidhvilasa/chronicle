# Known Issues

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
- **Timeline segments only cover `llm_call`/`tool_call`/`error`**:
  `agent_message`, `memory_update`, and `retry` events are not represented
  as segments in `GET /runs/{id}/timeline` yet — they're silently omitted
  from the per-agent lanes (see `server/src/timeline.py`).
- **Local JSON fallback is not concurrency-safe**: when the SDK falls back
  to writing `chronicle_runs/{run_id}.json` (server not running), it does a
  read-modify-write of the whole file. Multiple processes writing to the
  same `run_id` concurrently can race and drop events. Fine for local,
  single-process development; not safe for concurrent writers.
- **No schema migrations yet**: The server's SQLite schema is created with
  `CREATE TABLE IF NOT EXISTS` and has no migration system. Schema changes
  between versions may require deleting the local database file.

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
- **Timeline segments aren't individually addressable**: `GET
  /runs/{id}/timeline` segments don't carry an `event_id` (see
  `server/src/timeline.py`), so clicking a segment in the Timeline tab shows
  its own label/duration/token usage in the detail inspector, but can't look
  up the original event's full payload the way clicking a row in the
  Inspector tab can.
- **Diff tab is a placeholder**: run-to-run diffing is planned for a later
  phase (see `CHRONICLE_PLAN.md`); the "Diff" tab currently just says so.
- **Settings icon has no functionality yet**: it's present in the top nav
  per this phase's spec but doesn't open anything.

This list will grow as the project matures. If you hit something not listed
here, please open an issue.
