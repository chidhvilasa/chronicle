import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TimelineLane } from "../../../types";

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

import { TimelineChart } from "../TimelineChart";

const lane: TimelineLane = {
  agent_name: "agent-a",
  segments: [
    {
      type: "tool_call",
      start_time_ms: 0,
      duration_ms: 100,
      label: "search",
      token_usage: null,
      event_id: "evt-1",
    },
  ],
};

beforeEach(() => {
  mockInit.mockClear();
  mockChart.on.mockClear();
  mockChart.setOption.mockClear();
  mockChart.dispatchAction.mockClear();
  mockChart.resize.mockClear();
  mockChart.dispose.mockClear();
});

describe("TimelineChart", () => {
  it("initializes an echarts instance and sets series data for the given lanes", () => {
    render(<TimelineChart lanes={[lane]} zoom={1} />);

    expect(mockInit).toHaveBeenCalledTimes(1);
    expect(mockChart.setOption).toHaveBeenCalledTimes(1);

    const option = mockChart.setOption.mock.calls[0][0];
    expect(option.yAxis.data).toEqual(["agent-a"]);
    expect(option.series[0].data).toHaveLength(1);
  });

  it("does not crash and still calls setOption with empty data for zero lanes", () => {
    expect(() => render(<TimelineChart lanes={[]} zoom={1} />)).not.toThrow();

    expect(mockInit).toHaveBeenCalledTimes(1);
    const option = mockChart.setOption.mock.calls[0][0];
    expect(option.series[0].data).toEqual([]);
    expect(option.yAxis.data).toEqual([]);
  });

  it("calls onSegmentSelect with the clicked segment", () => {
    const onSegmentSelect = vi.fn();
    render(<TimelineChart lanes={[lane]} zoom={1} onSegmentSelect={onSegmentSelect} />);

    const clickCall = mockChart.on.mock.calls.find((call) => call[0] === "click");
    const handler = clickCall?.[1] as ((params: unknown) => void) | undefined;
    handler?.({ data: { segment: lane.segments[0], agentName: "agent-a" } });

    expect(onSegmentSelect).toHaveBeenCalledWith(lane.segments[0]);
  });

  it("calls onAgentSelect when a yAxis lane label is clicked", () => {
    const onAgentSelect = vi.fn();
    render(<TimelineChart lanes={[lane]} zoom={1} onAgentSelect={onAgentSelect} />);

    const clickCall = mockChart.on.mock.calls.find((call) => call[0] === "click");
    const handler = clickCall?.[1] as ((params: unknown) => void) | undefined;
    handler?.({ componentType: "yAxis", name: "agent-a" });

    expect(onAgentSelect).toHaveBeenCalledWith("agent-a");
  });

  it("enables triggerEvent on the yAxis so lane labels are clickable", () => {
    render(<TimelineChart lanes={[lane]} zoom={1} />);
    const option = mockChart.setOption.mock.calls[0][0];
    expect(option.yAxis.triggerEvent).toBe(true);
  });

  it("dispatches a dataZoom action when the zoom prop changes", () => {
    const { rerender } = render(<TimelineChart lanes={[lane]} zoom={1} />);
    mockChart.dispatchAction.mockClear();

    rerender(<TimelineChart lanes={[lane]} zoom={2} />);

    expect(mockChart.dispatchAction).toHaveBeenCalledWith(
      expect.objectContaining({ type: "dataZoom" })
    );
  });

  it("disposes the chart instance on unmount", () => {
    const { unmount } = render(<TimelineChart lanes={[lane]} zoom={1} />);
    unmount();
    expect(mockChart.dispose).toHaveBeenCalledTimes(1);
  });

  it("shows a Replay from here button when hovering a segment with a snapshot", () => {
    render(<TimelineChart lanes={[lane]} zoom={1} snapshotEventIds={new Set(["evt-1"])} />);

    const mouseoverCall = mockChart.on.mock.calls.find((call) => call[0] === "mouseover");
    const handler = mouseoverCall?.[2] as ((params: unknown) => void) | undefined;
    act(() => {
      handler?.({ data: { segment: lane.segments[0], agentName: "agent-a" }, event: { offsetX: 10, offsetY: 20 } });
    });

    expect(screen.getByTestId("replay-from-here-button")).toBeInTheDocument();
  });

  it("does not show a Replay from here button for a segment without a snapshot", () => {
    render(<TimelineChart lanes={[lane]} zoom={1} snapshotEventIds={new Set(["some-other-event"])} />);

    const mouseoverCall = mockChart.on.mock.calls.find((call) => call[0] === "mouseover");
    const handler = mouseoverCall?.[2] as ((params: unknown) => void) | undefined;
    act(() => {
      handler?.({ data: { segment: lane.segments[0], agentName: "agent-a" }, event: { offsetX: 10, offsetY: 20 } });
    });

    expect(screen.queryByTestId("replay-from-here-button")).not.toBeInTheDocument();
  });

  it("calls onReplayClick with the hovered segment when the replay button is clicked", () => {
    const onReplayClick = vi.fn();
    render(
      <TimelineChart
        lanes={[lane]}
        zoom={1}
        snapshotEventIds={new Set(["evt-1"])}
        onReplayClick={onReplayClick}
      />
    );

    const mouseoverCall = mockChart.on.mock.calls.find((call) => call[0] === "mouseover");
    const handler = mouseoverCall?.[2] as ((params: unknown) => void) | undefined;
    act(() => {
      handler?.({ data: { segment: lane.segments[0], agentName: "agent-a" }, event: { offsetX: 10, offsetY: 20 } });
    });

    screen.getByTestId("replay-from-here-button").click();
    expect(onReplayClick).toHaveBeenCalledWith(lane.segments[0]);
  });

  it("builds series data for up to 1000 events across many lanes without throwing", () => {
    const manyLanes: TimelineLane[] = Array.from({ length: 20 }, (_, laneIndex) => ({
      agent_name: `agent-${laneIndex}`,
      segments: Array.from({ length: 50 }, (_, segmentIndex) => ({
        type: "tool_call" as const,
        start_time_ms: segmentIndex * 10,
        duration_ms: 5,
        label: `call-${segmentIndex}`,
        token_usage: null,
        event_id: `evt-${laneIndex}-${segmentIndex}`,
      })),
    }));

    const start = performance.now();
    expect(() => render(<TimelineChart lanes={manyLanes} zoom={1} />)).not.toThrow();
    const elapsedMs = performance.now() - start;

    const option = mockChart.setOption.mock.calls[0][0];
    expect(option.series[0].data).toHaveLength(1000);
    expect(elapsedMs).toBeLessThan(2000);
  });
});
