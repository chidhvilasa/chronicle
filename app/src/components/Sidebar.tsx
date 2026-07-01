import type { ChronicleRun } from "../types";

interface SidebarProps {
  runs: ChronicleRun[];
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
}

function formatStartedAt(startedAt: number): string {
  return new Date(startedAt * 1000).toLocaleString();
}

/** Left-hand panel listing every captured run, newest first. */
export function Sidebar({ runs, selectedRunId, onSelectRun }: SidebarProps) {
  if (runs.length === 0) {
    return (
      <aside className="sidebar" data-testid="sidebar">
        <p className="sidebar-empty">No runs captured yet.</p>
      </aside>
    );
  }

  return (
    <aside className="sidebar" data-testid="sidebar">
      <ul className="run-list">
        {runs.map((run) => (
          <li key={run.id}>
            <button
              type="button"
              className={run.id === selectedRunId ? "run-item active" : "run-item"}
              onClick={() => onSelectRun(run.id)}
            >
              <span className="run-id">{run.id}</span>
              <span className="run-meta">
                {run.event_count} events · {formatStartedAt(run.started_at)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
