import { useEffect } from "react";
import { chronicleApi, ChronicleApiError } from "../api/client";
import { RUN_LIST_POLL_INTERVAL_MS } from "../config";
import { useAppStore } from "../store/useAppStore";
import { getReplayMetadata, type Run } from "../types";

function formatRelativeTime(unixSeconds: number): string {
  const diffSeconds = Math.max(0, Math.round(Date.now() / 1000 - unixSeconds));
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.round(diffHours / 24)}d ago`;
}

function formatDuration(startedAt: number, finishedAt: number): string {
  const seconds = Math.max(0, finishedAt - startedAt);
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds % 60)}s`;
}

function truncateRunId(runId: string): string {
  return runId.length > 14 ? `${runId.slice(0, 8)}…${runId.slice(-4)}` : runId;
}

/** Maps the server's `running`/`error` run status to a display badge. */
function statusBadge(status: string): "running" | "complete" | "failed" {
  if (status === "error") return "failed";
  if (status === "complete") return "complete";
  return "running";
}

function RunCard({ run, isSelected, onSelect }: { run: Run; isSelected: boolean; onSelect: () => void }) {
  const badge = statusBadge(run.status);
  const replayMeta = getReplayMetadata(run);
  return (
    <li>
      <button type="button" className={isSelected ? "run-card active" : "run-card"} onClick={onSelect}>
        <span className="run-card-id-row">
          <span className="run-card-id">{truncateRunId(run.run_id)}</span>
          {replayMeta !== null && (
            <span
              className="run-card-replay-badge"
              data-testid="replay-badge"
              title={`Replayed from run ${replayMeta.sourceRunId} at step ${replayMeta.stepIndex}`}
            >
              REPLAY
            </span>
          )}
        </span>
        <span className={`run-card-status status-${badge}`}>{badge}</span>
        <span className="run-card-meta">{formatRelativeTime(run.started_at)}</span>
        <span className="run-card-meta">{run.total_tokens} tokens</span>
        <span className="run-card-meta">{formatDuration(run.started_at, run.finished_at)}</span>
      </button>
    </li>
  );
}

/** Left sidebar: polls `GET /runs` and lets the user select the active run. */
export function RunList() {
  const runs = useAppStore((state) => state.runs);
  const selectedRunId = useAppStore((state) => state.selectedRunId);
  const loading = useAppStore((state) => state.loading);
  const error = useAppStore((state) => state.error);
  const setRuns = useAppStore((state) => state.setRuns);
  const setLoading = useAppStore((state) => state.setLoading);
  const setError = useAppStore((state) => state.setError);
  const selectRun = useAppStore((state) => state.selectRun);

  useEffect(() => {
    let cancelled = false;

    async function fetchRuns() {
      setLoading(true);
      try {
        const fetchedRuns = await chronicleApi.listRuns();
        if (cancelled) return;
        setRuns(fetchedRuns);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ChronicleApiError ? err.message : "Could not load runs.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchRuns();
    const interval = setInterval(fetchRuns, RUN_LIST_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [setRuns, setLoading, setError]);

  if (runs.length === 0 && loading) {
    return (
      <aside className="run-list" data-testid="run-list">
        <p className="run-list-empty">Loading runs…</p>
      </aside>
    );
  }

  if (runs.length === 0 && error !== null) {
    return (
      <aside className="run-list" data-testid="run-list">
        <p className="run-list-error">{error}</p>
      </aside>
    );
  }

  if (runs.length === 0) {
    return (
      <aside className="run-list" data-testid="run-list">
        <p className="run-list-empty">No runs yet. Instrument your agent with the Chronicle SDK.</p>
      </aside>
    );
  }

  return (
    <aside className="run-list" data-testid="run-list">
      <ul>
        {runs.map((run) => (
          <RunCard
            key={run.run_id}
            run={run}
            isSelected={run.run_id === selectedRunId}
            onSelect={() => selectRun(run.run_id)}
          />
        ))}
      </ul>
    </aside>
  );
}
