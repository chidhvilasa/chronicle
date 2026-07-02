import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RunList } from "../RunList";
import { useAppStore } from "../../store/useAppStore";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { RUN_LIST_POLL_INTERVAL_MS } from "../../config";
import type { Run } from "../../types";

vi.mock("../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../api/client")>("../../api/client");
  return {
    ...actual,
    chronicleApi: { listRuns: vi.fn() },
  };
});

const initialState = useAppStore.getState();

const run: Run = {
  run_id: "run-abcdefgh1234",
  started_at: Math.floor(Date.now() / 1000) - 30,
  finished_at: Math.floor(Date.now() / 1000) - 10,
  framework: null,
  agent_count: 1,
  total_tokens: 42,
  total_cost_usd: 0,
  status: "running",
  metadata: {},
};

beforeEach(() => {
  useAppStore.setState(initialState, true);
  vi.mocked(chronicleApi.listRuns).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("RunList", () => {
  it("shows the empty state once the initial fetch resolves with no runs", async () => {
    vi.mocked(chronicleApi.listRuns).mockResolvedValue([]);
    render(<RunList />);

    await waitFor(() => {
      expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
    });
  });

  it("renders a run card for each run with id, status, tokens, and duration", async () => {
    vi.mocked(chronicleApi.listRuns).mockResolvedValue([run]);
    render(<RunList />);

    await waitFor(() => {
      expect(screen.getByText(/42 tokens/)).toBeInTheDocument();
    });
    expect(screen.getByText("running")).toBeInTheDocument();
    expect(screen.getByText("20.0s")).toBeInTheDocument();
  });

  it("selects a run when its card is clicked", async () => {
    vi.mocked(chronicleApi.listRuns).mockResolvedValue([run]);
    render(<RunList />);

    const card = await screen.findByText(/42 tokens/);
    card.closest("button")?.click();

    expect(useAppStore.getState().selectedRunId).toBe(run.run_id);
  });

  it("shows a human-readable error when the server is unreachable", async () => {
    vi.mocked(chronicleApi.listRuns).mockRejectedValue(
      new ChronicleApiError("Could not reach the Chronicle server. Is it running?")
    );
    render(<RunList />);

    await waitFor(() => {
      expect(screen.getByText(/could not reach the chronicle server/i)).toBeInTheDocument();
    });
  });

  it("shows a REPLAY badge with a source tooltip for replay runs", async () => {
    const replayRun: Run = {
      ...run,
      run_id: "run-replay-1",
      metadata: {
        is_replay: true,
        source_run_id: "run-abcdefgh1234",
        source_snapshot_id: "snap-1",
        step_index: 4,
      },
    };
    vi.mocked(chronicleApi.listRuns).mockResolvedValue([replayRun]);
    render(<RunList />);

    await waitFor(() => {
      expect(screen.getByTestId("replay-badge")).toBeInTheDocument();
    });
    expect(screen.getByTestId("replay-badge")).toHaveAttribute(
      "title",
      "Replayed from run run-abcdefgh1234 at step 4"
    );
  });

  it("does not show a REPLAY badge for a non-replay run", async () => {
    vi.mocked(chronicleApi.listRuns).mockResolvedValue([run]);
    render(<RunList />);

    await waitFor(() => {
      expect(screen.getByText(/42 tokens/)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("replay-badge")).not.toBeInTheDocument();
  });

  it("polls GET /runs on the configured interval", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(chronicleApi.listRuns).mockResolvedValue([]);
    render(<RunList />);

    await act(async () => {
      await Promise.resolve();
    });
    expect(chronicleApi.listRuns).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(RUN_LIST_POLL_INTERVAL_MS);
      await Promise.resolve();
    });
    expect(chronicleApi.listRuns).toHaveBeenCalledTimes(2);
  });
});
