// TypeScript mirrors of the Chronicle server's response shapes.
// Keep in sync with server/src/models.py (EventOut, RunOut, TimelineOut).

export type EventType =
  | "tool_call"
  | "llm_call"
  | "agent_message"
  | "memory_update"
  | "error"
  | "retry";

export interface Event {
  event_id: string;
  run_id: string;
  timestamp: number;
  event_type: EventType;
  agent_name: string | null;
  duration_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  data: Record<string, unknown>;
  error: string | null;
}

export interface Run {
  run_id: string;
  started_at: number;
  finished_at: number;
  framework: string | null;
  agent_count: number;
  total_tokens: number;
  total_cost_usd: number;
  status: string;
  metadata: Record<string, unknown>;
}

export type TimelineSegmentType = "llm_call" | "tool_call" | "waiting" | "error" | "retry";

export interface TimelineTokenUsage {
  input_tokens: number | null;
  output_tokens: number | null;
}

export interface TimelineSegment {
  type: TimelineSegmentType;
  start_time_ms: number;
  duration_ms: number;
  label: string;
  token_usage: TimelineTokenUsage | null;
  event_id: string | null;
}

export interface TimelineLane {
  agent_name: string;
  segments: TimelineSegment[];
}

export interface Timeline {
  run_id: string;
  lanes: TimelineLane[];
}

export interface HealthStatus {
  status: "ok";
  version: string;
}

export interface SnapshotSummary {
  snapshot_id: string;
  step_index: number;
  timestamp: number;
  agent_name: string | null;
  event_id: string | null;
}

export interface Snapshot {
  snapshot_id: string;
  run_id: string;
  event_id: string | null;
  step_index: number;
  timestamp: number;
  agent_name: string | null;
  graph_state: Record<string, unknown>;
  messages: unknown[];
  tool_results: unknown[];
  metadata: Record<string, unknown>;
}

export interface ReplayResponse {
  run_id: string;
}

/** Whichever main-panel item is currently selected for the detail inspector. */
export type DetailItem = Event | TimelineSegment;

/** `Event` and `TimelineSegment` both carry `event_id`, so discriminate on `run_id` instead. */
export function isEventDetail(item: DetailItem): item is Event {
  return "run_id" in item;
}

export interface ReplayMetadata {
  sourceRunId: string;
  sourceSnapshotId: string;
  stepIndex: number;
}

/** Reads `{is_replay, source_run_id, source_snapshot_id, step_index}` out of a run's metadata. */
export function getReplayMetadata(run: Run): ReplayMetadata | null {
  const { metadata } = run;
  if (metadata["is_replay"] !== true) return null;
  const sourceRunId = metadata["source_run_id"];
  const sourceSnapshotId = metadata["source_snapshot_id"];
  const stepIndex = metadata["step_index"];
  if (typeof sourceRunId !== "string" || typeof sourceSnapshotId !== "string") return null;
  if (typeof stepIndex !== "number") return null;
  return { sourceRunId, sourceSnapshotId, stepIndex };
}

export type AssertionType =
  | "output_contains"
  | "output_not_contains"
  | "output_matches_regex"
  | "tool_called"
  | "tool_not_called"
  | "token_count_under"
  | "latency_under_ms"
  | "no_errors"
  | "custom";

export type OnFail = "fail" | "warn";

export type TestStatus = "pass" | "fail" | "error";

export interface ChronicleAssertion {
  assertion_id: string | null;
  assertion_type: AssertionType;
  target: string;
  agent_name: string | null;
  on_fail: OnFail;
}

export interface ChronicleTest {
  test_id: string;
  name: string;
  source_run_id: string;
  source_snapshot_id: string | null;
  assertions: ChronicleAssertion[];
  created_at: number;
  last_run_at: number | null;
  last_result: TestStatus | null;
}

export interface AssertionResult {
  assertion_id: string;
  assertion_type: string;
  passed: boolean;
  reason: string;
  on_fail: OnFail;
}

export interface TestResult {
  result_id: string;
  test_id: string;
  replay_run_id: string | null;
  status: TestStatus;
  passed: boolean;
  assertion_results: AssertionResult[];
  duration_ms: number | null;
  token_usage: { input_tokens: number | null; output_tokens: number | null } | null;
  error_reason: string | null;
  created_at: number;
}

// Mirrors server/src/models.py's MetricsOverviewOut/RunMetricsOut/TrendPointOut/
// ToolMetricsOut/ModelMetricsOut (the `GET/POST /metrics/*` endpoints, Phase 18).

export interface MetricsOverview {
  total_runs: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_run_duration_ms: number;
  total_errors: number;
  runs_last_7_days: number;
  tokens_last_7_days: number;
  cost_last_7_days: number;
  most_expensive_run_id: string | null;
  slowest_run_id: string | null;
  cost_is_estimate: true;
}

export interface RunMetrics {
  run_id: string;
  total_duration_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  llm_call_count: number;
  tool_call_count: number;
  error_count: number;
  retry_count: number;
  avg_llm_latency_ms: number | null;
  p95_llm_latency_ms: number | null;
  avg_tool_latency_ms: number | null;
  p95_tool_latency_ms: number | null;
  framework: string | null;
  agent_count: number;
  created_at: number;
  cost_is_estimate: true;
}

export type TrendPeriod = "day" | "week" | "month";
export type TrendMetric = "tokens" | "cost" | "latency" | "errors";

export interface TrendPoint {
  bucket: string;
  value: number;
}

export interface ToolMetrics {
  tool_name: string;
  call_count: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  error_rate: number;
  total_tokens: number;
}

export interface ModelMetrics {
  model_name: string;
  call_count: number;
  avg_latency_ms: number | null;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  cost_is_estimate: true;
}

export interface BackfillResult {
  backfilled_count: number;
}

// Mirrors server/src/models.py's GraphNodeOut/GraphEdgeOut/GraphMetadataOut/GraphOut
// (`GET /runs/{id}/graph`, Phase 22), built by server/src/graph_builder.py.

export type GraphNodeType = "agent" | "tool" | "llm" | "input" | "output";
export type GraphEdgeType = "calls" | "responds" | "handoff" | "triggers";
export type GraphNodeStatus = "ok" | "error" | "warning";

export interface GraphNode {
  id: string;
  type: GraphNodeType;
  label: string;
  agent_name: string | null;
  event_count: number;
  error_count: number;
  total_tokens: number;
  avg_latency_ms: number | null;
  status: GraphNodeStatus;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  edge_type: GraphEdgeType;
  event_count: number;
}

export interface GraphMetadata {
  total_nodes: number;
  total_edges: number;
  has_cycles: boolean;
  max_depth: number;
}

export interface ExecutionGraph {
  run_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  metadata: GraphMetadata;
}

// Mirrors server/src/models.py's PromptSummaryOut/PromptDetailOut/PromptDiffOut/
// MemorySnapshotOut/MemoryListOut (`GET/POST /runs/{id}/prompts|memory`, `GET
// /prompts/diff`, Phase 24).

export interface PromptSummary {
  event_id: string;
  step_index: number;
  agent_name: string | null;
  timestamp: number;
  total_chars: number;
  total_tokens: number;
}

export interface PromptMessage {
  role: string;
  content: string;
}

export interface PromptDetail {
  event_id: string;
  step_index: number;
  agent_name: string | null;
  timestamp: number;
  system_prompt: string | null;
  user_messages: PromptMessage[];
  assistant_messages: PromptMessage[];
  total_chars: number;
  total_tokens: number;
}

export interface PromptDiffResult {
  additions: number;
  deletions: number;
  unchanged: number;
  diff_html: string;
}

export interface MemorySnapshot {
  event_id: string;
  step_index: number;
  agent_name: string | null;
  timestamp: number;
  memory_before: Record<string, unknown>;
  memory_after: Record<string, unknown>;
  keys_added: string[];
  keys_removed: string[];
  keys_changed: string[];
}

export interface MemoryList {
  snapshots: MemorySnapshot[];
  message: string | null;
}
