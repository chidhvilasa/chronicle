"""Pydantic request/response models for the Chronicle server API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from src.validation import clamp_duration_ms, clamp_int32

EventTypeLiteral = Literal[
    "tool_call", "llm_call", "agent_message", "memory_update", "error", "retry"
]


class TokenUsageIn(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class EventIn(BaseModel):
    """Shape of one event as sent by chronicle-sdk's `ChronicleTracer`."""

    event_id: str
    run_id: str
    timestamp: float
    event_type: EventTypeLiteral
    agent_name: str | None = None
    data: dict[str, Any] = {}
    duration_ms: float | None = None
    token_usage: TokenUsageIn | None = None
    error: str | None = None

    def to_row(self) -> dict[str, Any]:
        """Flatten into the column shape `Database.insert_events` expects.

        Numeric fields are clamped to a signed 32-bit range here — the single place
        every event passes through on its way to SQLite — so a malformed or
        adversarial token count/duration can never reach storage or downstream
        consumers (the app's JS numbers, chart libraries, etc.) unbounded.
        """
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "agent_name": self.agent_name,
            "duration_ms": clamp_duration_ms(self.duration_ms),
            "input_tokens": clamp_int32(self.token_usage.input_tokens if self.token_usage else None),
            "output_tokens": clamp_int32(self.token_usage.output_tokens if self.token_usage else None),
            "data": self.data,
            "error": self.error,
        }


class SnapshotIn(BaseModel):
    """Shape of one state snapshot as sent by chronicle-sdk's `LangGraphAdapter`."""

    snapshot_id: str
    run_id: str
    event_id: str | None = None
    step_index: int
    timestamp: float
    agent_name: str | None = None
    messages: list[Any] = []
    tool_results: list[Any] = []
    graph_state: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class SnapshotSummaryOut(BaseModel):
    """Shape of one snapshot in `GET /runs/{id}/snapshots` — no `graph_state`/messages."""

    snapshot_id: str
    step_index: int
    timestamp: float
    agent_name: str | None
    event_id: str | None


class SnapshotOut(BaseModel):
    """Full snapshot detail, from `GET /runs/{id}/snapshots/{snapshot_id}`."""

    snapshot_id: str
    run_id: str
    event_id: str | None
    step_index: int
    timestamp: float
    agent_name: str | None
    graph_state: dict[str, Any]
    messages: list[Any]
    tool_results: list[Any]
    metadata: dict[str, Any]


class ReplayRequest(BaseModel):
    run_id: str
    snapshot_id: str
    modifications: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class ReplayResponse(BaseModel):
    run_id: str


class RegisterGraphRequest(BaseModel):
    graph_module: str
    graph_attr: str


class RegisterGraphResponse(BaseModel):
    name: str


class EventOut(BaseModel):
    """Shape of one event as stored and read back from SQLite."""

    event_id: str
    run_id: str
    timestamp: float
    event_type: str
    agent_name: str | None
    duration_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    data: dict[str, Any]
    error: str | None


class RunOut(BaseModel):
    """Summary stats for one run, derived from its events."""

    run_id: str
    started_at: float
    finished_at: float
    framework: str | None
    agent_count: int
    total_tokens: int
    total_cost_usd: float
    status: str
    metadata: dict[str, Any]


class TimelineSegmentOut(BaseModel):
    type: Literal["llm_call", "tool_call", "waiting", "error", "retry"]
    start_time_ms: float
    duration_ms: float
    label: str
    token_usage: dict[str, int | None] | None = None
    event_id: str | None = None


class TimelineLaneOut(BaseModel):
    agent_name: str
    segments: list[TimelineSegmentOut]


class TimelineOut(BaseModel):
    run_id: str
    lanes: list[TimelineLaneOut]


class HealthOut(BaseModel):
    status: Literal["ok"]
    version: str


class MetricsOverviewOut(BaseModel):
    """Aggregate stats across every run with a `run_metrics` row, from `GET /metrics/overview`."""

    total_runs: int
    total_tokens: int
    total_cost_usd: float
    avg_run_duration_ms: float
    total_errors: int
    runs_last_7_days: int
    tokens_last_7_days: int
    cost_last_7_days: float
    most_expensive_run_id: str | None
    slowest_run_id: str | None
    cost_is_estimate: Literal[True] = True


class RunMetricsOut(BaseModel):
    """One `run_metrics` row, from `GET /metrics/runs`."""

    run_id: str
    total_duration_ms: float
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    llm_call_count: int
    tool_call_count: int
    error_count: int
    retry_count: int
    avg_llm_latency_ms: float | None
    p95_llm_latency_ms: float | None
    avg_tool_latency_ms: float | None
    p95_tool_latency_ms: float | None
    framework: str | None
    agent_count: int
    created_at: float
    cost_is_estimate: Literal[True] = True


class TrendPointOut(BaseModel):
    """One time-bucketed data point, from `GET /metrics/trends`."""

    bucket: str
    value: float


class ToolMetricsOut(BaseModel):
    """One tool's aggregate performance across every run, from `GET /metrics/tools`."""

    tool_name: str
    call_count: int
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    error_rate: float
    total_tokens: int


class ModelMetricsOut(BaseModel):
    """One model's aggregate usage across every run, from `GET /metrics/models`."""

    model_name: str
    call_count: int
    avg_latency_ms: float | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    cost_is_estimate: Literal[True] = True


class BackfillResponse(BaseModel):
    backfilled_count: int


class GraphNodeOut(BaseModel):
    """One node in a run's execution graph, from `GET /runs/{id}/graph`."""

    id: str
    type: Literal["agent", "tool", "llm", "input", "output"]
    label: str
    agent_name: str | None
    event_count: int
    error_count: int
    total_tokens: int
    avg_latency_ms: float | None
    status: Literal["ok", "error", "warning"]


class GraphEdgeOut(BaseModel):
    """One edge in a run's execution graph, from `GET /runs/{id}/graph`."""

    id: str
    source: str
    target: str
    label: str
    edge_type: Literal["calls", "responds", "handoff", "triggers"]
    event_count: int


class GraphMetadataOut(BaseModel):
    total_nodes: int
    total_edges: int
    has_cycles: bool
    max_depth: int


class GraphOut(BaseModel):
    run_id: str
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
    metadata: GraphMetadataOut


class PromptSummaryOut(BaseModel):
    """One `llm_call` event, without message content - from `GET /runs/{id}/prompts`."""

    event_id: str
    step_index: int
    agent_name: str | None
    timestamp: float
    total_chars: int
    total_tokens: int


class PromptDetailOut(BaseModel):
    """Full prompt content for one `llm_call` event - from `GET /runs/{id}/prompts/{event_id}`."""

    event_id: str
    step_index: int
    agent_name: str | None
    timestamp: float
    system_prompt: str | None
    user_messages: list[dict[str, Any]]
    assistant_messages: list[dict[str, Any]]
    total_chars: int
    total_tokens: int


class PromptDiffOut(BaseModel):
    additions: int
    deletions: int
    unchanged: int
    diff_html: str


class MemorySnapshotOut(BaseModel):
    """One `memory_update` event's before/after diff - from `GET /runs/{id}/memory`."""

    event_id: str
    step_index: int
    agent_name: str | None
    timestamp: float
    memory_before: dict[str, Any]
    memory_after: dict[str, Any]
    keys_added: list[str]
    keys_removed: list[str]
    keys_changed: list[str]


class MemoryListOut(BaseModel):
    snapshots: list[MemorySnapshotOut]
    message: str | None = None


class RunMetadataRequest(BaseModel):
    """Body of `POST /runs/{id}/metadata` — e.g. `{"chaos_mode": true, "chaos_config": {...}}`."""

    metadata: dict[str, Any]


AssertionTypeLiteral = Literal[
    "output_contains",
    "output_not_contains",
    "output_matches_regex",
    "tool_called",
    "tool_not_called",
    "token_count_under",
    "latency_under_ms",
    "no_errors",
    "custom",
]

TestStatusLiteral = Literal["pass", "fail", "error"]


class AssertionIn(BaseModel):
    """One assertion, as sent by `POST /tests` or stored inside a test's `assertions` column."""

    assertion_id: str | None = None
    assertion_type: AssertionTypeLiteral
    target: str
    agent_name: str | None = None
    on_fail: Literal["fail", "warn"] = "fail"


class AssertionResultOut(BaseModel):
    assertion_id: str
    assertion_type: str
    passed: bool
    reason: str
    on_fail: Literal["fail", "warn"] = "fail"


class TestIn(BaseModel):
    """Shape of `POST /tests`'s body."""

    name: str
    source_run_id: str
    source_snapshot_id: str | None = None
    assertions: list[AssertionIn] = []


class TestOut(BaseModel):
    test_id: str
    name: str
    source_run_id: str
    source_snapshot_id: str | None
    assertions: list[AssertionIn]
    created_at: float
    last_run_at: float | None
    last_result: TestStatusLiteral | None


class TestResultOut(BaseModel):
    result_id: str
    test_id: str
    replay_run_id: str | None
    status: TestStatusLiteral
    passed: bool
    assertion_results: list[AssertionResultOut]
    duration_ms: float | None
    token_usage: dict[str, int | None] | None
    error_reason: str | None = None
    created_at: float
