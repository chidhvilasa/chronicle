import { useState } from "react";
import { useAppStore } from "../store/useAppStore";
import { isEventDetail } from "../types";

/** Right panel: collapsible detail view for whichever event/segment is selected. */
export function DetailInspector() {
  const [collapsed, setCollapsed] = useState(false);
  const selectedDetail = useAppStore((state) => state.selectedDetail);

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
          {selectedDetail === null ? (
            <p className="panel-empty">Select an event or segment to inspect its details.</p>
          ) : isEventDetail(selectedDetail) ? (
            <>
              <h2>{selectedDetail.event_type}</h2>
              <dl>
                <dt>Event ID</dt>
                <dd>{selectedDetail.event_id}</dd>
                <dt>Agent</dt>
                <dd>{selectedDetail.agent_name ?? "unknown"}</dd>
              </dl>
              <pre>{JSON.stringify(selectedDetail.data, null, 2)}</pre>
              {selectedDetail.error !== null && (
                <p className="detail-error">{selectedDetail.error}</p>
              )}
            </>
          ) : (
            <>
              <h2>{selectedDetail.type}</h2>
              <dl>
                <dt>Label</dt>
                <dd>{selectedDetail.label}</dd>
                <dt>Duration</dt>
                <dd>{selectedDetail.duration_ms.toFixed(1)}ms</dd>
              </dl>
              {selectedDetail.token_usage !== null && (
                <pre>{JSON.stringify(selectedDetail.token_usage, null, 2)}</pre>
              )}
            </>
          )}
        </div>
      )}
    </aside>
  );
}
