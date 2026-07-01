import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EventInspector } from "../EventInspector";
import type { Event, TimelineSegment } from "../../../types";

const llmEvent: Event = {
  event_id: "evt-1",
  run_id: "run-1",
  timestamp: 1700000000,
  event_type: "llm_call",
  agent_name: "agent-a",
  duration_ms: 250,
  input_tokens: 10,
  output_tokens: 5,
  data: { prompt: "What's the weather?", completion: "It's sunny." },
  error: null,
};

const toolEvent: Event = {
  event_id: "evt-2",
  run_id: "run-1",
  timestamp: 1700000000,
  event_type: "tool_call",
  agent_name: "agent-a",
  duration_ms: 50,
  input_tokens: null,
  output_tokens: null,
  data: { tool_name: "search", arguments: { query: "weather" }, result: { temp: 72 } },
  error: null,
};

const errorEvent: Event = {
  event_id: "evt-3",
  run_id: "run-1",
  timestamp: 1700000000,
  event_type: "error",
  agent_name: "agent-a",
  duration_ms: null,
  input_tokens: null,
  output_tokens: null,
  data: { traceback: "Traceback (most recent call last)..." },
  error: "boom",
};

describe("EventInspector", () => {
  it("renders without crashing and shows an empty state when nothing is selected", () => {
    render(<EventInspector detail={null} events={[]} />);
    expect(screen.getByText(/select an event or segment/i)).toBeInTheDocument();
  });

  it("shows the full prompt and response for an llm_call event", () => {
    render(<EventInspector detail={llmEvent} events={[llmEvent]} />);
    expect(screen.getByTestId("llm-prompt")).toHaveTextContent("What's the weather?");
    expect(screen.getByTestId("llm-response")).toHaveTextContent("It's sunny.");
  });

  it("shows tool name, formatted arguments/result, and success status for a tool_call event", () => {
    render(<EventInspector detail={toolEvent} events={[toolEvent]} />);
    expect(screen.getByText("search")).toBeInTheDocument();
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText(/"query": "weather"/)).toBeInTheDocument();
    expect(screen.getByText(/"temp": 72/)).toBeInTheDocument();
  });

  it("shows the error message, traceback, and agent for an error event", () => {
    render(<EventInspector detail={errorEvent} events={[errorEvent]} />);
    expect(screen.getByText("boom")).toBeInTheDocument();
    expect(screen.getByText(/traceback/i)).toBeInTheDocument();
    expect(screen.getAllByText("agent-a").length).toBeGreaterThan(0);
  });

  it("resolves a timeline segment to its full event via event_id", () => {
    const segment: TimelineSegment = {
      type: "llm_call",
      start_time_ms: 0,
      duration_ms: 250,
      label: "gpt-4o",
      token_usage: { input_tokens: 10, output_tokens: 5 },
      event_id: "evt-1",
    };
    render(<EventInspector detail={segment} events={[llmEvent]} />);
    expect(screen.getByTestId("llm-prompt")).toHaveTextContent("What's the weather?");
  });

  it("falls back to segment-only detail when the event can't be resolved", () => {
    const segment: TimelineSegment = {
      type: "waiting",
      start_time_ms: 0,
      duration_ms: 500,
      label: "waiting",
      token_usage: null,
      event_id: null,
    };
    render(<EventInspector detail={segment} events={[]} />);
    expect(screen.getByRole("heading", { name: "waiting" })).toBeInTheDocument();
    expect(screen.getByText("500ms")).toBeInTheDocument();
  });
});
