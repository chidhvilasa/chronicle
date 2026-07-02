import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Timeline as TimelineData } from "../../../types";

const { mockChart, mockInit } = vi.hoisted(() => {
  const mockChart = {
    on: vi.fn(),
    setOption: vi.fn(),
    dispatchAction: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  };
  const mockInit = vi.fn(() => mockChart);
  return { mockChart, mockInit };
});

vi.mock("echarts", () => ({
  init: mockInit,
  graphic: { clipRectByRect: vi.fn() },
}));

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: {
      getRunTimeline: vi.fn(),
      listRunSnapshots: vi.fn(),
      getSnapshot: vi.fn(),
      replay: vi.fn(),
      listRuns: vi.fn(),
    },
  };
});

import { Timeline } from "../Timeline";
import { chronicleApi, ChronicleApiError } from "../../../api/client";

const timelineData: TimelineData = {
  run_id: "run-1",
  lanes: [
    {
      agent_name: "agent-a",
      segments: [
        {
          type: "llm_call",
          start_time_ms: 0,
          duration_ms: 100,
          label: "gpt-4o",
          token_usage: { input_tokens: 10, output_tokens: 5 },
          event_id: "evt-1",
        },
        {
          type: "error",
          start_time_ms: 200,
          duration_ms: 0,
          label: "boom",
          token_usage: null,
          event_id: "evt-2",
        },
      ],
    },
  ],
};

beforeEach(() => {
  vi.mocked(chronicleApi.getRunTimeline).mockReset();
  vi.mocked(chronicleApi.listRunSnapshots).mockReset().mockResolvedValue([]);
  mockInit.mockClear();
  mockChart.on.mockClear();
  mockChart.setOption.mockClear();
  mockChart.dispatchAction.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Timeline", () => {
  it("prompts for a run when none is selected", () => {
    render(<Timeline runId={null} />);
    expect(screen.getByText(/select a run to see its timeline/i)).toBeInTheDocument();
  });

  it("shows a loading skeleton while the timeline fetch is in flight", () => {
    vi.mocked(chronicleApi.getRunTimeline).mockReturnValue(new Promise(() => {}));
    render(<Timeline runId="run-1" />);
    expect(screen.getByTestId("timeline-skeleton")).toBeInTheDocument();
  });

  it("shows the empty state for a run with zero events, with no console errors", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(chronicleApi.getRunTimeline).mockResolvedValue({ run_id: "run-1", lanes: [] });

    render(<Timeline runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByText(/no events recorded for this run/i)).toBeInTheDocument();
    });
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("shows a human-readable error with a retry button, and retries on click", async () => {
    vi.mocked(chronicleApi.getRunTimeline).mockRejectedValue(
      new ChronicleApiError("Could not reach the Chronicle server. Is it running?")
    );
    render(<Timeline runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByText(/could not reach the chronicle server/i)).toBeInTheDocument();
    });

    vi.mocked(chronicleApi.getRunTimeline).mockResolvedValue(timelineData);
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => {
      expect(screen.getByTestId("timeline-root")).toBeInTheDocument();
    });
    expect(chronicleApi.getRunTimeline).toHaveBeenCalledTimes(2);
  });

  it("renders the token summary, controls, and chart for a populated run", async () => {
    vi.mocked(chronicleApi.getRunTimeline).mockResolvedValue(timelineData);
    render(<Timeline runId="run-1" />);

    await waitFor(() => {
      expect(mockChart.setOption).toHaveBeenCalled();
    });
    expect(screen.getByTestId("token-usage-summary")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-controls")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-chart")).toBeInTheDocument();

    const option = mockChart.setOption.mock.calls[mockChart.setOption.mock.calls.length - 1]?.[0];
    expect(option.series[0].data).toHaveLength(2);
  });

  it("applies the segment filter down to the chart data", async () => {
    vi.mocked(chronicleApi.getRunTimeline).mockResolvedValue(timelineData);
    render(<Timeline runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByTestId("timeline-root")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Filter segments"), { target: { value: "errors" } });

    await waitFor(() => {
      const option = mockChart.setOption.mock.calls[mockChart.setOption.mock.calls.length - 1]?.[0];
      expect(option.series[0].data).toHaveLength(1);
    });
  });

  it("dispatches a zoom action when the zoom-in button is clicked", async () => {
    vi.mocked(chronicleApi.getRunTimeline).mockResolvedValue(timelineData);
    render(<Timeline runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByTestId("timeline-root")).toBeInTheDocument();
    });
    mockChart.dispatchAction.mockClear();

    fireEvent.click(screen.getByLabelText("Zoom in"));

    expect(mockChart.dispatchAction).toHaveBeenCalledWith(
      expect.objectContaining({ type: "dataZoom" })
    );
  });

  it("opens the replay modal when a Replay from here button is clicked", async () => {
    vi.mocked(chronicleApi.getRunTimeline).mockResolvedValue(timelineData);
    vi.mocked(chronicleApi.listRunSnapshots).mockResolvedValue([
      { snapshot_id: "snap-1", step_index: 2, timestamp: 1000, agent_name: "agent-a", event_id: "evt-1" },
    ]);
    vi.mocked(chronicleApi.getSnapshot).mockReturnValue(new Promise(() => {}));
    render(<Timeline runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByTestId("timeline-root")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(chronicleApi.listRunSnapshots).toHaveBeenCalledWith("run-1");
    });

    const mouseoverCall = mockChart.on.mock.calls.find((call) => call[0] === "mouseover");
    const handler = mouseoverCall?.[2] as ((params: unknown) => void) | undefined;
    act(() => {
      handler?.({
        data: { segment: timelineData.lanes[0].segments[0], agentName: "agent-a" },
        event: { offsetX: 5, offsetY: 5 },
      });
    });

    fireEvent.click(screen.getByTestId("replay-from-here-button"));

    expect(screen.getByTestId("replay-modal")).toBeInTheDocument();
  });
});
