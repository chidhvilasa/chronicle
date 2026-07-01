import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DiffSummary } from "../DiffSummary";
import type { RunStats } from "../computeDiff";

const statsA: RunStats = {
  durationSeconds: 30,
  totalTokens: 1000,
  totalCostUsd: 0.01,
  errorCount: 2,
  toolCallCount: 5,
};

const fasterStatsB: RunStats = {
  durationSeconds: 10,
  totalTokens: 500,
  totalCostUsd: 0.005,
  errorCount: 0,
  toolCallCount: 3,
};

const slowerStatsB: RunStats = {
  durationSeconds: 60,
  totalTokens: 2000,
  totalCostUsd: 0.02,
  errorCount: 5,
  toolCallCount: 8,
};

describe("DiffSummary", () => {
  it("renders all five comparison rows", () => {
    render(<DiffSummary statsA={statsA} statsB={fasterStatsB} />);
    const table = screen.getByTestId("diff-summary");
    expect(table.textContent).toContain("Total duration");
    expect(table.textContent).toContain("Total tokens");
    expect(table.textContent).toContain("Total cost");
    expect(table.textContent).toContain("Error count");
    expect(table.textContent).toContain("Total tool calls");
  });

  it("highlights the duration delta green when run B is faster", () => {
    render(<DiffSummary statsA={statsA} statsB={fasterStatsB} />);
    const row = screen.getByText("Total duration").closest("tr");
    const deltaCell = row?.querySelector("td:last-child");
    expect(deltaCell).toHaveClass("diff-delta-good");
  });

  it("highlights the duration delta red when run B is slower", () => {
    render(<DiffSummary statsA={statsA} statsB={slowerStatsB} />);
    const row = screen.getByText("Total duration").closest("tr");
    const deltaCell = row?.querySelector("td:last-child");
    expect(deltaCell).toHaveClass("diff-delta-bad");
  });
});
