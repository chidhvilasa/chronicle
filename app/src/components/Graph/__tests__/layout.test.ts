import { describe, expect, it } from "vitest";
import type { GraphEdge, GraphNode } from "../../../types";
import { computeLayout } from "../layout";

function makeNode(id: string, type: GraphNode["type"] = "agent"): GraphNode {
  return {
    id,
    type,
    label: id,
    agent_name: type === "agent" ? id : null,
    event_count: 1,
    error_count: 0,
    total_tokens: 0,
    avg_latency_ms: null,
    status: "ok",
  };
}

function makeEdge(source: string, target: string, edge_type: GraphEdge["edge_type"] = "calls"): GraphEdge {
  return { id: `${source}->${target}`, source, target, label: "", edge_type, event_count: 1 };
}

describe("computeLayout", () => {
  it("returns an empty map for no nodes", () => {
    expect(computeLayout([], []).size).toBe(0);
  });

  it("places nodes in increasing columns following forward edges from the input node", () => {
    const nodes = [makeNode("input", "input"), makeNode("agent:a"), makeNode("tool:x", "tool")];
    const edges = [makeEdge("input", "agent:a", "triggers"), makeEdge("agent:a", "tool:x", "calls")];

    const positions = computeLayout(nodes, edges);

    expect(positions.get("input")?.x).toBe(0);
    expect(positions.get("agent:a")?.x).toBeGreaterThan(positions.get("input")?.x ?? 0);
    expect(positions.get("tool:x")?.x).toBeGreaterThan(positions.get("agent:a")?.x ?? 0);
  });

  it("excludes responds edges from column computation so tool responses don't pull nodes backward", () => {
    const nodes = [makeNode("agent:a"), makeNode("tool:x", "tool")];
    const edges = [makeEdge("agent:a", "tool:x", "calls"), makeEdge("tool:x", "agent:a", "responds")];

    const positions = computeLayout(nodes, edges);

    expect(positions.get("tool:x")?.x).toBeGreaterThan(positions.get("agent:a")?.x ?? 0);
  });

  it("does not infinite-loop on a cyclic handoff graph", () => {
    const nodes = [makeNode("agent:a"), makeNode("agent:b")];
    const edges = [makeEdge("agent:a", "agent:b", "handoff"), makeEdge("agent:b", "agent:a", "handoff")];

    expect(() => computeLayout(nodes, edges)).not.toThrow();
    expect(computeLayout(nodes, edges).size).toBe(2);
  });

  it("places disconnected nodes in a trailing column instead of dropping them", () => {
    const nodes = [makeNode("agent:a"), makeNode("agent:disconnected")];
    const edges: GraphEdge[] = [];

    const positions = computeLayout(nodes, edges);

    expect(positions.has("agent:a")).toBe(true);
    expect(positions.has("agent:disconnected")).toBe(true);
  });

  it("stacks multiple nodes in the same column at different rows", () => {
    const nodes = [makeNode("input", "input"), makeNode("agent:a"), makeNode("agent:b")];
    const edges = [makeEdge("input", "agent:a", "triggers"), makeEdge("input", "agent:b", "triggers")];

    const positions = computeLayout(nodes, edges);

    expect(positions.get("agent:a")?.x).toBe(positions.get("agent:b")?.x);
    expect(positions.get("agent:a")?.y).not.toBe(positions.get("agent:b")?.y);
  });
});
