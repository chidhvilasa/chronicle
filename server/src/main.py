"""Chronicle FastAPI server: stores agent trace events and serves them to the app."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src import __version__
from src.database import DEFAULT_DB_PATH, Database
from src.models import EventIn, EventOut, HealthOut, RunOut, TimelineOut
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


@app.get("/runs", response_model=list[RunOut])
async def list_runs() -> list[RunOut]:
    runs = await app.state.db.list_runs()
    return [RunOut(**run) for run in runs]


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
