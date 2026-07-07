import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelMetrics } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { listMetricsModels: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { ModelsTable } from "../ModelsTable";

function makeModel(overrides: Partial<ModelMetrics> = {}): ModelMetrics {
  return {
    model_name: "gpt-4",
    call_count: 12,
    avg_latency_ms: 300,
    total_input_tokens: 100,
    total_output_tokens: 200,
    total_cost_usd: 1.23,
    cost_is_estimate: true,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(chronicleApi.listMetricsModels).mockReset();
});

describe("ModelsTable", () => {
  it("renders a row per model when model names are captured", async () => {
    vi.mocked(chronicleApi.listMetricsModels).mockResolvedValue([makeModel()]);
    render(<ModelsTable />);

    await waitFor(() => {
      expect(screen.getByText("gpt-4")).toBeInTheDocument();
    });
    expect(screen.getByText("$1.23 (est.)")).toBeInTheDocument();
  });

  it("shows the upgrade fallback when every model is 'unknown'", async () => {
    vi.mocked(chronicleApi.listMetricsModels).mockResolvedValue([makeModel({ model_name: "unknown" })]);
    render(<ModelsTable />);

    await waitFor(() => {
      expect(screen.getByTestId("models-table-fallback")).toBeInTheDocument();
    });
  });

  it("shows the upgrade fallback when there are no llm_call events at all", async () => {
    vi.mocked(chronicleApi.listMetricsModels).mockResolvedValue([]);
    render(<ModelsTable />);

    await waitFor(() => {
      expect(screen.getByTestId("models-table-fallback")).toBeInTheDocument();
    });
  });
});
