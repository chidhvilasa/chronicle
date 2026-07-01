import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Sidebar } from "../Sidebar";
import type { ChronicleRun } from "../../types";

const runs: ChronicleRun[] = [
  { id: "run-1", started_at: 1700000000, ended_at: 1700000010, event_count: 3 },
];

describe("Sidebar", () => {
  it("shows an empty state when there are no runs", () => {
    render(<Sidebar runs={[]} selectedRunId={null} onSelectRun={vi.fn()} />);
    expect(screen.getByText(/no runs captured yet/i)).toBeInTheDocument();
  });

  it("renders a run item for each run", () => {
    render(<Sidebar runs={runs} selectedRunId={null} onSelectRun={vi.fn()} />);
    expect(screen.getByText("run-1")).toBeInTheDocument();
    expect(screen.getByText(/3 events/i)).toBeInTheDocument();
  });
});
