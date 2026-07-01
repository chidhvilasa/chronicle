import { useAppStore } from "../store/useAppStore";
import { Timeline } from "./Timeline";
import { DiffPanel } from "./panels/DiffPanel";
import { InspectorPanel } from "./panels/InspectorPanel";

/** Main content area; renders whichever panel the top nav's tabs select. */
export function MainPanel() {
  const activePanel = useAppStore((state) => state.activePanel);
  const selectedRunId = useAppStore((state) => state.selectedRunId);
  const setSelectedDetail = useAppStore((state) => state.setSelectedDetail);

  return (
    <main className="main-panel" data-testid="main-panel">
      {activePanel === "timeline" && (
        <Timeline runId={selectedRunId} onSegmentSelect={setSelectedDetail} />
      )}
      {activePanel === "inspector" && <InspectorPanel />}
      {activePanel === "diff" && <DiffPanel />}
    </main>
  );
}
