import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "../../../store/useAppStore";
import type { ChronicleTest, TestResult as TestResultData } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { getTest: vi.fn(), getTestHistory: vi.fn(), runTest: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { TestResultPanel } from "../TestResult";

const initialState = useAppStore.getState();

function makeTest(overrides: Partial<ChronicleTest> = {}): ChronicleTest {
  return {
    test_id: "test-1",
    name: "greets the user",
    source_run_id: "run-1",
    source_snapshot_id: "snap-0",
    assertions: [],
    created_at: 1000,
    last_run_at: 2000,
    last_result: "pass",
    ...overrides,
  };
}

function makeResult(overrides: Partial<TestResultData> = {}): TestResultData {
  return {
    result_id: "result-1",
    test_id: "test-1",
    replay_run_id: "replay-1",
    status: "pass",
    passed: true,
    assertion_results: [
      { assertion_id: "a1", assertion_type: "output_contains", passed: true, reason: "matched", on_fail: "fail" },
    ],
    duration_ms: 120,
    token_usage: { input_tokens: 10, output_tokens: 5 },
    error_reason: null,
    created_at: 2000,
    ...overrides,
  };
}

beforeEach(() => {
  useAppStore.setState(initialState, true);
  vi.mocked(chronicleApi.getTest).mockReset();
  vi.mocked(chronicleApi.getTestHistory).mockReset();
  vi.mocked(chronicleApi.runTest).mockReset();
});

describe("TestResultPanel", () => {
  it("renders the test name, source run, history bar, and most recent assertion results", async () => {
    vi.mocked(chronicleApi.getTest).mockResolvedValue(makeTest());
    vi.mocked(chronicleApi.getTestHistory).mockResolvedValue([makeResult()]);

    render(<TestResultPanel testId="test-1" onBack={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("greets the user")).toBeInTheDocument();
    });
    expect(screen.getByTestId("test-result-history-bar")).toBeInTheDocument();
    expect(screen.getByText(/output_contains: matched/)).toBeInTheDocument();
  });

  it("calls onBack when the back button is clicked", async () => {
    vi.mocked(chronicleApi.getTest).mockResolvedValue(makeTest());
    vi.mocked(chronicleApi.getTestHistory).mockResolvedValue([]);
    const onBack = vi.fn();

    render(<TestResultPanel testId="test-1" onBack={onBack} />);
    await screen.findByText("greets the user");

    fireEvent.click(screen.getByRole("button", { name: /back to tests/i }));
    expect(onBack).toHaveBeenCalled();
  });

  it("selects the replay run and switches to the timeline tab when its link is clicked", async () => {
    vi.mocked(chronicleApi.getTest).mockResolvedValue(makeTest());
    vi.mocked(chronicleApi.getTestHistory).mockResolvedValue([makeResult()]);

    render(<TestResultPanel testId="test-1" onBack={vi.fn()} />);
    await screen.findByText("greets the user");

    fireEvent.click(screen.getByRole("button", { name: /view replay run/i }));

    expect(useAppStore.getState().selectedRunId).toBe("replay-1");
    expect(useAppStore.getState().activePanel).toBe("timeline");
  });

  it("runs the test again and reloads its history", async () => {
    vi.mocked(chronicleApi.getTest).mockResolvedValue(makeTest());
    vi.mocked(chronicleApi.getTestHistory)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([makeResult()]);
    vi.mocked(chronicleApi.runTest).mockResolvedValue(makeResult());

    render(<TestResultPanel testId="test-1" onBack={vi.fn()} />);
    await screen.findByText("greets the user");

    fireEvent.click(screen.getByRole("button", { name: /run again/i }));

    await waitFor(() => {
      expect(chronicleApi.runTest).toHaveBeenCalledWith("test-1");
    });
    await waitFor(() => {
      expect(screen.getByText(/output_contains: matched/)).toBeInTheDocument();
    });
  });

  it("shows the empty history message when the test has never run", async () => {
    vi.mocked(chronicleApi.getTest).mockResolvedValue(makeTest({ last_result: null, last_run_at: null }));
    vi.mocked(chronicleApi.getTestHistory).mockResolvedValue([]);

    render(<TestResultPanel testId="test-1" onBack={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
    });
  });
});
