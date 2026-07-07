import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ExecutionGraph as ExecutionGraphModel } from "../../../types";

vi.mock("../../../api/client", async () => {
  const actual = await vi.importActual<typeof import("../../../api/client")>("../../../api/client");
  return {
    ...actual,
    chronicleApi: { getRunGraph: vi.fn() },
  };
});

import { chronicleApi } from "../../../api/client";
import { ExecutionGraph } from "../ExecutionGraph";

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.mocked(chronicleApi.getRunGraph).mockReset();
  // React Flow relies on ResizeObserver, which jsdom does not implement.
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
});

function makeGraph(overrides: Partial<ExecutionGraphModel> = {}): ExecutionGraphModel {
  return {
    run_id: "run-1",
    nodes: [
      {
        id: "agent:researcher",
        type: "agent",
        label: "researcher",
        agent_name: "researcher",
        event_count: 2,
        error_count: 0,
        total_tokens: 30,
        avg_latency_ms: 120,
        status: "ok",
      },
      {
        id: "tool:search",
        type: "tool",
        label: "search",
        agent_name: null,
        event_count: 1,
        error_count: 0,
        total_tokens: 0,
        avg_latency_ms: 40,
        status: "ok",
      },
    ],
    edges: [
      {
        id: "agent:researcher->tool:search:calls",
        source: "agent:researcher",
        target: "tool:search",
        label: "search",
        edge_type: "calls",
        event_count: 1,
      },
    ],
    metadata: { total_nodes: 2, total_edges: 1, has_cycles: false, max_depth: 1 },
    ...overrides,
  };
}

describe("ExecutionGraph", () => {
  it("shows the empty state when no run is selected", () => {
    render(<ExecutionGraph runId={null} />);
    expect(screen.getByText("Select a run to view its execution graph")).toBeInTheDocument();
  });

  it("shows the no-events state when the run has no graphable events", async () => {
    vi.mocked(chronicleApi.getRunGraph).mockResolvedValue(
      makeGraph({ nodes: [], edges: [], metadata: { total_nodes: 0, total_edges: 0, has_cycles: false, max_depth: 0 } })
    );
    render(<ExecutionGraph runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByText("This run has no events to graph")).toBeInTheDocument();
    });
  });

  it("renders the graph without crashing given mock graph data", async () => {
    vi.mocked(chronicleApi.getRunGraph).mockResolvedValue(makeGraph());
    render(<ExecutionGraph runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByTestId("execution-graph")).toBeInTheDocument();
    });
    expect(screen.getByTestId("graph-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("graph-toolbar")).toBeInTheDocument();
  });

  it("shows the cycle warning banner when the graph metadata reports a cycle", async () => {
    vi.mocked(chronicleApi.getRunGraph).mockResolvedValue(
      makeGraph({ metadata: { total_nodes: 2, total_edges: 1, has_cycles: true, max_depth: 1 } })
    );
    render(<ExecutionGraph runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByTestId("graph-cycle-banner")).toBeInTheDocument();
    });
  });

  it("does not show the cycle warning banner when there is no cycle", async () => {
    vi.mocked(chronicleApi.getRunGraph).mockResolvedValue(makeGraph());
    render(<ExecutionGraph runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByTestId("execution-graph")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("graph-cycle-banner")).not.toBeInTheDocument();
  });

  it("shows an error message with a retry button when the fetch fails", async () => {
    vi.mocked(chronicleApi.getRunGraph).mockRejectedValue(new Error("network down"));
    render(<ExecutionGraph runId="run-1" />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    });
  });
});
