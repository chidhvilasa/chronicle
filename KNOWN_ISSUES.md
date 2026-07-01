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
- **App/server schema drift (as of Phase 3)**: `chronicle-server`'s
  `POST /events` and the rest of its endpoints now match the Phase 2 SDK
  event model (`event_id`/`data`/`agent_name`/`duration_ms`/`input_tokens`/
  `output_tokens`/`error`, plus the new `runs` summary columns and the
  `/runs/{id}/timeline` lane/segment shape). The desktop app
  (`app/src/types.ts`, `app/src/api/client.ts`) has *not* been updated yet
  and still models the Phase 1 response shape (`id`/`payload`/`parent_id`,
  `ChronicleRun.event_count`). The app will not render real server
  responses correctly until Phase 4 updates it.
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

This list will grow as the project matures. If you hit something not listed
here, please open an issue.
