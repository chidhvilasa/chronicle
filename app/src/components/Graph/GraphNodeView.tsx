import { Handle, Position, type NodeProps } from "reactflow";
import type { GraphNode } from "../../types";

export interface GraphNodeData {
  graphNode: GraphNode;
  dimmed: boolean;
}

function formatLatency(ms: number | null): string {
  if (ms === null) return "—";
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function shapeClassName(type: GraphNode["type"]): string {
  switch (type) {
    case "agent":
      return "graph-node-agent";
    case "tool":
      return "graph-node-tool";
    case "llm":
      return "graph-node-llm";
    default:
      return "graph-node-io";
  }
}

/** Single custom node renderer for every graph node type; shape/color come from CSS by node type. */
export function GraphNodeView({ data }: NodeProps<GraphNodeData>) {
  const { graphNode, dimmed } = data;
  const tooltip = `Total tokens: ${graphNode.total_tokens}\nError count: ${graphNode.error_count}\nAvg latency: ${formatLatency(graphNode.avg_latency_ms)}`;

  return (
    <div
      className={[
        "graph-node",
        shapeClassName(graphNode.type),
        `graph-node-status-${graphNode.status}`,
        dimmed ? "graph-node-dimmed" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      title={tooltip}
      data-testid={`graph-node-${graphNode.id}`}
    >
      <Handle type="target" position={Position.Left} />
      <span className="graph-node-label">{graphNode.label}</span>
      {graphNode.type === "agent" || graphNode.type === "tool" ? (
        <span className="graph-node-count">{graphNode.event_count}</span>
      ) : null}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
