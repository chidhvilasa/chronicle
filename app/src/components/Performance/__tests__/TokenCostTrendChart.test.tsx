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
import { TokenCostTrendChart } from "../TokenCostTrendChart";

beforeEach(() => {
  mockInit.mockClear();
  mockChart.setOption.mockClear();
  mockChart.dispose.mockClear();
  vi.mocked(chronicleApi.getMetricsTrends).mockReset();
});

describe("TokenCostTrendChart", () => {
  it("renders without crashing and sets chart options for empty data", async () => {
    vi.mocked(chronicleApi.getMetricsTrends).mockResolvedValue([]);
    expect(() => render(<TokenCostTrendChart range="30D" />)).not.toThrow();

    await waitFor(() => {
      expect(mockInit).toHaveBeenCalledTimes(1);
    });
  });

  it("plots tokens and cost as two series with the cost line dashed", async () => {
    vi.mocked(chronicleApi.getMetricsTrends).mockImplementation((_period, metric) =>
      Promise.resolve(
        metric === "tokens"
          ? [{ bucket: "2026-07-01", value: 100 }]
          : [{ bucket: "2026-07-01", value: 0.5 }]
      )
    );
    render(<TokenCostTrendChart range="30D" />);

    await waitFor(() => {
      expect(mockChart.setOption.mock.calls[mockChart.setOption.mock.calls.length - 1]?.[0].series[0].data).toEqual([100]);
    });
    const option = mockChart.setOption.mock.calls[mockChart.setOption.mock.calls.length - 1]?.[0];
    expect(option.series[0].data).toEqual([100]);
    expect(option.series[1].data).toEqual([0.5]);
    expect(option.series[1].lineStyle.type).toBe("dashed");
  });

  it("disposes the chart instance on unmount", async () => {
    vi.mocked(chronicleApi.getMetricsTrends).mockResolvedValue([]);
    const { unmount } = render(<TokenCostTrendChart range="30D" />);
    await waitFor(() => expect(mockInit).toHaveBeenCalled());

    unmount();
    expect(mockChart.dispose).toHaveBeenCalledTimes(1);
  });
});
