import { useEffect, useState } from "react";
import { chronicleApi } from "../../api/client";
import { useAppStore, type InspectorTab } from "../../store/useAppStore";
import type { Event } from "../../types";
import { AgentInspector } from "./AgentInspector";
import { EventInspector } from "./EventInspector";
import { ToolInspector } from "./ToolInspector";

const TABS: { id: InspectorTab; label: string }[] = [
  { id: "event", label: "Event" },
  { id: "agent", label: "Agent" },
  { id: "tools", label: "Tools" },
];

/** Right panel: collapsible Event/Agent/Tools inspector for the selected run. */
export function Inspector() {
  const [collapsed, setCollapsed] = useState(false);
  const [events, setEvents] = useState<Event[]>([]);
  const selectedRunId = useAppStore((state) => state.selectedRunId);
  const inspectorTab = useAppStore((state) => state.inspectorTab);
  const setInspectorTab = useAppStore((state) => state.setInspectorTab);
  const selectedDetail = useAppStore((state) => state.selectedDetail);
  const selectedAgentName = useAppStore((state) => state.selectedAgentName);
  const selectedToolName = useAppStore((state) => state.selectedToolName);
  const selectTool = useAppStore((state) => state.selectTool);

  useEffect(() => {
    if (selectedRunId === null) {
      setEvents([]);
      return;
    }
    let cancelled = false;
    chronicleApi
      .listRunEvents(selectedRunId)
      .then((result) => {
        if (!cancelled) setEvents(result);
      })
      .catch(() => {
        if (!cancelled) setEvents([]);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  return (
    <aside
      className={collapsed ? "detail-inspector collapsed" : "detail-inspector"}
      data-testid="detail-inspector"
    >
      <button
        type="button"
        className="detail-inspector-toggle"
        onClick={() => setCollapsed((value) => !value)}
        aria-label={collapsed ? "Expand detail inspector" : "Collapse detail inspector"}
      >
        {collapsed ? "«" : "»"}
      </button>
      {!collapsed && (
        <div className="detail-inspector-body">
          <div className="inspector-tabs" role="tablist">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={tab.id === inspectorTab}
                className={tab.id === inspectorTab ? "inspector-tab active" : "inspector-tab"}
                onClick={() => setInspectorTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {inspectorTab === "event" && <EventInspector detail={selectedDetail} events={events} />}
          {inspectorTab === "agent" && (
            <AgentInspector agentName={selectedAgentName} events={events} />
          )}
          {inspectorTab === "tools" && (
            <ToolInspector
              events={events}
              selectedToolName={selectedToolName}
              onSelectTool={selectTool}
            />
          )}
        </div>
      )}
    </aside>
  );
}
