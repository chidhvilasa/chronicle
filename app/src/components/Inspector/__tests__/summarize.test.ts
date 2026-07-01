import { describe, expect, it } from "vitest";
import { summarizeAgent, summarizeTools } from "../summarize";
import type { Event } from "../../../types";

function makeEvent(overrides: Partial<Event>): Event {
  return {
    event_id: "evt-1",
    run_id: "run-1",
    timestamp: 1000,
    event_type: "tool_call",
    agent_name: "agent-a",
    duration_ms: null,
    input_tokens: null,
    output_tokens: null,
    data: {},
    error: null,
    ...overrides,
  };
}

describe("summarizeAgent", () => {
  it("counts llm calls, tool calls, tokens, and errors for the given agent only", () => {
    const events: Event[] = [
      makeEvent({ event_id: "e1", agent_name: "agent-a", event_type: "llm_call", duration_ms: 100, input_tokens: 10, output_tokens: 5 }),
      makeEvent({ event_id: "e2", agent_name: "agent-a", event_type: "tool_call", data: { tool_name: "search" } }),
      makeEvent({ event_id: "e3", agent_name: "agent-a", event_type: "error" }),
      makeEvent({ event_id: "e4", agent_name: "agent-b", event_type: "llm_call" }),
    ];

    const summary = summarizeAgent(events, "agent-a");

    expect(summary.llmCallCount).toBe(1);
    expect(summary.toolCallCount).toBe(1);
    expect(summary.errorCount).toBe(1);
    expect(summary.totalTokens).toBe(15);
  });

  it("computes average llm latency from durations only", () => {
    const events: Event[] = [
      makeEvent({ event_id: "e1", event_type: "llm_call", duration_ms: 100 }),
      makeEvent({ event_id: "e2", event_type: "llm_call", duration_ms: 300 }),
    ];
    const summary = summarizeAgent(events, "agent-a");
    expect(summary.averageLlmLatencyMs).toBe(200);
  });

  it("returns null average latency when there are no llm calls", () => {
    const summary = summarizeAgent([], "agent-a");
    expect(summary.averageLlmLatencyMs).toBeNull();
  });

  it("groups tool usage by tool name with call counts, sorted descending", () => {
    const events: Event[] = [
      makeEvent({ event_id: "e1", event_type: "tool_call", data: { tool_name: "search" } }),
      makeEvent({ event_id: "e2", event_type: "tool_call", data: { tool_name: "search" } }),
      makeEvent({ event_id: "e3", event_type: "tool_call", data: { tool_name: "calculator" } }),
    ];
    const summary = summarizeAgent(events, "agent-a");
    expect(summary.toolUsage).toEqual([
      { toolName: "search", callCount: 2 },
      { toolName: "calculator", callCount: 1 },
    ]);
  });

  it("treats a missing agent_name as unknown", () => {
    const events: Event[] = [makeEvent({ agent_name: null, event_type: "llm_call" })];
    const summary = summarizeAgent(events, "unknown");
    expect(summary.llmCallCount).toBe(1);
  });
});

describe("summarizeTools", () => {
  it("groups calls by tool name and computes success rate from event.error", () => {
    const events: Event[] = [
      makeEvent({ event_id: "e1", event_type: "tool_call", data: { tool_name: "search" }, error: null }),
      makeEvent({ event_id: "e2", event_type: "tool_call", data: { tool_name: "search" }, error: "boom" }),
    ];
    const [summary] = summarizeTools(events);
    expect(summary.toolName).toBe("search");
    expect(summary.callCount).toBe(2);
    expect(summary.successRate).toBe(0.5);
  });

  it("computes average latency and total tokens per tool", () => {
    const events: Event[] = [
      makeEvent({ event_id: "e1", event_type: "tool_call", data: { tool_name: "search" }, duration_ms: 100, input_tokens: 10, output_tokens: 5 }),
      makeEvent({ event_id: "e2", event_type: "tool_call", data: { tool_name: "search" }, duration_ms: 300, input_tokens: 20, output_tokens: 5 }),
    ];
    const [summary] = summarizeTools(events);
    expect(summary.averageLatencyMs).toBe(200);
    expect(summary.totalTokens).toBe(40);
  });

  it("sorts tools by call count descending", () => {
    const events: Event[] = [
      makeEvent({ event_id: "e1", event_type: "tool_call", data: { tool_name: "rare" } }),
      makeEvent({ event_id: "e2", event_type: "tool_call", data: { tool_name: "common" } }),
      makeEvent({ event_id: "e3", event_type: "tool_call", data: { tool_name: "common" } }),
    ];
    const tools = summarizeTools(events);
    expect(tools.map((t) => t.toolName)).toEqual(["common", "rare"]);
  });

  it("returns an empty list when there are no tool calls", () => {
    expect(summarizeTools([])).toEqual([]);
  });

  it("defaults an unnamed tool to unknown", () => {
    const events: Event[] = [makeEvent({ event_type: "tool_call", data: {} })];
    const [summary] = summarizeTools(events);
    expect(summary.toolName).toBe("unknown");
  });
});
