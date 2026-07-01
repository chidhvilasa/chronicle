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
- **SDK/server event schema drift (as of Phase 2)**: `chronicle-sdk`'s
  `ChronicleTracer` now buffers and POSTs events shaped like
  `chronicle.models.ChronicleEvent` (`event_id`, `data`, `agent_name`,
  `duration_ms`, `token_usage`, `error`), but `chronicle-server`'s
  `POST /events` still validates against the Phase 1 shape (`id`,
  `payload`, `parent_id`). Until Phase 3 reconciles the two schemas, a
  running server will reject events from the current SDK with a 422 and
  every event will fall through to the local `chronicle_runs/{run_id}.json`
  fallback instead.
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
