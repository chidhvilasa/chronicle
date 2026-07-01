# chronicle-server

Local FastAPI server for [Chronicle](../README.md). Receives agent trace
events from the Python SDK, stores them in SQLite, and serves them to the
Tauri desktop app.

## Install

```bash
pip install -e ".[dev]"
```

## Run

```bash
uvicorn chronicle_server.main:app --host 127.0.0.1 --port 8765 --reload
```

## Endpoints

| Method | Path                     | Description                     |
| ------ | ------------------------ | -------------------------------- |
| GET    | `/health`                | Liveness check                   |
| POST   | `/events`                | Ingest a trace event              |
| GET    | `/runs`                  | List all runs                    |
| GET    | `/runs/{id}/events`      | List events for a run             |
| GET    | `/runs/{id}/timeline`    | Chronological timeline for a run  |
| DELETE | `/runs/{id}`             | Delete a run and its events       |

## Development

```bash
pytest
```
