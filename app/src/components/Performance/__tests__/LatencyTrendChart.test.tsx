import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockChart, mockInit } = vi.hoisted(() => {
  const mockChart = { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() };
  const mockInit = vi.fn(() => mockChart);
  return { mockChart, mockInit };
});

vi.mock("echarts", () => ({ init: mockInit }));

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { getMetricsTrends: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { LatencyTrendChart } from "../LatencyTrendChart";

beforeEach(() => {
  mockInit.mockClear();
  mockChart.setOption.mockClear();
  vi.mocked(chronicleApi.getMetricsTrends).mockReset();
});

describe("LatencyTrendChart", () => {
  it("renders without crashing for empty data", async () => {
    vi.mocked(chronicleApi.getMetricsTrends).mockResolvedValue([]);
    expect(() => render(<LatencyTrendChart range="7D" />)).not.toThrow();

    await waitFor(() => expect(mockInit).toHaveBeenCalledTimes(1));
  });

  it("fetches both avg and p95 latency series and plots them", async () => {
    vi.mocked(chronicleApi.getMetricsTrends).mockImplementation((_period, _metric, stat) =>
      Promise.resolve(
        stat === "p95" ? [{ bucket: "2026-07-01", value: 500 }] : [{ bucket: "2026-07-01", value: 100 }]
      )
    );
    render(<LatencyTrendChart range="7D" />);

    await waitFor(() => {
      expect(mockChart.setOption.mock.calls[mockChart.setOption.mock.calls.length - 1]?.[0].series[0].data).toEqual([100]);
    });
    const option = mockChart.setOption.mock.calls[mockChart.setOption.mock.calls.length - 1]?.[0];
    expect(option.series[0].data).toEqual([100]);
    expect(option.series[1].data).toEqual([500]);
    expect(chronicleApi.getMetricsTrends).toHaveBeenCalledWith("day", "latency", "avg");
    expect(chronicleApi.getMetricsTrends).toHaveBeenCalledWith("day", "latency", "p95");
  });
});
