"""Chronicle FastAPI server: stores agent trace events and serves them to the app."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException

from chronicle_server.db import DEFAULT_DB_PATH, Database
from chronicle_server.models import EventIn, HealthOut, RunOut


def _resolve_db_path() -> str:
    return os.environ.get("CHRONICLE_DB_PATH", str(DEFAULT_DB_PATH))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db = Database(db_path=_resolve_db_path())
    await db.connect()
    app.state.db = db
    yield
    await db.close()


app = FastAPI(title="Chronicle Server", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(status="ok")


@app.post("/events", response_model=EventIn, status_code=201)
async def create_event(event: EventIn) -> EventIn:
    await app.state.db.insert_event(event.model_dump())
    return event


@app.get("/runs", response_model=list[RunOut])
async def list_runs() -> list[RunOut]:
    runs = await app.state.db.list_runs()
    return [RunOut(**run) for run in runs]


@app.get("/runs/{run_id}/events", response_model=list[EventIn])
async def list_run_events(run_id: str) -> list[EventIn]:
    run = await app.state.db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")
    events = await app.state.db.list_events(run_id)
    return [EventIn(**event) for event in events]


@app.get("/runs/{run_id}/timeline", response_model=list[EventIn])
async def get_run_timeline(run_id: str) -> list[EventIn]:
    run = await app.state.db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")
    events = await app.state.db.list_events(run_id)
    return [EventIn(**event) for event in events]


@app.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: str) -> None:
    deleted = await app.state.db.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")
