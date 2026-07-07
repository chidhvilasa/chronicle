import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ToolMetrics } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { listMetricsTools: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { useAppStore } from "../../../store/useAppStore";
import { ToolsTable } from "../ToolsTable";

function makeTool(overrides: Partial<ToolMetrics> = {}): ToolMetrics {
  return {
    tool_name: "search",
    call_count: 10,
    avg_latency_ms: 100,
    p95_latency_ms: 200,
    error_rate: 0.02,
    total_tokens: 500,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(chronicleApi.listMetricsTools).mockReset();
  useAppStore.setState({ toolNameFilter: null });
});

describe("ToolsTable", () => {
  it("renders the empty state with no tool calls", async () => {
    vi.mocked(chronicleApi.listMetricsTools).mockResolvedValue([]);
    render(<ToolsTable />);

    await waitFor(() => {
      expect(screen.getByText("No tool calls recorded yet.")).toBeInTheDocument();
    });
  });

  it("renders a row per tool with error rate highlighted above 5%", async () => {
    vi.mocked(chronicleApi.listMetricsTools).mockResolvedValue([
      makeTool({ tool_name: "search", error_rate: 0.1 }),
      makeTool({ tool_name: "calculator", error_rate: 0.01 }),
    ]);
    render(<ToolsTable />);

    await screen.findByText("search");
    const highRateCell = screen.getByText("10.0%");
    expect(highRateCell.className).toContain("perf-error-rate-high");
    const lowRateCell = screen.getByText("1.0%");
    expect(lowRateCell.className).not.toContain("perf-error-rate-high");
  });

  it("sorts by a column when its header is clicked", async () => {
    vi.mocked(chronicleApi.listMetricsTools).mockResolvedValue([
      makeTool({ tool_name: "b-tool", call_count: 5 }),
      makeTool({ tool_name: "a-tool", call_count: 20 }),
    ]);
    render(<ToolsTable />);

    // Default sort is by call_count desc, so a-tool (20) leads.
    await screen.findByText("a-tool");
    let rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("a-tool");

    // Clicking a new column resets to descending; b > a alphabetically.
    fireEvent.click(screen.getByText("Tool Name"));
    rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("b-tool");
  });

  it("sets the tool name filter in the store when a tool name is clicked", async () => {
    vi.mocked(chronicleApi.listMetricsTools).mockResolvedValue([makeTool({ tool_name: "search" })]);
    render(<ToolsTable />);

    const link = await screen.findByText("search");
    fireEvent.click(link);

    expect(useAppStore.getState().toolNameFilter).toBe("search");
  });
});
