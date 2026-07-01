import { useAppStore } from "../store/useAppStore";
import { DiffPanel } from "./panels/DiffPanel";
import { InspectorPanel } from "./panels/InspectorPanel";
import { TimelinePanel } from "./panels/TimelinePanel";

/** Main content area; renders whichever panel the top nav's tabs select. */
export function MainPanel() {
  const activePanel = useAppStore((state) => state.activePanel);

  return (
    <main className="main-panel" data-testid="main-panel">
      {activePanel === "timeline" && <TimelinePanel />}
      {activePanel === "inspector" && <InspectorPanel />}
      {activePanel === "diff" && <DiffPanel />}
    </main>
  );
}
