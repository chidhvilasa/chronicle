import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

import { Inspector } from "../Inspector";

const initialState = useAppStore.getState();

const events: Event[] = [
  {
    event_id: "e1",
    run_id: "run-1",
    timestamp: 1000,
    event_type: "llm_call",
    agent_name: "agent-a",
    duration_ms: 200,
    input_tokens: 10,
    output_tokens: 5,
    data: { prompt: "hi", completion: "hello" },
    error: null,
  },
];

beforeEach(() => {
  useAppStore.setState(initialState, true);
  vi.mocked(chronicleApi.listRunEvents).mockReset();
  vi.mocked(chronicleApi.listRunEvents).mockResolvedValue(events);
});

describe("Inspector", () => {
  it("renders without crashing when nothing is selected", () => {
    expect(() => render(<Inspector />)).not.toThrow();
    expect(screen.getByTestId("detail-inspector")).toBeInTheDocument();
    expect(screen.getByText(/select an event or segment/i)).toBeInTheDocument();
  });

  it("renders all three tabs", () => {
    render(<Inspector />);
    expect(screen.getByRole("tab", { name: "Event" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Agent" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Tools" })).toBeInTheDocument();
  });

  it("switches to the agent tab and shows the agent inspector", () => {
    useAppStore.getState().selectRun("run-1");
    render(<Inspector />);

    fireEvent.click(screen.getByRole("tab", { name: "Agent" }));
    expect(screen.getByText(/click an agent's lane header/i)).toBeInTheDocument();
  });

  it("switches to the tools tab and shows the tool inspector", async () => {
    useAppStore.getState().selectRun("run-1");
    render(<Inspector />);

    fireEvent.click(screen.getByRole("tab", { name: "Tools" }));
    await waitFor(() => {
      expect(screen.getByText(/no tool calls recorded/i)).toBeInTheDocument();
    });
  });

  it("preserves the last selected item per tab when switching back and forth", async () => {
    useAppStore.getState().selectRun("run-1");
    render(<Inspector />);

    act(() => {
      useAppStore.getState().selectDetail(events[0]);
    });
    await waitFor(() => {
      expect(screen.getByTestId("llm-prompt")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("tab", { name: "Agent" }));
    act(() => {
      useAppStore.getState().selectAgent("agent-a");
    });
    expect(screen.getByTestId("agent-inspector")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Event" }));
    expect(screen.getByTestId("llm-prompt")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Agent" }));
    expect(screen.getByTestId("agent-inspector")).toBeInTheDocument();
  });

  it("collapses and expands via the toggle button", () => {
    render(<Inspector />);
    fireEvent.click(screen.getByRole("button", { name: /collapse detail inspector/i }));
    expect(screen.getByTestId("detail-inspector")).toHaveClass("collapsed");
    expect(screen.queryByRole("tab", { name: "Event" })).not.toBeInTheDocument();
  });
});
