import type { Event } from "../../types";

export interface ToolUsageCount {
  toolName: string;
  callCount: number;
}

export interface AgentSummary {
  agentName: string;
  llmCallCount: number;
  toolCallCount: number;
  totalTokens: number;
  errorCount: number;
  averageLlmLatencyMs: number | null;
  toolUsage: ToolUsageCount[];
}

export interface ToolSummary {
  toolName: string;
  callCount: number;
  successRate: number;
  averageLatencyMs: number | null;
  totalTokens: number;
  calls: Event[];
}

function eventTokens(event: Event): number {
  return (event.input_tokens ?? 0) + (event.output_tokens ?? 0);
}

function average(values: number[]): number | null {
  return values.length > 0 ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function toolNameOf(event: Event): string {
  const name = event.data["tool_name"];
  return typeof name === "string" && name.length > 0 ? name : "unknown";
}

/** Summarizes one agent's activity across a run: call counts, tokens, errors, and tool usage. */
export function summarizeAgent(events: Event[], agentName: string): AgentSummary {
  const agentEvents = events.filter((event) => (event.agent_name ?? "unknown") === agentName);
  const llmCalls = agentEvents.filter((event) => event.event_type === "llm_call");
  const toolCalls = agentEvents.filter((event) => event.event_type === "tool_call");
  const errors = agentEvents.filter((event) => event.event_type === "error");

  const toolUsageCounts = new Map<string, number>();
  for (const call of toolCalls) {
    const toolName = toolNameOf(call);
    toolUsageCounts.set(toolName, (toolUsageCounts.get(toolName) ?? 0) + 1);
  }

  return {
    agentName,
    llmCallCount: llmCalls.length,
    toolCallCount: toolCalls.length,
    totalTokens: agentEvents.reduce((sum, event) => sum + eventTokens(event), 0),
    errorCount: errors.length,
    averageLlmLatencyMs: average(
      llmCalls.map((event) => event.duration_ms).filter((ms): ms is number => ms !== null)
    ),
    toolUsage: Array.from(toolUsageCounts, ([toolName, callCount]) => ({ toolName, callCount })).sort(
      (a, b) => b.callCount - a.callCount
    ),
  };
}

/** Summarizes every tool used in a run: call count, success rate, latency, and tokens. */
export function summarizeTools(events: Event[]): ToolSummary[] {
  const toolCalls = events.filter((event) => event.event_type === "tool_call");
  const byTool = new Map<string, Event[]>();
  for (const call of toolCalls) {
    const toolName = toolNameOf(call);
    const calls = byTool.get(toolName) ?? [];
    calls.push(call);
    byTool.set(toolName, calls);
  }

  return Array.from(byTool, ([toolName, calls]) => {
    const successCount = calls.filter((call) => call.error === null).length;
    return {
      toolName,
      callCount: calls.length,
      successRate: calls.length > 0 ? successCount / calls.length : 0,
      averageLatencyMs: average(
        calls.map((call) => call.duration_ms).filter((ms): ms is number => ms !== null)
      ),
      totalTokens: calls.reduce((sum, call) => sum + eventTokens(call), 0),
      calls,
    };
  }).sort((a, b) => b.callCount - a.callCount);
}
