import type { Run } from "../../types";

interface RunSelectorProps {
  runs: Run[];
  runAId: string | null;
  runBId: string | null;
  onSelectRunA: (runId: string | null) => void;
  onSelectRunB: (runId: string | null) => void;
}

/** Two run dropdowns; each disables the run currently selected in the other. */
export function RunSelector({ runs, runAId, runBId, onSelectRunA, onSelectRunB }: RunSelectorProps) {
  return (
    <div className="diff-run-selector" data-testid="diff-run-selector">
      <label>
        Run A
        <select
          value={runAId ?? ""}
          onChange={(event) => onSelectRunA(event.target.value || null)}
          aria-label="Run A"
        >
          <option value="">Select a run…</option>
          {runs.map((run) => (
            <option key={run.run_id} value={run.run_id} disabled={run.run_id === runBId}>
              {run.run_id}
            </option>
          ))}
        </select>
      </label>
      <label>
        Run B
        <select
          value={runBId ?? ""}
          onChange={(event) => onSelectRunB(event.target.value || null)}
          aria-label="Run B"
        >
          <option value="">Select a run…</option>
          {runs.map((run) => (
            <option key={run.run_id} value={run.run_id} disabled={run.run_id === runAId}>
              {run.run_id}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
