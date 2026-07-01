import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Timeline } from "../Timeline";
import type { ChronicleEvent } from "../../types";

const events: ChronicleEvent[] = [
  {
    id: "evt-1",
    run_id: "run-1",
    parent_id: null,
    event_type: "tool_call",
    timestamp: 1700000000,
    payload: { tool_name: "search" },
  },
];

describe("Timeline", () => {
  it("shows an empty state when no events are provided", () => {
    render(<Timeline events={[]} selectedEventId={null} onSelectEvent={vi.fn()} />);
    expect(screen.getByText(/select a run/i)).toBeInTheDocument();
  });

  it("renders an item per event", () => {
    render(<Timeline events={events} selectedEventId={null} onSelectEvent={vi.fn()} />);
    expect(screen.getByText("tool_call")).toBeInTheDocument();
  });
});
