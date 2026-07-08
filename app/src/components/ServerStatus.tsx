import { useEffect, useRef, useState } from "react";
import { chronicleApi } from "../api/client";
import { SERVER_STATUS_POLL_INTERVAL_MS } from "../config";

/**
 * Full-screen onboarding overlay shown until the Chronicle server answers
 * `GET /health`. Chronicle doesn't bundle a Tauri sidecar binary (see
 * KNOWN_ISSUES.md), so a fresh install has no server running yet — this is
 * the fallback that tells the user how to start one instead of showing a
 * blank, confusing app.
 */
export function ServerStatus() {
  const [serverUp, setServerUp] = useState(true);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const pollingRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function checkHealth() {
      if (pollingRef.current) return;
      pollingRef.current = true;
      try {
        await chronicleApi.checkHealth();
        if (!cancelled) setServerUp(true);
      } catch {
        if (!cancelled) setServerUp(false);
      } finally {
        pollingRef.current = false;
      }
    }

    checkHealth();
    const interval = setInterval(checkHealth, SERVER_STATUS_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (serverUp) return null;

  return (
    <div className="server-status-overlay" role="alert" data-testid="server-status-overlay">
      <div className="server-status-card">
        <h1>Start the Chronicle Server</h1>
        <p>Chronicle couldn't reach the local server. Install the SDK and start it, then this screen will disappear automatically.</p>

        <pre className="code-block">pip install "chronicle-sdk[all]"</pre>
        <pre className="code-block">chronicle start</pre>

        <button type="button" className="server-status-retry" onClick={() => checkHealthNow(setServerUp)}>
          Check Again
        </button>

        <details
          className="server-status-advanced"
          open={advancedOpen}
          onToggle={(e) => setAdvancedOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary>Advanced</summary>
          <pre className="code-block">uvicorn src.main:app --port 7823</pre>
        </details>
      </div>
    </div>
  );
}

async function checkHealthNow(setServerUp: (up: boolean) => void) {
  try {
    await chronicleApi.checkHealth();
    setServerUp(true);
  } catch {
    setServerUp(false);
  }
}
