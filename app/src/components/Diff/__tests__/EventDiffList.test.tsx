import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EventDiffList } from "../EventDiffList";
import { buildEventDiffRows } from "../computeDiff";
import type { Event } from "../../../types";

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

describe("EventDiffList", () => {
  it("renders without crashing and shows an empty message for no rows", () => {
    expect(() => render(<EventDiffList rows={[]} />)).not.toThrow();
    expect(screen.getByText(/events to compare/i)).toBeInTheDocument();
  });

  it("does not highlight rows that are identical", () => {
    const a = makeEvent({ event_id: "a1", duration_ms: 100 });
    const b = makeEvent({ event_id: "b1", duration_ms: 100 });
    render(<EventDiffList rows={buildEventDiffRows([a], [b])} />);
    expect(document.querySelector(".diff-row-same")).toBeInTheDocument();
    expect(document.querySelector(".diff-row-different")).not.toBeInTheDocument();
  });

  it("highlights rows with differing fields as yellow (different)", () => {
    const a = makeEvent({ event_id: "a1", duration_ms: 100 });
    const b = makeEvent({ event_id: "b1", duration_ms: 999 });
    render(<EventDiffList rows={buildEventDiffRows([a], [b])} />);
    expect(document.querySelector(".diff-row-different")).toBeInTheDocument();
  });

  it("labels a row missing from run A in red", () => {
    const b = makeEvent({ event_id: "b1" });
    render(<EventDiffList rows={buildEventDiffRows([], [b])} />);
    expect(document.querySelector(".diff-row-missing_a")).toBeInTheDocument();
    expect(screen.getByText(/missing in Run A/i)).toBeInTheDocument();
  });

  it("labels a row missing from run B in red", () => {
    const a = makeEvent({ event_id: "a1" });
    render(<EventDiffList rows={buildEventDiffRows([a], [])} />);
    expect(document.querySelector(".diff-row-missing_b")).toBeInTheDocument();
    expect(screen.getByText(/missing in Run B/i)).toBeInTheDocument();
  });

  it("renders a prompt diff for llm_call events at the same position", () => {
    const a = makeEvent({ event_id: "a1", event_type: "llm_call", data: { prompt: "hello" } });
    const b = makeEvent({ event_id: "b1", event_type: "llm_call", data: { prompt: "hallo" } });
    render(<EventDiffList rows={buildEventDiffRows([a], [b])} />);
    expect(screen.getByTestId("prompt-diff")).toBeInTheDocument();
  });

  it("does not render a prompt diff for non-llm_call events", () => {
    const a = makeEvent({ event_id: "a1", event_type: "tool_call" });
    const b = makeEvent({ event_id: "b1", event_type: "tool_call" });
    render(<EventDiffList rows={buildEventDiffRows([a], [b])} />);
    expect(screen.queryByTestId("prompt-diff")).not.toBeInTheDocument();
  });

  it("handles runs of very different lengths without crashing", () => {
    const eventsA = Array.from({ length: 3 }, (_, i) => makeEvent({ event_id: `a${i}` }));
    const eventsB = Array.from({ length: 50 }, (_, i) => makeEvent({ event_id: `b${i}` }));
    expect(() =>
      render(<EventDiffList rows={buildEventDiffRows(eventsA, eventsB)} />)
    ).not.toThrow();
    expect(document.querySelectorAll(".diff-row-missing_a").length).toBe(47);
  });
});
