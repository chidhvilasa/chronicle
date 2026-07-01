// TypeScript mirrors of the Chronicle server's event and run schemas.
// Keep in sync with server/src/chronicle_server/models.py

export type EventType =
  | "tool_call"
  | "llm_call"
  | "agent_message"
  | "memory_update"
  | "error"
  | "retry";

export interface ChronicleEvent {
  id: string;
  run_id: string;
  parent_id: string | null;
  event_type: EventType;
  timestamp: number;
  payload: Record<string, unknown>;
}

export interface ChronicleRun {
  id: string;
  started_at: number;
  ended_at: number;
  event_count: number;
}
