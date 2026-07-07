import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MemorySnapshot } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { getRunMemory: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { MemoryInspector } from "../MemoryInspector";

function makeSnapshot(overrides: Partial<MemorySnapshot> = {}): MemorySnapshot {
  return {
    event_id: "e1",
    step_index: 0,
    agent_name: "agent-a",
    timestamp: 1000,
    memory_before: { a: 1 },
    memory_after: { a: 1, b: 2 },
    keys_added: ["b"],
    keys_removed: [],
    keys_changed: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(chronicleApi.getRunMemory).mockReset();
});

describe("MemoryInspector", () => {
  it("renders the empty state when no run is selected", () => {
    expect(() => render(<MemoryInspector runId={null} />)).not.toThrow();
    expect(screen.getByText("Select a run to inspect its memory.")).toBeInTheDocument();
  });

  it("renders without crashing with zero memory updates, showing the server's message", async () => {
    vi.mocked(chronicleApi.getRunMemory).mockResolvedValue({
      snapshots: [],
      message: "No memory updates recorded for this run. Memory tracking requires chronicle-sdk 0.7.0 or higher.",
    });
    expect(() => render(<MemoryInspector runId="run-1" />)).not.toThrow();

    await waitFor(() => {
      expect(screen.getByText(/chronicle-sdk 0\.7\.0/)).toBeInTheDocument();
    });
  });

  it("renders a timeline row per snapshot with a key-count summary", async () => {
    vi.mocked(chronicleApi.getRunMemory).mockResolvedValue({
      snapshots: [makeSnapshot({ keys_added: ["b", "c"], keys_changed: ["a"] })],
      message: null,
    });
    render(<MemoryInspector runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByText("+2 keys, -0 keys, ~1 key")).toBeInTheDocument();
    });
  });

  it("shows added/removed/changed keys with their values for the selected snapshot", async () => {
    vi.mocked(chronicleApi.getRunMemory).mockResolvedValue({
      snapshots: [
        makeSnapshot({
          memory_before: { removed_key: "gone", changed_key: "old" },
          memory_after: { added_key: "new value", changed_key: "new" },
          keys_added: ["added_key"],
          keys_removed: ["removed_key"],
          keys_changed: ["changed_key"],
        }),
      ],
      message: null,
    });
    render(<MemoryInspector runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByText("added_key")).toBeInTheDocument();
    });
    expect(screen.getByText("new value")).toBeInTheDocument();
    expect(screen.getByText("removed_key")).toBeInTheDocument();
    expect(screen.getByText("gone")).toBeInTheDocument();
    expect(screen.getByText("changed_key")).toBeInTheDocument();
    expect(screen.getByText("old")).toBeInTheDocument();
    expect(screen.getByText("new")).toBeInTheDocument();
  });

  it("hides unchanged keys by default and shows them after toggling", async () => {
    vi.mocked(chronicleApi.getRunMemory).mockResolvedValue({
      snapshots: [
        makeSnapshot({
          memory_before: { unchanged_key: "same value", a: 1 },
          memory_after: { unchanged_key: "same value", a: 1, b: 2 },
          keys_added: ["b"],
          keys_removed: [],
          keys_changed: [],
        }),
      ],
      message: null,
    });
    render(<MemoryInspector runId="run-1" />);

    await waitFor(() => expect(screen.getByText("b")).toBeInTheDocument());
    expect(screen.queryByText("unchanged_key")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show unchanged keys" }));
    expect(screen.getByText("unchanged_key")).toBeInTheDocument();
  });

  it("switches the diff view when a different timeline row is clicked", async () => {
    vi.mocked(chronicleApi.getRunMemory).mockResolvedValue({
      snapshots: [
        makeSnapshot({ event_id: "e1", step_index: 0, keys_added: ["first_key"], memory_after: { first_key: 1 } }),
        makeSnapshot({ event_id: "e2", step_index: 1, keys_added: ["second_key"], memory_after: { second_key: 2 } }),
      ],
      message: null,
    });
    render(<MemoryInspector runId="run-1" />);

    await waitFor(() => expect(screen.getByText("first_key")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Step 1"));
    await waitFor(() => expect(screen.getByText("second_key")).toBeInTheDocument());
    expect(screen.queryByText("first_key")).not.toBeInTheDocument();
  });
});
