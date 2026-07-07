import { useEffect, useState } from "react";
import { chronicleApi } from "../api/client";
import { HEALTH_CHECK_INTERVAL_MS } from "../config";
import { useAppStore, type PanelId } from "../store/useAppStore";

const PANELS: { id: PanelId; label: string }[] = [
  { id: "timeline", label: "Timeline" },
  { id: "inspector", label: "Inspector" },
  { id: "diff", label: "Diff" },
  { id: "tests", label: "Tests" },
  { id: "performance", label: "Performance" },
  { id: "graph", label: "Graph" },
];

/** Top navigation bar: brand, panel switcher tabs, settings icon, connection status. */
export function TopNav() {
  const activePanel = useAppStore((state) => state.activePanel);
  const setActivePanel = useAppStore((state) => state.setActivePanel);
  const [serverReachable, setServerReachable] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function checkHealth() {
      try {
        await chronicleApi.checkHealth();
        if (!cancelled) setServerReachable(true);
      } catch {
        if (!cancelled) setServerReachable(false);
      }
    }

    checkHealth();
    const interval = setInterval(checkHealth, HEALTH_CHECK_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="top-nav" data-testid="top-nav">
      <div className="top-nav-brand">
        <span className="top-nav-logo" aria-hidden="true">
          ◎
        </span>
        <span className="top-nav-title">Chronicle</span>
      </div>

      <nav className="top-nav-tabs">
        {PANELS.map((panel) => (
          <button
            key={panel.id}
            type="button"
            className={panel.id === activePanel ? "top-nav-tab active" : "top-nav-tab"}
            onClick={() => setActivePanel(panel.id)}
          >
            {panel.label}
          </button>
        ))}
      </nav>

      <div className="top-nav-actions">
        <span
          className={serverReachable ? "connection-dot connected" : "connection-dot disconnected"}
          data-testid="connection-status"
          role="status"
          aria-label={serverReachable ? "Chronicle server connected" : "Chronicle server unreachable"}
          title={serverReachable ? "Chronicle server connected" : "Chronicle server unreachable"}
        />
        <button type="button" className="settings-icon" aria-label="Settings" title="Settings (coming soon)">
          ⚙
        </button>
      </div>
    </header>
  );
}
