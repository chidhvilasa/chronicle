import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Inspector } from "../Inspector";
import type { ChronicleEvent } from "../../types";

const event: ChronicleEvent = {
  id: "evt-1",
  run_id: "run-1",
  parent_id: null,
  event_type: "error",
  timestamp: 1700000000,
  payload: { message: "boom" },
};

describe("Inspector", () => {
  it("shows an empty state when no event is selected", () => {
    render(<Inspector event={null} />);
    expect(screen.getByText(/select an event/i)).toBeInTheDocument();
  });

  it("renders the event payload when an event is selected", () => {
    render(<Inspector event={event} />);
    expect(screen.getByText("error")).toBeInTheDocument();
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });
});
