import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentInspector } from "../AgentInspector";
import type { Event } from "../../../types";

const events: Event[] = [
  {
    event_id: "e1",
    run_id: "run-1",
    timestamp: 1000,
    event_type: "llm_call",
    agent_name: "agent-a",
    duration_ms: 200,
    input_tokens: 10,
    output_tokens: 5,
    data: {},
    error: null,
  },
  {
    event_id: "e2",
    run_id: "run-1",
    timestamp: 1001,
    event_type: "tool_call",
    agent_name: "agent-a",
    duration_ms: 50,
    input_tokens: null,
    output_tokens: null,
    data: { tool_name: "search" },
    error: null,
  },
];

describe("AgentInspector", () => {
  it("renders without crashing and shows an empty state when no agent is selected", () => {
    render(<AgentInspector agentName={null} events={[]} />);
    expect(screen.getByText(/click an agent's lane header/i)).toBeInTheDocument();
  });

  it("renders aggregate stats for the selected agent", () => {
    render(<AgentInspector agentName="agent-a" events={events} />);
    const inspector = screen.getByTestId("agent-inspector");
    expect(inspector.textContent).toContain("LLM calls");
    expect(inspector.textContent).toContain("1");
    expect(inspector.textContent).toContain("Tool calls");
    expect(inspector.textContent).toContain("Total tokens");
    expect(inspector.textContent).toContain("15");
  });

  it("lists tools the agent used with call counts", () => {
    render(<AgentInspector agentName="agent-a" events={events} />);
    expect(screen.getByText("search")).toBeInTheDocument();
    expect(screen.getByText("1 calls")).toBeInTheDocument();
  });

  it("shows an empty tools message when the agent made no tool calls", () => {
    const llmOnly = events.filter((e) => e.event_type === "llm_call");
    render(<AgentInspector agentName="agent-a" events={llmOnly} />);
    expect(screen.getByText(/didn't call any tools/i)).toBeInTheDocument();
  });
});
