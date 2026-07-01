import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RunSelector } from "../RunSelector";
import type { Run } from "../../../types";

function makeRun(runId: string): Run {
  return {
    run_id: runId,
    started_at: 1000,
    finished_at: 1010,
    framework: null,
    agent_count: 1,
    total_tokens: 0,
    total_cost_usd: 0,
    status: "running",
    metadata: {},
  };
}

const runs = [makeRun("run-1"), makeRun("run-2")];

describe("RunSelector", () => {
  it("calls onSelectRunA/onSelectRunB when a dropdown changes", () => {
    const onSelectRunA = vi.fn();
    const onSelectRunB = vi.fn();
    render(
      <RunSelector
        runs={runs}
        runAId={null}
        runBId={null}
        onSelectRunA={onSelectRunA}
        onSelectRunB={onSelectRunB}
      />
    );

    fireEvent.change(screen.getByLabelText("Run A"), { target: { value: "run-1" } });
    expect(onSelectRunA).toHaveBeenCalledWith("run-1");

    fireEvent.change(screen.getByLabelText("Run B"), { target: { value: "run-2" } });
    expect(onSelectRunB).toHaveBeenCalledWith("run-2");
  });

  it("disables the run selected in A from being chosen in B, and vice versa", () => {
    render(
      <RunSelector
        runs={runs}
        runAId="run-1"
        runBId={null}
        onSelectRunA={vi.fn()}
        onSelectRunB={vi.fn()}
      />
    );

    const runBSelect = screen.getByLabelText("Run B") as HTMLSelectElement;
    const run1OptionInB = Array.from(runBSelect.options).find((opt) => opt.value === "run-1");
    expect(run1OptionInB?.disabled).toBe(true);
  });
});
