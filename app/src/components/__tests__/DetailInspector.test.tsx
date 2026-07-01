import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { DetailInspector } from "../DetailInspector";
import { useAppStore } from "../../store/useAppStore";
import type { Event, TimelineSegment } from "../../types";

const initialState = useAppStore.getState();

beforeEach(() => {
  useAppStore.setState(initialState, true);
});

const event: Event = {
  event_id: "evt-1",
  run_id: "run-1",
  timestamp: 1700000000,
  event_type: "error",
  agent_name: "agent-a",
  duration_ms: null,
  input_tokens: null,
  output_tokens: null,
  data: {},
  error: "boom",
};

const segment: TimelineSegment = {
  type: "llm_call",
  start_time_ms: 0,
  duration_ms: 250.5,
  label: "gpt-4o",
  token_usage: { input_tokens: 10, output_tokens: 5 },
};

describe("DetailInspector", () => {
  it("shows an empty state when nothing is selected", () => {
    render(<DetailInspector />);
    expect(screen.getByText(/select an event or segment/i)).toBeInTheDocument();
  });

  it("renders event details when an event is selected", () => {
    useAppStore.getState().setSelectedDetail(event);
    render(<DetailInspector />);

    expect(screen.getByText("error")).toBeInTheDocument();
    expect(screen.getByText("evt-1")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("renders segment details when a segment is selected", () => {
    useAppStore.getState().setSelectedDetail(segment);
    render(<DetailInspector />);

    expect(screen.getByText("llm_call")).toBeInTheDocument();
    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("250.5ms")).toBeInTheDocument();
  });

  it("collapses and expands via the toggle button", () => {
    useAppStore.getState().setSelectedDetail(event);
    render(<DetailInspector />);

    const toggle = screen.getByRole("button", { name: /collapse detail inspector/i });
    fireEvent.click(toggle);

    expect(screen.getByTestId("detail-inspector")).toHaveClass("collapsed");
    expect(screen.queryByText("error")).not.toBeInTheDocument();
  });
});
