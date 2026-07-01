import { COST_PER_INPUT_TOKEN_USD, COST_PER_OUTPUT_TOKEN_USD } from "../../config";
import type { Event, Run } from "../../types";

export interface RunStats {
  durationSeconds: number;
  totalTokens: number;
  totalCostUsd: number;
  errorCount: number;
  toolCallCount: number;
}

/** Duration/tokens come from the run summary; cost/errors/tool-calls are derived from its events. */
export function computeRunStats(run: Run, events: Event[]): RunStats {
  let inputTokens = 0;
  let outputTokens = 0;
  let errorCount = 0;
  let toolCallCount = 0;
  for (const event of events) {
    inputTokens += event.input_tokens ?? 0;
    outputTokens += event.output_tokens ?? 0;
    if (event.event_type === "error") errorCount += 1;
    if (event.event_type === "tool_call") toolCallCount += 1;
  }
  return {
    durationSeconds: Math.max(0, run.finished_at - run.started_at),
    totalTokens: run.total_tokens,
    totalCostUsd: inputTokens * COST_PER_INPUT_TOKEN_USD + outputTokens * COST_PER_OUTPUT_TOKEN_USD,
    errorCount,
    toolCallCount,
  };
}

export type EventDiffStatus = "same" | "different" | "missing_a" | "missing_b";

export interface DiffField {
  label: string;
  a: string;
  b: string;
  differs: boolean;
}

export interface EventDiffRow {
  index: number;
  eventA: Event | null;
  eventB: Event | null;
  status: EventDiffStatus;
  fields: DiffField[];
}

function toolNameOf(event: Event): string {
  const name = event.data["tool_name"];
  return typeof name === "string" ? name : "";
}

function durationLabel(event: Event): string {
  return event.duration_ms !== null ? `${Math.round(event.duration_ms)}ms` : "—";
}

function tokensLabel(event: Event): string {
  return `${event.input_tokens ?? 0} in / ${event.output_tokens ?? 0} out`;
}

function buildFields(a: Event, b: Event): DiffField[] {
  return [
    {
      label: "Duration",
      a: durationLabel(a),
      b: durationLabel(b),
      differs: a.duration_ms !== b.duration_ms,
    },
    {
      label: "Tokens",
      a: tokensLabel(a),
      b: tokensLabel(b),
      differs: a.input_tokens !== b.input_tokens || a.output_tokens !== b.output_tokens,
    },
    { label: "Tool", a: toolNameOf(a), b: toolNameOf(b), differs: toolNameOf(a) !== toolNameOf(b) },
    {
      label: "Error",
      a: a.error ?? "",
      b: b.error ?? "",
      differs: (a.error ?? "") !== (b.error ?? ""),
    },
  ];
}

/** Diffs two runs' events by sequence position (index), not by matching/aligning content. */
export function buildEventDiffRows(eventsA: Event[], eventsB: Event[]): EventDiffRow[] {
  const length = Math.max(eventsA.length, eventsB.length);
  const rows: EventDiffRow[] = [];
  for (let index = 0; index < length; index += 1) {
    const eventA = eventsA[index] ?? null;
    const eventB = eventsB[index] ?? null;

    if (eventA === null || eventB === null) {
      rows.push({
        index,
        eventA,
        eventB,
        status: eventA === null ? "missing_a" : "missing_b",
        fields: [],
      });
      continue;
    }

    const fields = buildFields(eventA, eventB);
    rows.push({
      index,
      eventA,
      eventB,
      status: fields.some((field) => field.differs) ? "different" : "same",
      fields,
    });
  }
  return rows;
}

export function promptOf(event: Event | null): string {
  if (event === null) return "";
  const prompt = event.data["prompt"];
  return typeof prompt === "string" ? prompt : "";
}
