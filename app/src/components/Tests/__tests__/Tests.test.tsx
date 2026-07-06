import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChronicleTest } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { listTests: vi.fn(), getTest: vi.fn(), getTestHistory: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { Tests } from "../Tests";

function makeTest(overrides: Partial<ChronicleTest> = {}): ChronicleTest {
  return {
    test_id: "test-1",
    name: "greets the user",
    source_run_id: "run-1",
    source_snapshot_id: "snap-0",
    assertions: [],
    created_at: 1000,
    last_run_at: null,
    last_result: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(chronicleApi.listTests).mockReset();
  vi.mocked(chronicleApi.getTest).mockReset();
  vi.mocked(chronicleApi.getTestHistory).mockReset();
});

describe("Tests", () => {
  it("shows the test list by default", async () => {
    vi.mocked(chronicleApi.listTests).mockResolvedValue([]);
    render(<Tests />);

    await waitFor(() => {
      expect(screen.getByText(/no tests yet/i)).toBeInTheDocument();
    });
  });

  it("switches to the test result view when a row is clicked, and back again", async () => {
    vi.mocked(chronicleApi.listTests).mockResolvedValue([makeTest()]);
    vi.mocked(chronicleApi.getTest).mockResolvedValue(makeTest());
    vi.mocked(chronicleApi.getTestHistory).mockResolvedValue([]);

    render(<Tests />);

    fireEvent.click(await screen.findByText("greets the user"));

    await waitFor(() => {
      expect(screen.getByTestId("test-result-panel")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /back to tests/i }));

    await waitFor(() => {
      expect(screen.getByTestId("test-list")).toBeInTheDocument();
    });
  });
});
