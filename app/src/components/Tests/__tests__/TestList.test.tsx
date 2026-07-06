import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChronicleTest } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { listTests: vi.fn(), runTest: vi.fn(), deleteTest: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { TestList } from "../TestList";

function makeTest(overrides: Partial<ChronicleTest> = {}): ChronicleTest {
  return {
    test_id: "test-1",
    name: "greets the user",
    source_run_id: "run-abcdefgh1234",
    source_snapshot_id: "snap-1",
    assertions: [],
    created_at: 1000,
    last_run_at: null,
    last_result: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(chronicleApi.listTests).mockReset();
  vi.mocked(chronicleApi.runTest).mockReset();
  vi.mocked(chronicleApi.deleteTest).mockReset();
});

describe("TestList", () => {
  it("renders the empty state when no tests exist", async () => {
    vi.mocked(chronicleApi.listTests).mockResolvedValue([]);
    render(<TestList onSelectTest={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/no tests yet\. create your first test from any run\./i)).toBeInTheDocument();
    });
  });

  it("renders a row per test with name, source run, and a NEVER RUN badge", async () => {
    vi.mocked(chronicleApi.listTests).mockResolvedValue([makeTest()]);
    render(<TestList onSelectTest={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("greets the user")).toBeInTheDocument();
    });
    expect(screen.getByText("NEVER RUN")).toBeInTheDocument();
  });

  it("shows a PASS badge for a test that last passed", async () => {
    vi.mocked(chronicleApi.listTests).mockResolvedValue([
      makeTest({ last_result: "pass", last_run_at: 2000 }),
    ]);
    render(<TestList onSelectTest={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("PASS")).toBeInTheDocument();
    });
  });

  it("calls onSelectTest when a test row is clicked", async () => {
    vi.mocked(chronicleApi.listTests).mockResolvedValue([makeTest()]);
    const onSelectTest = vi.fn();
    render(<TestList onSelectTest={onSelectTest} />);

    const row = await screen.findByText("greets the user");
    fireEvent.click(row);

    expect(onSelectTest).toHaveBeenCalledWith("test-1");
  });

  it("runs a test when Run is clicked and refreshes the list", async () => {
    vi.mocked(chronicleApi.listTests)
      .mockResolvedValueOnce([makeTest()])
      .mockResolvedValueOnce([makeTest({ last_result: "pass", last_run_at: 2000 })]);
    vi.mocked(chronicleApi.runTest).mockResolvedValue({
      result_id: "r1",
      test_id: "test-1",
      replay_run_id: "replay-1",
      status: "pass",
      passed: true,
      assertion_results: [],
      duration_ms: 100,
      token_usage: null,
      error_reason: null,
      created_at: 2000,
    });
    render(<TestList onSelectTest={vi.fn()} />);

    await screen.findByText("greets the user");
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(chronicleApi.runTest).toHaveBeenCalledWith("test-1");
    });
    await waitFor(() => {
      expect(screen.getByText("PASS")).toBeInTheDocument();
    });
  });

  it("deletes a test after confirming", async () => {
    vi.mocked(chronicleApi.listTests).mockResolvedValue([makeTest()]);
    vi.mocked(chronicleApi.deleteTest).mockResolvedValue(undefined);
    render(<TestList onSelectTest={vi.fn()} />);

    await screen.findByText("greets the user");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));

    await waitFor(() => {
      expect(chronicleApi.deleteTest).toHaveBeenCalledWith("test-1");
    });
    await waitFor(() => {
      expect(screen.queryByText("greets the user")).not.toBeInTheDocument();
    });
  });

  it("cancels a delete without calling the API", async () => {
    vi.mocked(chronicleApi.listTests).mockResolvedValue([makeTest()]);
    render(<TestList onSelectTest={vi.fn()} />);

    await screen.findByText("greets the user");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(chronicleApi.deleteTest).not.toHaveBeenCalled();
    expect(screen.getByText("greets the user")).toBeInTheDocument();
  });
});
