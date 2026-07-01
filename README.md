# Chronicle

[![CI](https://github.com/chidhvilasa/chronicle/actions/workflows/ci.yml/badge.svg)](https://github.com/chidhvilasa/chronicle/actions/workflows/ci.yml)

**Chronicle is the Chrome DevTools for AI agents.**

An open source engineering platform for debugging, profiling, replaying, and
understanding AI agent systems. Instrument your agent with the Python SDK,
run the local server, and inspect every tool call, LLM call, message, memory
update, error, and retry in a desktop app.

## Architecture

```
┌─────────────┐   HTTP   ┌──────────────┐   REST   ┌─────────────┐
│  Python SDK │ ───────▶ │ FastAPI      │ ◀──────── │ Tauri App   │
│ (your agent)│          │ Server       │           │ (React/TS)  │
└─────────────┘          │ (SQLite)     │           └─────────────┘
                         └──────────────┘
```

- **`/sdk`** — `chronicle-sdk`, a Python package agents import to emit trace
  events. Buffers and ships events to the local Chronicle server over HTTP in
  batches; falls back to writing unsent events to
  `chronicle_runs/{run_id}.json` if the server isn't running.
- **`/server`** — A FastAPI server that stores events in SQLite and serves
  them to the desktop app over REST.
- **`/app`** — A Tauri + React + TypeScript desktop app for browsing runs,
  timelines, and event payloads.
- **`/docs`** — Documentation.

See [CHRONICLE_PLAN.md](./CHRONICLE_PLAN.md) for the full design and
phase-by-phase roadmap.

## Getting started

### SDK

```bash
cd sdk
pip install -e ".[dev]"
pytest
```

```python
from chronicle import ChronicleTracer

with ChronicleTracer() as tracer:
    tracer.record_event("tool_call", data={"tool_name": "search", "arguments": {"query": "weather in nyc"}})
```

### Server

```bash
cd server
pip install -e ".[dev]"
uvicorn src.main:app --host 127.0.0.1 --port 7823 --reload
```

### App

```bash
cd app
npm install
npm run tauri dev
```

## Project status

Chronicle is early and under active development. See
[KNOWN_ISSUES.md](./KNOWN_ISSUES.md) for current constraints and
[CHANGELOG.md](./CHANGELOG.md) for what's shipped so far.

## Security

See [SECURITY.md](./SECURITY.md) for how to report vulnerabilities and the
security model of the local server.

## License

MIT
