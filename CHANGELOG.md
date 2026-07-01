# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

- Initial monorepo scaffold: `/sdk` (chronicle-sdk Python package), `/server`
  (FastAPI server), `/app` (Tauri + React + TypeScript desktop app), `/docs`.
- `chronicle-sdk`: `ChronicleTracer`, event schemas (`tool_call`, `llm_call`,
  `agent_message`, `memory_update`, `error`, `retry`), local SQLite fallback
  storage, and a LangGraph/LangChain callback handler.
- `chronicle-server`: FastAPI app with `POST /events`, `GET /runs`,
  `GET /runs/{id}/events`, `GET /runs/{id}/timeline`, `DELETE /runs/{id}`,
  backed by SQLite via `aiosqlite`.
- `chronicle-app`: Tauri desktop shell with a run sidebar, event timeline, and
  event inspector panel.
- CI workflow running Python tests for `/sdk` and `/server`, and TypeScript
  type-checking plus Vitest for `/app`.

### Changed

- `chronicle-sdk`: reworked the event model into
  `chronicle.models.ChronicleEvent`/`TokenUsage` dataclasses
  (`event_id`/`data`/`agent_name`/`duration_ms`/`token_usage`/`error`).
  `ChronicleTracer` now exposes `record_event()`/`flush()`, buffers events,
  and flushes them to the server in batches, falling back to
  `chronicle_runs/{run_id}.json` (instead of a local SQLite database) when
  the server is unreachable. Replaced the LangChain callback handler with
  `chronicle.adapters.langgraph.LangGraphAdapter`, which adds
  `on_agent_finish` handling and captures per-call duration and token usage.
  Requires Python 3.10+.
