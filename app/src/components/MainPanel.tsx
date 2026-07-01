import { useAppStore } from "../store/useAppStore";
import { Diff } from "./Diff";
import { Timeline } from "./Timeline";
import { InspectorPanel } from "./panels/InspectorPanel";

/** Main content area; renders whichever panel the top nav's tabs select. */
export function MainPanel() {
  const activePanel = useAppStore((state) => state.activePanel);
  const selectedRunId = useAppStore((state) => state.selectedRunId);
  const selectDetail = useAppStore((state) => state.selectDetail);
  const selectAgent = useAppStore((state) => state.selectAgent);

  return (
    <main className="main-panel" data-testid="main-panel">
      {activePanel === "timeline" && (
        <Timeline runId={selectedRunId} onSegmentSelect={selectDetail} onAgentSelect={selectAgent} />
      )}
      {activePanel === "inspector" && <InspectorPanel />}
      {activePanel === "diff" && <Diff />}
    </main>
  );
}
