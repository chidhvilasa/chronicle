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

export type TimelineSegmentType = "llm_call" | "tool_call" | "waiting" | "error";

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

/** Whichever main-panel item is currently selected for the detail inspector. */
export type DetailItem = Event | TimelineSegment;

export function isEventDetail(item: DetailItem): item is Event {
  return "event_id" in item;
}
