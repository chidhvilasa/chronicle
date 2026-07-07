# Chronicle

[![CI](https://github.com/chidhvilasa/chronicle/actions/workflows/ci.yml/badge.svg)](https://github.com/chidhvilasa/chronicle/actions/workflows/ci.yml)

**Chronicle is the Chrome DevTools for AI agents.**

An open source engineering platform for debugging, profiling, replaying, and
understanding AI agent systems. Instrument your agent with the Python SDK,
run the local server, and inspect every tool call, LLM call, message, memory
update, error, and retry in a desktop app.

## Screenshots

> Chronicle is under active development; the images below are placeholders
> until real screenshots are captured from a built release.

| Execution timeline | Agent & tool inspector |
| --- | --- |
| ![Execution timeline placeholder](https://placehold.co/640x400?text=Timeline+view) | ![Inspector placeholder](https://placehold.co/640x400?text=Inspector+view) |

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

## Quickstart

```bash
pip install chronicle-sdk
```

Then in your agent file add one line:

```python
import chronicle
graph = chronicle.instrument(graph)
```

Open the Chronicle desktop app. Run your agent. That is it.

## Framework support

| Framework | Status |
| --- | --- |
| LangGraph | Supported |
| OpenAI Agents SDK | Supported |
| PydanticAI | Supported |
| CrewAI | Supported |
| AutoGen | Supported |
| Semantic Kernel | Supported |

## Getting started (development)

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

## Download

Chronicle desktop app builds for Windows (x64), macOS (x64 + arm64), and
Linux (x64), plus the `chronicle-sdk` Python wheel, are published on the
[v0.1.0 release](https://github.com/chidhvilasa/chronicle/releases/tag/v0.1.0).

## Project status

Chronicle is early and under active development. See
[KNOWN_ISSUES.md](./KNOWN_ISSUES.md) for current constraints and
[CHANGELOG.md](./CHANGELOG.md) for what's shipped so far.

## Security

See [SECURITY.md](./SECURITY.md) for how to report vulnerabilities and the
security model of the local server.

## License

MIT
