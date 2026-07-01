import { beforeEach, describe, expect, it } from "vitest";
import { useAppStore } from "../useAppStore";
import type { Run } from "../../types";

const initialState = useAppStore.getState();

beforeEach(() => {
  useAppStore.setState(initialState, true);
});

const run: Run = {
  run_id: "run-1",
  started_at: 1000,
  finished_at: 1010,
  framework: null,
  agent_count: 1,
  total_tokens: 10,
  total_cost_usd: 0,
  status: "running",
  metadata: {},
};

describe("useAppStore", () => {
  it("has the expected defaults", () => {
    const state = useAppStore.getState();
    expect(state.runs).toEqual([]);
    expect(state.selectedRunId).toBeNull();
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
    expect(state.activePanel).toBe("timeline");
    expect(state.selectedDetail).toBeNull();
  });

  it("setRuns replaces the run list", () => {
    useAppStore.getState().setRuns([run]);
    expect(useAppStore.getState().runs).toEqual([run]);
  });

  it("selectRun sets selectedRunId and clears selectedDetail", () => {
    useAppStore.getState().setSelectedDetail({
      event_id: "evt-1",
      run_id: "run-1",
      timestamp: 1000,
      event_type: "tool_call",
      agent_name: null,
      duration_ms: null,
      input_tokens: null,
      output_tokens: null,
      data: {},
      error: null,
    });

    useAppStore.getState().selectRun("run-1");

    expect(useAppStore.getState().selectedRunId).toBe("run-1");
    expect(useAppStore.getState().selectedDetail).toBeNull();
  });

  it("setLoading and setError update independently", () => {
    useAppStore.getState().setLoading(true);
    useAppStore.getState().setError("boom");

    expect(useAppStore.getState().loading).toBe(true);
    expect(useAppStore.getState().error).toBe("boom");
  });

  it("setActivePanel switches the active panel", () => {
    useAppStore.getState().setActivePanel("diff");
    expect(useAppStore.getState().activePanel).toBe("diff");
  });
});
