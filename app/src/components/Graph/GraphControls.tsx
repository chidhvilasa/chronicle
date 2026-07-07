import { toPng } from "html-to-image";
import { getNodesBounds, getViewportForBounds, useReactFlow, type Node } from "reactflow";

interface GraphControlsProps {
  containerRef: React.RefObject<HTMLDivElement | null>;
  showEdgeLabels: boolean;
  onToggleEdgeLabels: () => void;
  highlightErrorsOnly: boolean;
  onToggleHighlightErrors: () => void;
}

async function exportAsPng(container: HTMLDivElement, nodes: Node[]): Promise<void> {
  const viewportEl = container.querySelector<HTMLElement>(".react-flow__viewport");
  if (viewportEl === null || nodes.length === 0) return;

  const width = container.clientWidth;
  const height = container.clientHeight;
  const bounds = getNodesBounds(nodes);
  const viewport = getViewportForBounds(bounds, width, height, 0.1, 2, 0.1);
  const dataUrl = await toPng(viewportEl, {
    backgroundColor: "#ffffff",
    width,
    height,
    style: {
      width: `${width}px`,
      height: `${height}px`,
      transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`,
    },
  });

  const link = document.createElement("a");
  link.download = "chronicle-execution-graph.png";
  link.href = dataUrl;
  link.click();
}

/** Toolbar for the Execution Graph tab: fit-to-screen, edge label/error toggles, PNG export. */
export function GraphControls({
  containerRef,
  showEdgeLabels,
  onToggleEdgeLabels,
  highlightErrorsOnly,
  onToggleHighlightErrors,
}: GraphControlsProps) {
  const reactFlowInstance = useReactFlow();

  function handleExport() {
    const container = containerRef.current;
    if (container === null) return;
    void exportAsPng(container, reactFlowInstance.getNodes());
  }

  return (
    <div className="graph-toolbar" data-testid="graph-toolbar">
      <button type="button" onClick={() => reactFlowInstance.fitView()}>
        Fit to screen
      </button>
      <button
        type="button"
        className={showEdgeLabels ? "graph-toggle active" : "graph-toggle"}
        onClick={onToggleEdgeLabels}
      >
        Toggle edge labels
      </button>
      <button
        type="button"
        className={highlightErrorsOnly ? "graph-toggle active" : "graph-toggle"}
        onClick={onToggleHighlightErrors}
      >
        Highlight errors only
      </button>
      <button type="button" onClick={handleExport}>
        Export as PNG
      </button>
    </div>
  );
}
