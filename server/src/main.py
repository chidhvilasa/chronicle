"""Chronicle FastAPI server: stores agent trace events and serves them to the app."""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src import __version__
from src.database import DEFAULT_DB_PATH, Database
from src.models import (
    EventIn,
    EventOut,
    HealthOut,
    RegisterGraphRequest,
    RegisterGraphResponse,
    ReplayRequest,
    ReplayResponse,
    RunOut,
    SnapshotIn,
    SnapshotOut,
    SnapshotSummaryOut,
    TimelineOut,
)
from src.registry import GraphRegistrationError, GraphRegistry
from src.replay import ReplayEngine
from src.timeline import build_timeline

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7823
ALLOWED_ORIGINS = ["http://localhost:1420"]


def _resolve_db_path() -> str:
    return os.environ.get("CHRONICLE_DB_PATH", str(DEFAULT_DB_PATH))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    db = Database(db_path=_resolve_db_path())
    await db.connect()
    app.state.db = db
    app.state.registry = GraphRegistry()
    yield
    await db.close()


app = FastAPI(title="Chronicle Server", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _status_label(status_code: int) -> str:
    return {
        400: "bad_request",
        404: "not_found",
        422: "validation_error",
        500: "internal_error",
    }.get(status_code, "error")


def _format_validation_errors(errors: list[dict[str, Any]]) -> str:
    messages = []
    for err in errors:
        loc = ".".join(str(part) for part in err.get("loc", []) if part != "body")
        message = err.get("msg", "Invalid request")
        messages.append(f"{loc}: {message}" if loc else message)
    return "; ".join(messages) or "Invalid request"


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": _status_label(exc.status_code), "detail": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "detail": _format_validation_errors(exc.errors())},
    )


@app.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(status="ok", version=__version__)


@app.post("/events")
async def create_events(events: list[EventIn]) -> dict[str, int]:
    count = await app.state.db.insert_events([event.to_row() for event in events])
    return {"count": count}


@app.post("/snapshots")
async def create_snapshots(snapshots: list[SnapshotIn]) -> dict[str, int]:
    count = await app.state.db.insert_snapshots([snapshot.model_dump() for snapshot in snapshots])
    return {"count": count}


@app.post("/register", response_model=RegisterGraphResponse)
async def register_graph(request: RegisterGraphRequest) -> RegisterGraphResponse:
    try:
        name = app.state.registry.register(request.graph_module, request.graph_attr)
    except GraphRegistrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RegisterGraphResponse(name=name)


@app.get("/registry", response_model=list[str])
async def list_registered_graphs() -> list[str]:
    return app.state.registry.list_names()


@app.post("/replay", response_model=ReplayResponse)
async def replay(request: ReplayRequest, background_tasks: BackgroundTasks) -> ReplayResponse:
    graph = app.state.registry.get_active()
    if graph is None:
        raise HTTPException(
            status_code=400,
            detail="No graph registered. Call tracer.register_graph() before replaying.",
        )

    snapshot = await app.state.db.get_snapshot(request.snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Snapshot '{request.snapshot_id}' was not found")

    new_run_id = str(uuid.uuid4())
    engine = ReplayEngine(db=app.state.db, graph=graph)
    background_tasks.add_task(
        engine.start_replay, snapshot, request.modifications, new_run_id, request.run_id
    )
    return ReplayResponse(run_id=new_run_id)


@app.get("/runs", response_model=list[RunOut])
async def list_runs() -> list[RunOut]:
    runs = await app.state.db.list_runs()
    return [RunOut(**run) for run in runs]


@app.get("/runs/{run_id}/snapshots", response_model=list[SnapshotSummaryOut])
async def list_run_snapshots(run_id: str) -> list[SnapshotSummaryOut]:
    run = await app.state.db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")
    snapshots = await app.state.db.list_snapshots_summary(run_id)
    return [SnapshotSummaryOut(**snapshot) for snapshot in snapshots]


@app.get("/runs/{run_id}/snapshots/{snapshot_id}", response_model=SnapshotOut)
async def get_run_snapshot(run_id: str, snapshot_id: str) -> SnapshotOut:
    snapshot = await app.state.db.get_snapshot(snapshot_id)
    if snapshot is None or snapshot["run_id"] != run_id:
        raise HTTPException(
            status_code=404, detail=f"Snapshot '{snapshot_id}' was not found for run '{run_id}'"
        )
    return SnapshotOut(**snapshot)


@app.get("/runs/{run_id}/events", response_model=list[EventOut])
async def list_run_events(run_id: str) -> list[EventOut]:
    run = await app.state.db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")
    events = await app.state.db.list_events(run_id)
    return [EventOut(**event) for event in events]


@app.get("/runs/{run_id}/timeline", response_model=TimelineOut)
async def get_run_timeline(run_id: str) -> TimelineOut:
    run = await app.state.db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")
    events = await app.state.db.list_events(run_id)
    return TimelineOut(run_id=run_id, lanes=build_timeline(events))


@app.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: str) -> None:
    deleted = await app.state.db.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=DEFAULT_HOST, port=DEFAULT_PORT, reload=True)
