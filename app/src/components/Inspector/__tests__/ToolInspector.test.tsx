import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToolInspector } from "../ToolInspector";
import type { Event } from "../../../types";

const events: Event[] = [
  {
    event_id: "e1",
    run_id: "run-1",
    timestamp: 1000,
    event_type: "tool_call",
    agent_name: "agent-a",
    duration_ms: 100,
    input_tokens: 5,
    output_tokens: 2,
    data: { tool_name: "search", arguments: { query: "weather" }, result: { temp: 72 } },
    error: null,
  },
  {
    event_id: "e2",
    run_id: "run-1",
    timestamp: 1001,
    event_type: "tool_call",
    agent_name: "agent-a",
    duration_ms: 200,
    input_tokens: null,
    output_tokens: null,
    data: { tool_name: "search" },
    error: "timeout",
  },
];

describe("ToolInspector", () => {
  it("renders without crashing and shows an empty state when there are no tool calls", () => {
    render(<ToolInspector events={[]} selectedToolName={null} onSelectTool={vi.fn()} />);
    expect(screen.getByText(/no tool calls recorded/i)).toBeInTheDocument();
  });

  it("renders a table row per tool with call count and success rate", () => {
    render(<ToolInspector events={events} selectedToolName={null} onSelectTool={vi.fn()} />);
    expect(screen.getByTestId("tool-inspector")).toBeInTheDocument();
    expect(screen.getByText("search")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("calls onSelectTool when a tool row is clicked", () => {
    const onSelectTool = vi.fn();
    render(<ToolInspector events={events} selectedToolName={null} onSelectTool={onSelectTool} />);
    fireEvent.click(screen.getByText("search"));
    expect(onSelectTool).toHaveBeenCalledWith("search");
  });

  it("shows the per-call list with timestamp, args, result, duration, and status when a tool is selected", () => {
    render(<ToolInspector events={events} selectedToolName="search" onSelectTool={vi.fn()} />);
    const callList = screen.getByTestId("tool-call-list");
    expect(callList.textContent).toContain("query");
    expect(callList.textContent).toContain("temp");
    expect(callList.textContent).toContain("success");
    expect(callList.textContent).toContain("error");
  });
});
