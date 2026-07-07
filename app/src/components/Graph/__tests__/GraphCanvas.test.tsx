import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReactFlowProvider } from "reactflow";
import type { ExecutionGraph } from "../../../types";
import { GraphCanvas } from "../GraphCanvas";

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
});

function makeGraph(nodeCount: number): ExecutionGraph {
  const nodes: ExecutionGraph["nodes"] = Array.from({ length: nodeCount }, (_, index) => ({
    id: `agent:agent-${index}`,
    type: "agent",
    label: `agent-${index}`,
    agent_name: `agent-${index}`,
    event_count: 1,
    error_count: 0,
    total_tokens: 0,
    avg_latency_ms: null,
    status: "ok",
  }));
  const edges: ExecutionGraph["edges"] = nodes.slice(1).map((node, index) => ({
    id: `${nodes[index].id}->${node.id}`,
    source: nodes[index].id,
    target: node.id,
    label: "",
    edge_type: "handoff",
    event_count: 1,
  }));
  return { run_id: "run-1", nodes, edges, metadata: { total_nodes: nodeCount, total_edges: edges.length, has_cycles: false, max_depth: nodeCount } };
}

function renderCanvas(graph: ExecutionGraph, overrides: Partial<Parameters<typeof GraphCanvas>[0]> = {}) {
  const onSelectAgent = vi.fn();
  const onSelectTool = vi.fn();
  render(
    <ReactFlowProvider>
      <GraphCanvas
        graph={graph}
        showEdgeLabels={true}
        highlightErrorsOnly={false}
        onSelectAgent={onSelectAgent}
        onSelectTool={onSelectTool}
        {...overrides}
      />
    </ReactFlowProvider>
  );
  return { onSelectAgent, onSelectTool };
}

describe("GraphCanvas", () => {
  it("renders without crashing for a graph with zero nodes", () => {
    expect(() =>
      renderCanvas({ run_id: "run-1", nodes: [], edges: [], metadata: { total_nodes: 0, total_edges: 0, has_cycles: false, max_depth: 0 } })
    ).not.toThrow();
  });

  it("renders up to 50 nodes without crashing", () => {
    expect(() => renderCanvas(makeGraph(50))).not.toThrow();
    expect(screen.getByTestId("graph-node-agent:agent-0")).toBeInTheDocument();
    expect(screen.getByTestId("graph-node-agent:agent-49")).toBeInTheDocument();
  });

  it("calls onSelectAgent when an agent node is clicked", () => {
    const { onSelectAgent } = renderCanvas(makeGraph(3));
    fireEvent.click(screen.getByTestId("graph-node-agent:agent-0"));
    expect(onSelectAgent).toHaveBeenCalledWith("agent-0");
  });

  it("calls onSelectTool when a tool node is clicked", () => {
    const graph: ExecutionGraph = {
      run_id: "run-1",
      nodes: [
        {
          id: "agent:a",
          type: "agent",
          label: "a",
          agent_name: "a",
          event_count: 1,
          error_count: 0,
          total_tokens: 0,
          avg_latency_ms: null,
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
          avg_latency_ms: null,
          status: "ok",
        },
      ],
      edges: [{ id: "e1", source: "agent:a", target: "tool:search", label: "", edge_type: "calls", event_count: 1 }],
      metadata: { total_nodes: 2, total_edges: 1, has_cycles: false, max_depth: 1 },
    };
    const { onSelectTool } = renderCanvas(graph);
    fireEvent.click(screen.getByTestId("graph-node-tool:search"));
    expect(onSelectTool).toHaveBeenCalledWith("search");
  });
});
