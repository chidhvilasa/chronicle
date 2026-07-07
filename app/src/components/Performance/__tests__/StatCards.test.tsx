import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MetricsOverview } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { getMetricsOverview: vi.fn(), listMetricsRuns: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { StatCards } from "../StatCards";

function makeOverview(overrides: Partial<MetricsOverview> = {}): MetricsOverview {
  return {
    total_runs: 10,
    total_tokens: 123456,
    total_cost_usd: 4.5,
    avg_run_duration_ms: 2500,
    total_errors: 0,
    runs_last_7_days: 3,
    tokens_last_7_days: 1000,
    cost_last_7_days: 0.5,
    most_expensive_run_id: "run-1",
    slowest_run_id: "run-2",
    cost_is_estimate: true,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(chronicleApi.getMetricsOverview).mockReset();
  vi.mocked(chronicleApi.listMetricsRuns).mockReset();
  vi.mocked(chronicleApi.listMetricsRuns).mockResolvedValue([]);
});

describe("StatCards", () => {
  it("renders all six stat cards with formatted values", async () => {
    vi.mocked(chronicleApi.getMetricsOverview).mockResolvedValue(makeOverview());
    render(<StatCards />);

    await waitFor(() => {
      expect(screen.getByText("Total Runs")).toBeInTheDocument();
    });
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("123.5K")).toBeInTheDocument();
    expect(screen.getByText("$4.50")).toBeInTheDocument();
    expect(screen.getByText("2.5s")).toBeInTheDocument();
  });

  it("shows total errors in red text when above zero", async () => {
    vi.mocked(chronicleApi.getMetricsOverview).mockResolvedValue(makeOverview({ total_errors: 5 }));
    render(<StatCards />);

    const value = await screen.findByText("5");
    expect(value.className).toContain("perf-stat-value-error");
  });

  it("shows a retry button on fetch failure", async () => {
    vi.mocked(chronicleApi.getMetricsOverview).mockRejectedValue(new Error("network down"));
    render(<StatCards />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    });
  });
});
