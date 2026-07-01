import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TimelinePanel } from "../TimelinePanel";
import { useAppStore } from "../../../store/useAppStore";
import { chronicleApi } from "../../../api/client";
import type { Timeline } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { getRunTimeline: vi.fn() },
  };
});

const initialState = useAppStore.getState();

const timeline: Timeline = {
  run_id: "run-1",
  lanes: [
    {
      agent_name: "agent-a",
      segments: [
        {
          type: "tool_call",
          start_time_ms: 0,
          duration_ms: 120,
          label: "search",
          token_usage: null,
        },
      ],
    },
  ],
};

beforeEach(() => {
  useAppStore.setState(initialState, true);
  vi.mocked(chronicleApi.getRunTimeline).mockReset();
});

describe("TimelinePanel", () => {
  it("prompts for a run when none is selected", () => {
    render(<TimelinePanel />);
    expect(screen.getByText(/select a run/i)).toBeInTheDocument();
  });

  it("renders lanes and segments for the selected run", async () => {
    vi.mocked(chronicleApi.getRunTimeline).mockResolvedValue(timeline);
    useAppStore.getState().selectRun("run-1");
    render(<TimelinePanel />);

    await waitFor(() => {
      expect(screen.getByText("agent-a")).toBeInTheDocument();
    });
    expect(screen.getByText("search")).toBeInTheDocument();
  });

  it("selects a segment as the detail item when clicked", async () => {
    vi.mocked(chronicleApi.getRunTimeline).mockResolvedValue(timeline);
    useAppStore.getState().selectRun("run-1");
    render(<TimelinePanel />);

    const segment = await screen.findByText("search");
    segment.click();

    expect(useAppStore.getState().selectedDetail).toEqual(timeline.lanes[0].segments[0]);
  });
});
