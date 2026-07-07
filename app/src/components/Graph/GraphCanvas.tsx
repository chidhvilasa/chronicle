import { useMemo } from "react";
import ReactFlow, { Background, Controls, MarkerType, type Edge, type Node } from "reactflow";
import "reactflow/dist/style.css";
import type { ExecutionGraph, GraphEdgeType, GraphNode as GraphNodeModel } from "../../types";
import { GraphNodeView, type GraphNodeData } from "./GraphNodeView";
import { computeLayout } from "./layout";

interface GraphCanvasProps {
  graph: ExecutionGraph;
  showEdgeLabels: boolean;
  highlightErrorsOnly: boolean;
  onSelectAgent: (agentName: string) => void;
  onSelectTool: (toolName: string) => void;
}

const nodeTypes = { graphNode: GraphNodeView };

const EDGE_STYLE: Record<GraphEdgeType, { stroke: string; strokeWidth: number; dashed: boolean }> = {
  calls: { stroke: "#4285f4", strokeWidth: 1.5, dashed: false },
  responds: { stroke: "#9ca3af", strokeWidth: 1.5, dashed: true },
  handoff: { stroke: "#a855f7", strokeWidth: 3, dashed: false },
  triggers: { stroke: "#9ca3af", strokeWidth: 1, dashed: false },
};

function buildNodes(graph: ExecutionGraph, highlightErrorsOnly: boolean): Node<GraphNodeData>[] {
  const positions = computeLayout(graph.nodes, graph.edges);
  return graph.nodes.map((graphNode: GraphNodeModel) => ({
    id: graphNode.id,
    type: "graphNode",
    position: positions.get(graphNode.id) ?? { x: 0, y: 0 },
    data: { graphNode, dimmed: highlightErrorsOnly && graphNode.status !== "error" },
  }));
}

function buildEdges(graph: ExecutionGraph, showEdgeLabels: boolean): Edge[] {
  return graph.edges.map((edge) => {
    const style = EDGE_STYLE[edge.edge_type];
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: showEdgeLabels && edge.event_count > 1 ? `x${edge.event_count}` : undefined,
      style: {
        stroke: style.stroke,
        strokeWidth: style.strokeWidth,
        strokeDasharray: style.dashed ? "5,5" : undefined,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: style.stroke },
    };
  });
}

/** React Flow canvas for one run's execution graph. Must render inside a `ReactFlowProvider`. */
export function GraphCanvas({
  graph,
  showEdgeLabels,
  highlightErrorsOnly,
  onSelectAgent,
  onSelectTool,
}: GraphCanvasProps) {
  const nodes = useMemo(() => buildNodes(graph, highlightErrorsOnly), [graph, highlightErrorsOnly]);
  const edges = useMemo(() => buildEdges(graph, showEdgeLabels), [graph, showEdgeLabels]);

  function handleNodeClick(_event: React.MouseEvent, node: Node<GraphNodeData>) {
    const { graphNode } = node.data;
    if (graphNode.type === "agent" && graphNode.agent_name !== null) {
      onSelectAgent(graphNode.agent_name);
    } else if (graphNode.type === "tool") {
      onSelectTool(graphNode.label);
    }
  }

  return (
    <div className="graph-canvas-wrapper" data-testid="graph-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        fitView
        minZoom={0.1}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
