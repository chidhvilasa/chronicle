import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "../../../store/useAppStore";
import { chronicleApi, ChronicleApiError } from "../../../api/client";
import type { Run, Snapshot } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: {
      getSnapshot: vi.fn(),
      replay: vi.fn(),
      listRuns: vi.fn(),
    },
  };
});

import { ReplayModal } from "../ReplayModal";

const initialState = useAppStore.getState();

const snapshot: Snapshot = {
  snapshot_id: "snap-1",
  run_id: "run-1",
  event_id: "evt-1",
  step_index: 3,
  timestamp: 1700000000,
  agent_name: "agent-a",
  graph_state: {},
  messages: [{ role: "user", content: "hi" }],
  tool_results: [{ tool: "search", result: "ok" }],
  metadata: {},
};

function makeRun(runId: string, status: string): Run {
  return {
    run_id: runId,
    started_at: 1000,
    finished_at: 1030,
    framework: null,
    agent_count: 1,
    total_tokens: 10,
    total_cost_usd: 0,
    status,
    metadata: {},
  };
}

beforeEach(() => {
  useAppStore.setState(initialState, true);
  vi.mocked(chronicleApi.getSnapshot).mockReset();
  vi.mocked(chronicleApi.replay).mockReset();
  vi.mocked(chronicleApi.listRuns).mockReset();
});

describe("ReplayModal", () => {
  it("shows snapshot step, timestamp, agent, and graph state summary once loaded", async () => {
    vi.mocked(chronicleApi.getSnapshot).mockResolvedValue(snapshot);
    render(<ReplayModal runId="run-1" snapshotId="snap-1" onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("3")).toBeInTheDocument();
    });
    expect(screen.getByText("agent-a")).toBeInTheDocument();
    expect(screen.getByText(/1 message/)).toBeInTheDocument();
  });

  it("shows a load error in place of the snapshot details", async () => {
    vi.mocked(chronicleApi.getSnapshot).mockRejectedValue(
      new ChronicleApiError("Could not reach the Chronicle server. Is it running?")
    );
    render(<ReplayModal runId="run-1" snapshotId="snap-1" onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/could not reach the chronicle server/i)).toBeInTheDocument();
    });
  });

  it("replays as-is with empty modifications and selects the new run on completion", async () => {
    vi.mocked(chronicleApi.getSnapshot).mockResolvedValue(snapshot);
    vi.mocked(chronicleApi.replay).mockResolvedValue({ run_id: "run-2" });
    vi.mocked(chronicleApi.listRuns).mockResolvedValue([makeRun("run-2", "complete")]);
    const onClose = vi.fn();
    render(<ReplayModal runId="run-1" snapshotId="snap-1" onClose={onClose} />);

    await waitFor(() => {
      expect(screen.getByText("agent-a")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Replay as-is" }));

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(chronicleApi.replay).toHaveBeenCalledWith("run-1", "snap-1", {});
    expect(useAppStore.getState().selectedRunId).toBe("run-2");
    expect(useAppStore.getState().toast?.message).toBe("Replay complete. Compare with original?");
  });

  it("parses the modifications textarea and sends it as the replay body", async () => {
    vi.mocked(chronicleApi.getSnapshot).mockResolvedValue(snapshot);
    vi.mocked(chronicleApi.replay).mockResolvedValue({ run_id: "run-2" });
    vi.mocked(chronicleApi.listRuns).mockResolvedValue([makeRun("run-2", "complete")]);
    render(<ReplayModal runId="run-1" snapshotId="snap-1" onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("agent-a")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('{ "override_key": "new_value" }'), {
      target: { value: '{ "override_key": "new_value" }' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Replay with modifications" }));

    await waitFor(() => {
      expect(chronicleApi.replay).toHaveBeenCalledWith("run-1", "snap-1", { override_key: "new_value" });
    });
  });

  it("shows a red validation error and does not call replay for invalid JSON", async () => {
    vi.mocked(chronicleApi.getSnapshot).mockResolvedValue(snapshot);
    render(<ReplayModal runId="run-1" snapshotId="snap-1" onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("agent-a")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('{ "override_key": "new_value" }'), {
      target: { value: "{ not valid json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Replay with modifications" }));

    expect(screen.getByText(/modifications must be valid json/i)).toBeInTheDocument();
    expect(chronicleApi.replay).not.toHaveBeenCalled();
  });

  it("shows the server error message in red when replay fails", async () => {
    vi.mocked(chronicleApi.getSnapshot).mockResolvedValue(snapshot);
    vi.mocked(chronicleApi.replay).mockRejectedValue(
      new ChronicleApiError("No graph registered. Call tracer.register_graph() before replaying.")
    );
    render(<ReplayModal runId="run-1" snapshotId="snap-1" onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("agent-a")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Replay as-is" }));

    await waitFor(() => {
      expect(screen.getByText(/no graph registered/i)).toBeInTheDocument();
    });
    expect(document.querySelector(".replay-error")).not.toBeNull();
  });

  it("shows a spinner with the step index while replaying", async () => {
    vi.mocked(chronicleApi.getSnapshot).mockResolvedValue(snapshot);
    vi.mocked(chronicleApi.replay).mockReturnValue(new Promise(() => {}));
    render(<ReplayModal runId="run-1" snapshotId="snap-1" onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("agent-a")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Replay as-is" }));

    await waitFor(() => {
      expect(screen.getByText(/replaying from step 3/i)).toBeInTheDocument();
    });
  });
});
