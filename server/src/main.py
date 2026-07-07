"""Chronicle FastAPI server: stores agent trace events and serves them to the app."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src import __version__
from src.database import DEFAULT_DB_PATH, Database
from src.graph_builder import build_graph
from src.models import (
    BackfillResponse,
    EventIn,
    EventOut,
    GraphOut,
    HealthOut,
    MetricsOverviewOut,
    ModelMetricsOut,
    RegisterGraphRequest,
    RegisterGraphResponse,
    ReplayRequest,
    ReplayResponse,
    RunMetricsOut,
    RunOut,
    SnapshotIn,
    SnapshotOut,
    SnapshotSummaryOut,
    TestIn,
    TestOut,
    TestResultOut,
    TimelineOut,
    ToolMetricsOut,
    TrendPointOut,
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
    app.state.backfill_lock = asyncio.Lock()
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


async def _compute_metrics_if_complete(db: Database, run_id: str) -> None:
    """Populates `run_metrics` for a run once its status is `complete`.

    Scheduled as a `BackgroundTasks` job off `POST /events` so metric
    computation never blocks or slows down event ingestion.
    """
    run = await db.get_run(run_id)
    if run is not None and run["status"] == "complete":
        await db.compute_run_metrics(run_id)


@app.post("/events")
async def create_events(events: list[EventIn], background_tasks: BackgroundTasks) -> dict[str, int]:
    count = await app.state.db.insert_events([event.to_row() for event in events])
    for run_id in {event.run_id for event in events}:
        background_tasks.add_task(_compute_metrics_if_complete, app.state.db, run_id)
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
        engine.start_replay,
        snapshot,
        request.modifications,
        new_run_id,
        request.run_id,
        extra_metadata=request.metadata,
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


@app.get("/runs/{run_id}/graph", response_model=GraphOut)
async def get_run_graph(run_id: str) -> GraphOut:
    run = await app.state.db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")
    events = await app.state.db.list_events(run_id)
    graph = build_graph(events)
    return GraphOut(run_id=run_id, nodes=graph["nodes"], edges=graph["edges"], metadata=graph["metadata"])


@app.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: str) -> None:
    deleted = await app.state.db.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found")


_VALID_TREND_PERIODS = {"day", "week", "month"}
_VALID_TREND_METRICS = {"tokens", "cost", "latency", "errors"}


def _parse_date_param(value: str | None, field_name: str) -> float | None:
    """Parses an ISO 8601 date/datetime query param into an epoch timestamp (UTC if no tz given)."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


@app.get("/metrics/overview", response_model=MetricsOverviewOut)
async def get_metrics_overview() -> MetricsOverviewOut:
    overview = await app.state.db.get_metrics_overview()
    return MetricsOverviewOut(**overview)


@app.get("/metrics/runs", response_model=list[RunMetricsOut])
async def list_metrics_runs(
    limit: int = 50,
    offset: int = 0,
    from_date: str | None = None,
    to_date: str | None = None,
    framework: str | None = None,
    status: str | None = None,
) -> list[RunMetricsOut]:
    rows = await app.state.db.list_run_metrics(
        limit=limit,
        offset=offset,
        from_date=_parse_date_param(from_date, "from_date"),
        to_date=_parse_date_param(to_date, "to_date"),
        framework=framework,
        status=status,
    )
    return [RunMetricsOut(**row) for row in rows]


@app.get("/metrics/trends", response_model=list[TrendPointOut])
async def get_metrics_trends(
    period: str = "day", metric: str = "tokens", stat: str = "avg"
) -> list[TrendPointOut]:
    if period not in _VALID_TREND_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period: {period!r}. Must be one of {sorted(_VALID_TREND_PERIODS)}",
        )
    if metric not in _VALID_TREND_METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric: {metric!r}. Must be one of {sorted(_VALID_TREND_METRICS)}",
        )
    points = await app.state.db.get_metrics_trends(period, metric, stat)
    return [TrendPointOut(**point) for point in points]


@app.get("/metrics/tools", response_model=list[ToolMetricsOut])
async def list_metrics_tools() -> list[ToolMetricsOut]:
    tools = await app.state.db.get_tool_metrics()
    return [ToolMetricsOut(**tool) for tool in tools]


@app.get("/metrics/models", response_model=list[ModelMetricsOut])
async def list_metrics_models() -> list[ModelMetricsOut]:
    models = await app.state.db.get_model_metrics()
    return [ModelMetricsOut(**model) for model in models]


@app.post("/metrics/backfill", response_model=BackfillResponse)
async def backfill_metrics() -> BackfillResponse:
    """Computes `run_metrics` for every complete run recorded before this version.

    Rate-limited to one concurrent backfill (409 if one is already running)
    since a full backfill re-reads every complete run's events.
    """
    if app.state.backfill_lock.locked():
        raise HTTPException(status_code=409, detail="A backfill is already running")
    async with app.state.backfill_lock:
        count = await app.state.db.backfill_run_metrics()
    return BackfillResponse(backfilled_count=count)


@app.post("/tests", response_model=TestOut, status_code=201)
async def create_test(request: TestIn) -> TestOut:
    run = await app.state.db.get_run(request.source_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{request.source_run_id}' was not found")

    test_id = str(uuid.uuid4())
    await app.state.db.create_test(
        test_id=test_id,
        name=request.name,
        source_run_id=request.source_run_id,
        source_snapshot_id=request.source_snapshot_id,
        assertions=[a.model_dump() for a in request.assertions],
        created_at=time.time(),
    )
    test = await app.state.db.get_test(test_id)
    assert test is not None
    return TestOut(**test)


@app.get("/tests", response_model=list[TestOut])
async def list_tests() -> list[TestOut]:
    tests = await app.state.db.list_tests()
    return [TestOut(**test) for test in tests]


@app.get("/tests/{test_id}", response_model=TestOut)
async def get_test(test_id: str) -> TestOut:
    test = await app.state.db.get_test(test_id)
    if test is None:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' was not found")
    return TestOut(**test)


@app.delete("/tests/{test_id}", status_code=204)
async def delete_test(test_id: str) -> None:
    deleted = await app.state.db.delete_test(test_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' was not found")


@app.get("/tests/{test_id}/history", response_model=list[TestResultOut])
async def get_test_history(test_id: str) -> list[TestResultOut]:
    test = await app.state.db.get_test(test_id)
    if test is None:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' was not found")
    results = await app.state.db.list_test_results(test_id, limit=20)
    return [TestResultOut(**result) for result in results]


@app.post("/tests/{test_id}/run", response_model=TestResultOut)
async def run_test(test_id: str) -> TestResultOut:
    """Replays the test's source run and evaluates its assertions, awaiting the full result.

    Unlike `POST /replay`, this does not return immediately — it runs the
    replay to completion (via a direct, awaited `ReplayEngine.start_replay`
    call rather than a `BackgroundTasks` job) so the caller gets a finished
    `TestResultOut` in one request, matching the "Run" button's spinner-
    until-done UX in the desktop app.
    """
    test = await app.state.db.get_test(test_id)
    if test is None:
        raise HTTPException(status_code=404, detail=f"Test '{test_id}' was not found")

    graph = app.state.registry.get_active()
    if graph is None:
        raise HTTPException(
            status_code=400,
            detail="No graph registered. Call tracer.register_graph() before running tests.",
        )

    snapshot_id = test["source_snapshot_id"]
    if snapshot_id is None:
        summaries = await app.state.db.list_snapshots_summary(test["source_run_id"])
        step_zero = next((s for s in summaries if s["step_index"] == 0), None)
        if step_zero is None:
            raise HTTPException(
                status_code=404,
                detail=f"No step-0 snapshot found for run '{test['source_run_id']}'",
            )
        snapshot_id = step_zero["snapshot_id"]

    snapshot = await app.state.db.get_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' was not found")

    replay_run_id = str(uuid.uuid4())
    engine = ReplayEngine(db=app.state.db, graph=graph)
    await engine.start_replay(
        snapshot,
        {},
        replay_run_id,
        test["source_run_id"],
        extra_metadata={"triggered_by": "test", "test_id": test_id},
    )

    replay_run = await app.state.db.get_run(replay_run_id)
    events = await app.state.db.list_events(replay_run_id)

    if replay_run is None or replay_run["status"] != "complete":
        result = _error_test_result(test_id, replay_run_id, "replay run failed")
    else:
        try:
            from chronicle.testing.models import ChronicleAssertion
            from chronicle.testing.runner import evaluate_assertion, total_duration_ms, total_token_usage
        except ImportError:
            result = _error_test_result(
                test_id, replay_run_id, "chronicle-sdk is not installed; cannot evaluate assertions"
            )
        else:
            assertions = [ChronicleAssertion.from_dict(a) for a in test["assertions"]]
            assertion_results = [evaluate_assertion(a, events) for a in assertions]
            overall_passed = not any(
                not r.passed and r.on_fail == "fail" for r in assertion_results
            )
            result = TestResultOut(
                result_id=str(uuid.uuid4()),
                test_id=test_id,
                replay_run_id=replay_run_id,
                status="pass" if overall_passed else "fail",
                passed=overall_passed,
                assertion_results=[
                    {
                        "assertion_id": r.assertion_id,
                        "assertion_type": r.assertion_type,
                        "passed": r.passed,
                        "reason": r.reason,
                        "on_fail": r.on_fail,
                    }
                    for r in assertion_results
                ],
                duration_ms=total_duration_ms(events),
                token_usage=total_token_usage(events),
                created_at=time.time(),
            )

    await app.state.db.insert_test_result(
        result_id=result.result_id,
        test_id=test_id,
        replay_run_id=result.replay_run_id,
        status=result.status,
        passed=result.passed,
        assertion_results=[r.model_dump() for r in result.assertion_results],
        duration_ms=result.duration_ms,
        token_usage=result.token_usage,
        error_reason=result.error_reason,
        created_at=result.created_at,
    )
    await app.state.db.update_test_last_result(test_id, result.status, result.created_at)
    return result


def _error_test_result(test_id: str, replay_run_id: str | None, reason: str) -> TestResultOut:
    return TestResultOut(
        result_id=str(uuid.uuid4()),
        test_id=test_id,
        replay_run_id=replay_run_id,
        status="error",
        passed=False,
        assertion_results=[],
        duration_ms=None,
        token_usage=None,
        error_reason=reason,
        created_at=time.time(),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=DEFAULT_HOST, port=DEFAULT_PORT, reload=True)
