import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "../../../store/useAppStore";
import { chronicleApi } from "../../../api/client";
import type { Event, Run } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { listRunEvents: vi.fn() },
  };
});

import { Diff } from "../Diff";

const initialState = useAppStore.getState();

function makeRun(runId: string): Run {
  return {
    run_id: runId,
    started_at: 1000,
    finished_at: 1030,
    framework: null,
    agent_count: 1,
    total_tokens: 100,
    total_cost_usd: 0,
    status: "running",
    metadata: {},
  };
}

function makeEvents(count: number, runId: string): Event[] {
  return Array.from({ length: count }, (_, i) => ({
    event_id: `${runId}-e${i}`,
    run_id: runId,
    timestamp: 1000 + i,
    event_type: "tool_call",
    agent_name: "agent-a",
    duration_ms: 100,
    input_tokens: null,
    output_tokens: null,
    data: {},
    error: null,
  }));
}

beforeEach(() => {
  useAppStore.setState(initialState, true);
  useAppStore.getState().setRuns([makeRun("run-1"), makeRun("run-2")]);
  vi.mocked(chronicleApi.listRunEvents).mockReset();
});

describe("Diff", () => {
  it("prompts for two runs when none are selected", () => {
    render(<Diff />);
    expect(screen.getByText(/select two runs to compare/i)).toBeInTheDocument();
  });

  it("renders the summary and event diff once both runs are selected", async () => {
    vi.mocked(chronicleApi.listRunEvents).mockImplementation((runId: string) =>
      Promise.resolve(makeEvents(2, runId))
    );
    render(<Diff />);

    fireEvent.change(screen.getByLabelText("Run A"), { target: { value: "run-1" } });
    fireEvent.change(screen.getByLabelText("Run B"), { target: { value: "run-2" } });

    await waitFor(() => {
      expect(screen.getByTestId("diff-summary")).toBeInTheDocument();
    });
    expect(screen.getByTestId("diff-event-list")).toBeInTheDocument();
  });

  it("renders correctly with two mock runs of different lengths", async () => {
    vi.mocked(chronicleApi.listRunEvents).mockImplementation((runId: string) =>
      Promise.resolve(makeEvents(runId === "run-1" ? 2 : 5, runId))
    );
    render(<Diff />);

    fireEvent.change(screen.getByLabelText("Run A"), { target: { value: "run-1" } });
    fireEvent.change(screen.getByLabelText("Run B"), { target: { value: "run-2" } });

    await waitFor(() => {
      expect(screen.getByTestId("diff-event-list")).toBeInTheDocument();
    });
    expect(document.querySelectorAll(".diff-row")).toHaveLength(5);
    expect(document.querySelectorAll(".diff-row-missing_a")).toHaveLength(3);
  });

  it("shows a warning but still renders when either run has more than 500 events", async () => {
    vi.mocked(chronicleApi.listRunEvents).mockImplementation((runId: string) =>
      Promise.resolve(makeEvents(runId === "run-1" ? 600 : 2, runId))
    );
    render(<Diff />);

    fireEvent.change(screen.getByLabelText("Run A"), { target: { value: "run-1" } });
    fireEvent.change(screen.getByLabelText("Run B"), { target: { value: "run-2" } });

    await waitFor(() => {
      expect(screen.getByTestId("diff-large-warning")).toBeInTheDocument();
    });
    expect(screen.getByTestId("diff-event-list")).toBeInTheDocument();
  });

  it("shows a human-readable error when fetching events fails", async () => {
    vi.mocked(chronicleApi.listRunEvents).mockRejectedValue(new Error("boom"));
    render(<Diff />);

    fireEvent.change(screen.getByLabelText("Run A"), { target: { value: "run-1" } });
    fireEvent.change(screen.getByLabelText("Run B"), { target: { value: "run-2" } });

    await waitFor(() => {
      expect(screen.getByText(/could not load runs to diff/i)).toBeInTheDocument();
    });
  });
});
