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
- **SQLite fallback is single-writer**: When the SDK falls back to writing
  directly to the local SQLite file (server not running), concurrent writes
  from multiple processes to the same file may block briefly under SQLite's
  file-locking model. This is acceptable for local development but not a
  concurrent-write-optimized design.
- **No schema migrations yet**: The SQLite schema is created with
  `CREATE TABLE IF NOT EXISTS` and has no migration system. Schema changes
  between versions may require deleting the local database file.

This list will grow as the project matures. If you hit something not listed
here, please open an issue.
