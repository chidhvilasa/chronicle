# chronicle-server

Local FastAPI server for [Chronicle](../README.md). Receives batches of agent
trace events from the Python SDK, stores them in SQLite, and serves runs,
events, and per-agent timelines to the Tauri desktop app.

## Install

```bash
pip install -e ".[dev]"
```

## Run

```bash
uvicorn src.main:app --host 127.0.0.1 --port 7823 --reload
```

The server listens on `127.0.0.1:7823` by default and only accepts CORS
requests from `http://localhost:1420` (the Tauri dev server).

## Endpoints

| Method | Path                     | Description                                       |
| ------ | ------------------------ | -------------------------------------------------- |
| GET    | `/health`                | Liveness check; returns `{status, version}`         |
| POST   | `/events`                | Ingest a batch of events (up to hundreds at once)   |
| GET    | `/runs`                  | List all runs, newest first, with summary stats     |
| GET    | `/runs/{id}/events`      | List all events for a run, chronological            |
| GET    | `/runs/{id}/timeline`    | Per-agent lanes of llm_call/tool_call/waiting/error segments |
| DELETE | `/runs/{id}`             | Delete a run and its events                          |

Every error response (404, 422, etc.) has the shape
`{"error": "<short_code>", "detail": "<human-readable message>"}`.

## Storage

SQLite via `aiosqlite`, with two tables: `runs` (aggregate stats, recomputed
from `events` on every write) and `events` (the full event log). See
`src/database.py`.

## Development

```bash
pytest
```
