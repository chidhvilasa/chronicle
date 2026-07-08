//! Tauri backend: starts the local Chronicle FastAPI server as a child
//! process when the app launches, and stops it when the app exits.
//!
//! This shells out to `python -m uvicorn` rather than using a bundled Tauri
//! sidecar binary (see KNOWN_ISSUES.md for why, and the documented fallback:
//! run `chronicle-server` yourself and the app will still work by connecting
//! to `localhost:7823` over HTTP either way).

use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::{AppHandle, Emitter, Manager, RunEvent, State};

const SERVER_HOST: &str = "127.0.0.1";
const SERVER_PORT: &str = "7823";
const SERVER_ERROR_EVENT: &str = "chronicle-server-error";

/// Holds the handle to the spawned Chronicle server child process, if any.
pub struct ServerState(Mutex<Option<Child>>);

impl ServerState {
    fn new() -> Self {
        ServerState(Mutex::new(None))
    }
}

/// Locates the sibling `/server` checkout this app expects to run next to in
/// development. Does not resolve inside a packaged app bundle.
fn server_dir() -> Option<PathBuf> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir.join("..").join("..").join("server").canonicalize().ok()
}

fn spawn_server_process() -> Result<Child, String> {
    let dir = server_dir().ok_or_else(|| {
        "Could not locate the Chronicle server directory next to the app.".to_string()
    })?;

    Command::new("python")
        .args([
            "-m",
            "uvicorn",
            "src.main:app",
            "--host",
            SERVER_HOST,
            "--port",
            SERVER_PORT,
        ])
        .current_dir(&dir)
        .spawn()
        .map_err(|err| {
            format!(
                "Could not start the Chronicle server automatically ({err}). \
                 Make sure Python and chronicle-server are installed \
                 (`pip install -e .` in /server), or start it yourself with \
                 `uvicorn src.main:app --port 7823` — the app will still \
                 connect once it's running."
            )
        })
}

/// Starts the Chronicle server if it isn't already running. Emits
/// `chronicle-server-error` with a human-readable message on failure.
#[tauri::command]
fn start_chronicle_server(app: AppHandle, state: State<ServerState>) -> Result<(), String> {
    let mut guard = state
        .0
        .lock()
        .map_err(|_| "Chronicle server state lock was poisoned.".to_string())?;

    if guard.is_some() {
        return Ok(());
    }

    match spawn_server_process() {
        Ok(child) => {
            *guard = Some(child);
            Ok(())
        }
        Err(message) => {
            let _ = app.emit(SERVER_ERROR_EVENT, message.clone());
            Err(message)
        }
    }
}

/// Stops the Chronicle server child process if one is running.
#[tauri::command]
fn stop_chronicle_server(state: State<ServerState>) -> Result<(), String> {
    let mut guard = state
        .0
        .lock()
        .map_err(|_| "Chronicle server state lock was poisoned.".to_string())?;

    if let Some(mut child) = guard.take() {
        child
            .kill()
            .map_err(|err| format!("Could not stop the Chronicle server: {err}"))?;
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(ServerState::new())
        .invoke_handler(tauri::generate_handler![start_chronicle_server, stop_chronicle_server])
        .setup(|app| {
            let handle = app.handle().clone();
            let state = handle.state::<ServerState>();
            if let Err(message) = start_chronicle_server(handle.clone(), state) {
                eprintln!("Chronicle server failed to start: {message}");
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::ExitRequested { .. } = event {
            let state = app_handle.state::<ServerState>();
            let _ = stop_chronicle_server(state);
        }
    });
}
