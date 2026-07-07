import type { GraphEdge, GraphNode } from "../../types";

export interface NodePosition {
  x: number;
  y: number;
}

const COLUMN_SPACING = 220;
const ROW_SPACING = 90;

/**
 * Simple left-to-right layered layout: each node's column is its shortest-hop
 * distance from the graph's "input" node (or the first node, if there isn't
 * one), computed via BFS over `calls`/`handoff`/`triggers` edges only
 * (excluding `responds`, which would otherwise create a trivial back-edge for
 * every tool call). Nodes unreachable from the start (disconnected
 * sub-graphs) are placed in one extra trailing column. No external layout
 * library needed for graphs capped at ~50 nodes.
 */
export function computeLayout(
  nodes: GraphNode[],
  edges: GraphEdge[]
): Map<string, NodePosition> {
  const adjacency = new Map<string, string[]>();
  nodes.forEach((node) => adjacency.set(node.id, []));
  edges
    .filter((edge) => edge.edge_type !== "responds")
    .forEach((edge) => adjacency.get(edge.source)?.push(edge.target));

  const depth = new Map<string, number>();
  const startId = nodes.find((node) => node.type === "input")?.id ?? nodes[0]?.id;
  if (startId !== undefined) {
    depth.set(startId, 0);
    const queue: string[] = [startId];
    while (queue.length > 0) {
      const current = queue.shift() as string;
      const currentDepth = depth.get(current) ?? 0;
      for (const neighbor of adjacency.get(current) ?? []) {
        if (!depth.has(neighbor)) {
          depth.set(neighbor, currentDepth + 1);
          queue.push(neighbor);
        }
      }
    }
  }

  const maxDepth = Math.max(0, ...Array.from(depth.values()));
  nodes.forEach((node) => {
    if (!depth.has(node.id)) depth.set(node.id, maxDepth + 1);
  });

  const columns = new Map<number, string[]>();
  nodes.forEach((node) => {
    const d = depth.get(node.id) ?? 0;
    const column = columns.get(d) ?? [];
    column.push(node.id);
    columns.set(d, column);
  });

  const positions = new Map<string, NodePosition>();
  for (const [d, ids] of columns) {
    ids.forEach((id, index) => {
      positions.set(id, { x: d * COLUMN_SPACING, y: index * ROW_SPACING });
    });
  }
  return positions;
}
