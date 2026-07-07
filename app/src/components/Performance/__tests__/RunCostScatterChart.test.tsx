import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RunMetrics } from "../../../types";

const { mockChart, mockInit } = vi.hoisted(() => {
  const mockChart = { on: vi.fn(), setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() };
  const mockInit = vi.fn(() => mockChart);
  return { mockChart, mockInit };
});

vi.mock("echarts", () => ({ init: mockInit }));

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { listMetricsRuns: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { useAppStore } from "../../../store/useAppStore";
import { RunCostScatterChart } from "../RunCostScatterChart";

function makeRunMetrics(overrides: Partial<RunMetrics> = {}): RunMetrics {
  return {
    run_id: "run-1",
    total_duration_ms: 1000,
    total_input_tokens: 10,
    total_output_tokens: 20,
    total_tokens: 30,
    estimated_cost_usd: 0.05,
    llm_call_count: 2,
    tool_call_count: 1,
    error_count: 0,
    retry_count: 0,
    avg_llm_latency_ms: 100,
    p95_llm_latency_ms: 120,
    avg_tool_latency_ms: 50,
    p95_tool_latency_ms: 60,
    framework: "langgraph",
    agent_count: 1,
    created_at: 1000,
    cost_is_estimate: true,
    ...overrides,
  };
}

beforeEach(() => {
  mockInit.mockClear();
  mockChart.on.mockClear();
  mockChart.setOption.mockClear();
  vi.mocked(chronicleApi.listMetricsRuns).mockReset();
  useAppStore.setState({ selectedRunId: null });
});

describe("RunCostScatterChart", () => {
  it("renders without crashing for empty data", async () => {
    vi.mocked(chronicleApi.listMetricsRuns).mockResolvedValue([]);
    expect(() => render(<RunCostScatterChart />)).not.toThrow();

    await waitFor(() => expect(mockInit).toHaveBeenCalledTimes(1));
    const option = mockChart.setOption.mock.calls[mockChart.setOption.mock.calls.length - 1]?.[0];
    expect(option.series[0].data).toEqual([]);
  });

  it("colors error runs red and successful runs green", async () => {
    vi.mocked(chronicleApi.listMetricsRuns).mockResolvedValue([
      makeRunMetrics({ run_id: "run-ok", error_count: 0 }),
      makeRunMetrics({ run_id: "run-bad", error_count: 2 }),
    ]);
    render(<RunCostScatterChart />);

    await waitFor(() => expect(mockChart.setOption).toHaveBeenCalled());
    const option = mockChart.setOption.mock.calls[mockChart.setOption.mock.calls.length - 1]?.[0];
    const colorFn = option.series[0].itemStyle.color;
    expect(colorFn({ data: { run: { error_count: 0 } } })).toBe("#2e9e4f");
    expect(colorFn({ data: { run: { error_count: 2 } } })).toBe("#ef4444");
  });

  it("selects the clicked run in the sidebar", async () => {
    vi.mocked(chronicleApi.listMetricsRuns).mockResolvedValue([makeRunMetrics({ run_id: "run-42" })]);
    render(<RunCostScatterChart />);

    await waitFor(() => expect(mockChart.on).toHaveBeenCalled());
    const clickCall = mockChart.on.mock.calls.find((call) => call[0] === "click");
    const handler = clickCall?.[1] as ((params: unknown) => void) | undefined;
    handler?.({ data: { run: { run_id: "run-42" } } });

    expect(useAppStore.getState().selectedRunId).toBe("run-42");
  });
});
