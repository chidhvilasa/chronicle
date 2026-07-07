import { useEffect, useRef, useState } from "react";
import { ReactFlowProvider } from "reactflow";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { useAppStore } from "../../store/useAppStore";
import type { ExecutionGraph as ExecutionGraphModel } from "../../types";
import { CycleWarningBanner } from "./CycleWarningBanner";
import { GraphCanvas } from "./GraphCanvas";
import { GraphControls } from "./GraphControls";

interface ExecutionGraphProps {
  runId: string | null;
}

/** Graph tab: fetches `GET /runs/{id}/graph` and renders it as a React Flow DAG. */
export function ExecutionGraph({ runId }: ExecutionGraphProps) {
  const [graph, setGraph] = useState<ExecutionGraphModel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showEdgeLabels, setShowEdgeLabels] = useState(true);
  const [highlightErrorsOnly, setHighlightErrorsOnly] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const selectAgent = useAppStore((state) => state.selectAgent);
  const selectTool = useAppStore((state) => state.selectTool);
  const setInspectorTab = useAppStore((state) => state.setInspectorTab);
  const setActivePanel = useAppStore((state) => state.setActivePanel);

  useEffect(() => {
    if (runId === null) {
      setGraph(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    chronicleApi
      .getRunGraph(runId)
      .then((fetched) => {
        if (!cancelled) setGraph(fetched);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load execution graph.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  function handleSelectAgent(agentName: string) {
    selectAgent(agentName);
    setActivePanel("inspector");
  }

  function handleSelectTool(toolName: string) {
    selectTool(toolName);
    setInspectorTab("tools");
    setActivePanel("inspector");
  }

  if (runId === null) {
    return <p className="panel-empty">Select a run to view its execution graph</p>;
  }
  if (loading) {
    return <p className="panel-empty">Loading execution graph…</p>;
  }
  if (error !== null) {
    return (
      <div>
        <p className="panel-error">{error}</p>
        <button type="button" onClick={() => setGraph(null)}>
          Retry
        </button>
      </div>
    );
  }
  if (graph === null || graph.nodes.length === 0) {
    return <p className="panel-empty">This run has no events to graph</p>;
  }

  return (
    <div className="execution-graph-root" data-testid="execution-graph">
      {graph.metadata.has_cycles && <CycleWarningBanner />}
      <ReactFlowProvider>
        <div className="graph-body" ref={containerRef}>
          <GraphControls
            containerRef={containerRef}
            showEdgeLabels={showEdgeLabels}
            onToggleEdgeLabels={() => setShowEdgeLabels((value) => !value)}
            highlightErrorsOnly={highlightErrorsOnly}
            onToggleHighlightErrors={() => setHighlightErrorsOnly((value) => !value)}
          />
          <GraphCanvas
            graph={graph}
            showEdgeLabels={showEdgeLabels}
            highlightErrorsOnly={highlightErrorsOnly}
            onSelectAgent={handleSelectAgent}
            onSelectTool={handleSelectTool}
          />
        </div>
      </ReactFlowProvider>
    </div>
  );
}
