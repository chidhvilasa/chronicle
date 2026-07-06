import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { useAppStore } from "../../store/useAppStore";
import type { ChronicleTest, TestResult as TestResultData } from "../../types";

interface TestResultPanelProps {
  testId: string;
  onBack: () => void;
}

function historyBlockClass(status: string): string {
  if (status === "pass") return "history-block-pass";
  if (status === "fail") return "history-block-fail";
  return "history-block-error";
}

/** Main-panel detail view for one test: history bar, most recent result, and a re-run button. */
export function TestResultPanel({ testId, onBack }: TestResultPanelProps) {
  const [test, setTest] = useState<ChronicleTest | null>(null);
  const [history, setHistory] = useState<TestResultData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const selectRun = useAppStore((state) => state.selectRun);
  const setActivePanel = useAppStore((state) => state.setActivePanel);

  async function load() {
    setLoading(true);
    try {
      const [testDetail, testHistory] = await Promise.all([
        chronicleApi.getTest(testId),
        chronicleApi.getTestHistory(testId),
      ]);
      setTest(testDetail);
      setHistory(testHistory);
      setError(null);
    } catch (err) {
      setError(err instanceof ChronicleApiError ? err.message : "Could not load test.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // Re-runs only when `testId` changes; `load` is intentionally re-created each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testId]);

  async function handleRunAgain() {
    setRunning(true);
    try {
      await chronicleApi.runTest(testId);
      await load();
    } catch (err) {
      setError(err instanceof ChronicleApiError ? err.message : "Could not run test.");
    } finally {
      setRunning(false);
    }
  }

  function handleViewReplayRun(replayRunId: string) {
    selectRun(replayRunId);
    setActivePanel("timeline");
  }

  if (loading && test === null) {
    return <p className="panel-empty">Loading test…</p>;
  }

  if (error !== null && test === null) {
    return <p className="panel-error">{error}</p>;
  }

  if (test === null) return null;

  const mostRecent = history[0] ?? null;
  const oldestFirst = history.slice(0, 10).reverse();

  return (
    <div className="test-result-panel" data-testid="test-result-panel">
      <button type="button" className="test-result-back" onClick={onBack}>
        ← Back to tests
      </button>
      <h3>{test.name}</h3>
      <p className="test-result-source">Source run: {test.source_run_id}</p>

      <div className="test-result-history-bar" data-testid="test-result-history-bar">
        {oldestFirst.length === 0 && <span className="panel-empty">No runs yet.</span>}
        {oldestFirst.map((result) => (
          <span
            key={result.result_id}
            className={`history-block ${historyBlockClass(result.status)}`}
            title={result.status}
          />
        ))}
      </div>

      {mostRecent !== null && (
        <div className="test-result-detail">
          <h4>Most recent result: {mostRecent.status}</h4>
          {mostRecent.error_reason !== null && <p className="panel-error">{mostRecent.error_reason}</p>}
          <ul className="assertion-result-list">
            {mostRecent.assertion_results.map((assertionResult) => (
              <li key={assertionResult.assertion_id}>
                <span aria-hidden="true">{assertionResult.passed ? "✓" : "✗"}</span>{" "}
                {assertionResult.assertion_type}: {assertionResult.reason}
              </li>
            ))}
          </ul>
          {mostRecent.replay_run_id !== null && (
            <button type="button" onClick={() => handleViewReplayRun(mostRecent.replay_run_id as string)}>
              View replay run
            </button>
          )}
        </div>
      )}

      {error !== null && <p className="panel-error">{error}</p>}

      <button type="button" onClick={handleRunAgain} disabled={running}>
        {running ? "Running…" : "Run again"}
      </button>
    </div>
  );
}
