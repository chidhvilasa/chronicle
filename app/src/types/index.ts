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
