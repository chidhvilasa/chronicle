import { render } from "@testing-library/react";
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
    { type: "tool_call", start_time_ms: 0, duration_ms: 100, label: "search", token_usage: null },
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

  it("builds series data for up to 1000 events across many lanes without throwing", () => {
    const manyLanes: TimelineLane[] = Array.from({ length: 20 }, (_, laneIndex) => ({
      agent_name: `agent-${laneIndex}`,
      segments: Array.from({ length: 50 }, (_, segmentIndex) => ({
        type: "tool_call" as const,
        start_time_ms: segmentIndex * 10,
        duration_ms: 5,
        label: `call-${segmentIndex}`,
        token_usage: null,
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
