import { describe, expect, it } from "vitest";
import { buildEventDiffRows, computeRunStats, promptOf } from "../computeDiff";
import type { Event, Run } from "../../../types";

function makeEvent(overrides: Partial<Event>): Event {
  return {
    event_id: "evt-1",
    run_id: "run-1",
    timestamp: 1000,
    event_type: "tool_call",
    agent_name: "agent-a",
    duration_ms: 100,
    input_tokens: null,
    output_tokens: null,
    data: {},
    error: null,
    ...overrides,
  };
}

function makeRun(overrides: Partial<Run>): Run {
  return {
    run_id: "run-1",
    started_at: 1000,
    finished_at: 1010,
    framework: null,
    agent_count: 1,
    total_tokens: 0,
    total_cost_usd: 0,
    status: "running",
    metadata: {},
    ...overrides,
  };
}

describe("computeRunStats", () => {
  it("computes duration from the run's started_at/finished_at", () => {
    const run = makeRun({ started_at: 1000, finished_at: 1030 });
    const stats = computeRunStats(run, []);
    expect(stats.durationSeconds).toBe(30);
  });

  it("counts errors and tool calls from events", () => {
    const run = makeRun({});
    const events = [
      makeEvent({ event_type: "error" }),
      makeEvent({ event_type: "tool_call" }),
      makeEvent({ event_type: "tool_call" }),
      makeEvent({ event_type: "llm_call" }),
    ];
    const stats = computeRunStats(run, events);
    expect(stats.errorCount).toBe(1);
    expect(stats.toolCallCount).toBe(2);
  });

  it("estimates cost from summed input/output tokens across events", () => {
    const run = makeRun({});
    const events = [makeEvent({ input_tokens: 1000, output_tokens: 500 })];
    const stats = computeRunStats(run, events);
    // 1000 * 0.000003 + 500 * 0.000015 = 0.003 + 0.0075 = 0.0105
    expect(stats.totalCostUsd).toBeCloseTo(0.0105, 6);
  });
});

describe("buildEventDiffRows", () => {
  it("returns an empty list when both runs have no events", () => {
    expect(buildEventDiffRows([], [])).toEqual([]);
  });

  it("marks a row as missing_b when only run A has an event at that position", () => {
    const rows = buildEventDiffRows([makeEvent({ event_id: "a1" })], []);
    expect(rows).toHaveLength(1);
    expect(rows[0].status).toBe("missing_b");
    expect(rows[0].eventA).not.toBeNull();
    expect(rows[0].eventB).toBeNull();
  });

  it("marks a row as missing_a when only run B has an event at that position", () => {
    const rows = buildEventDiffRows([], [makeEvent({ event_id: "b1" })]);
    expect(rows[0].status).toBe("missing_a");
  });

  it("marks a row as same when both events at a position have identical diffed fields", () => {
    const a = makeEvent({ event_id: "a1", duration_ms: 100, data: { tool_name: "search" } });
    const b = makeEvent({ event_id: "b1", duration_ms: 100, data: { tool_name: "search" } });
    const rows = buildEventDiffRows([a], [b]);
    expect(rows[0].status).toBe("same");
  });

  it("marks a row as different and flags the differing field when durations differ", () => {
    const a = makeEvent({ event_id: "a1", duration_ms: 100 });
    const b = makeEvent({ event_id: "b1", duration_ms: 500 });
    const rows = buildEventDiffRows([a], [b]);
    expect(rows[0].status).toBe("different");
    const durationField = rows[0].fields.find((f) => f.label === "Duration");
    expect(durationField?.differs).toBe(true);
  });

  it("handles runs of different lengths gracefully, producing one row per max length", () => {
    const eventsA = [makeEvent({ event_id: "a1" }), makeEvent({ event_id: "a2" })];
    const eventsB = [makeEvent({ event_id: "b1" })];
    const rows = buildEventDiffRows(eventsA, eventsB);
    expect(rows).toHaveLength(2);
    expect(rows[0].status).not.toBe("missing_a");
    expect(rows[1].status).toBe("missing_b");
  });

  it("flags tool name and error status as differing fields", () => {
    const a = makeEvent({ event_id: "a1", data: { tool_name: "search" }, error: null });
    const b = makeEvent({ event_id: "b1", data: { tool_name: "calculator" }, error: "boom" });
    const rows = buildEventDiffRows([a], [b]);
    const toolField = rows[0].fields.find((f) => f.label === "Tool");
    const errorField = rows[0].fields.find((f) => f.label === "Error");
    expect(toolField?.differs).toBe(true);
    expect(errorField?.differs).toBe(true);
  });
});

describe("promptOf", () => {
  it("extracts a string prompt field from event data", () => {
    const event = makeEvent({ data: { prompt: "hello" } });
    expect(promptOf(event)).toBe("hello");
  });

  it("returns an empty string when there is no prompt field or event", () => {
    expect(promptOf(makeEvent({ data: {} }))).toBe("");
    expect(promptOf(null)).toBe("");
  });
});
