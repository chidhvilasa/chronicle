import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("echarts", () => ({
  init: vi.fn(() => ({ on: vi.fn(), setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
}));

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: {
      getMetricsOverview: vi.fn(),
      listMetricsRuns: vi.fn(),
      getMetricsTrends: vi.fn(),
      listMetricsTools: vi.fn(),
      listMetricsModels: vi.fn(),
    },
  };
});

import { chronicleApi } from "../../../api/client";
import { PerformanceDashboard } from "../PerformanceDashboard";

beforeEach(() => {
  vi.mocked(chronicleApi.getMetricsOverview).mockResolvedValue({
    total_runs: 0,
    total_tokens: 0,
    total_cost_usd: 0,
    avg_run_duration_ms: 0,
    total_errors: 0,
    runs_last_7_days: 0,
    tokens_last_7_days: 0,
    cost_last_7_days: 0,
    most_expensive_run_id: null,
    slowest_run_id: null,
    cost_is_estimate: true,
  });
  vi.mocked(chronicleApi.listMetricsRuns).mockResolvedValue([]);
  vi.mocked(chronicleApi.getMetricsTrends).mockResolvedValue([]);
  vi.mocked(chronicleApi.listMetricsTools).mockResolvedValue([]);
  vi.mocked(chronicleApi.listMetricsModels).mockResolvedValue([]);
});

describe("PerformanceDashboard", () => {
  it("renders every section with empty data without crashing", async () => {
    expect(() => render(<PerformanceDashboard />)).not.toThrow();

    await waitFor(() => {
      expect(chronicleApi.getMetricsOverview).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(chronicleApi.listMetricsTools).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(chronicleApi.listMetricsModels).toHaveBeenCalled();
    });
  });
});
