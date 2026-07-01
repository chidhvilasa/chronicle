import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InspectorPanel } from "../InspectorPanel";
import { useAppStore } from "../../../store/useAppStore";
import { chronicleApi } from "../../../api/client";
import type { Event } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { listRunEvents: vi.fn() },
  };
});

const initialState = useAppStore.getState();

const event: Event = {
  event_id: "evt-1",
  run_id: "run-1",
  timestamp: 1700000000,
  event_type: "tool_call",
  agent_name: "agent-a",
  duration_ms: 100,
  input_tokens: null,
  output_tokens: null,
  data: { tool_name: "search" },
  error: null,
};

beforeEach(() => {
  useAppStore.setState(initialState, true);
  vi.mocked(chronicleApi.listRunEvents).mockReset();
});

describe("InspectorPanel", () => {
  it("prompts for a run when none is selected", () => {
    render(<InspectorPanel />);
    expect(screen.getByText(/select a run/i)).toBeInTheDocument();
  });

  it("renders a row for each event", async () => {
    vi.mocked(chronicleApi.listRunEvents).mockResolvedValue([event]);
    useAppStore.getState().selectRun("run-1");
    render(<InspectorPanel />);

    await waitFor(() => {
      expect(screen.getByText("tool_call")).toBeInTheDocument();
    });
    expect(screen.getByText("agent-a")).toBeInTheDocument();
  });

  it("selects an event as the detail item when clicked", async () => {
    vi.mocked(chronicleApi.listRunEvents).mockResolvedValue([event]);
    useAppStore.getState().selectRun("run-1");
    render(<InspectorPanel />);

    const row = await screen.findByText("tool_call");
    row.closest("button")?.click();

    expect(useAppStore.getState().selectedDetail).toEqual(event);
  });
});
