import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { TEST_LIST_POLL_INTERVAL_MS } from "../../config";
import type { ChronicleTest, TestStatus } from "../../types";

interface TestListProps {
  onSelectTest: (testId: string) => void;
}

function truncateRunId(runId: string): string {
  return runId.length > 14 ? `${runId.slice(0, 8)}…${runId.slice(-4)}` : runId;
}

function formatRelativeTime(unixSeconds: number): string {
  const diffSeconds = Math.max(0, Math.round(Date.now() / 1000 - unixSeconds));
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.round(diffHours / 24)}d ago`;
}

function resultBadge(status: TestStatus | null): { label: string; className: string } {
  if (status === "pass") return { label: "PASS", className: "test-badge-pass" };
  if (status === "fail") return { label: "FAIL", className: "test-badge-fail" };
  if (status === "error") return { label: "ERROR", className: "test-badge-error" };
  return { label: "NEVER RUN", className: "test-badge-never" };
}

/** Tests tab's default view: polls `GET /tests` and lets the user run, inspect, or delete each one. */
export function TestList({ onSelectTest }: TestListProps) {
  const [tests, setTests] = useState<ChronicleTest[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runningTestId, setRunningTestId] = useState<string | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchTests() {
      setLoading(true);
      try {
        const fetched = await chronicleApi.listTests();
        if (!cancelled) {
          setTests(fetched);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load tests.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchTests();
    const interval = setInterval(fetchTests, TEST_LIST_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  async function handleRun(testId: string) {
    setRunningTestId(testId);
    try {
      await chronicleApi.runTest(testId);
      setTests(await chronicleApi.listTests());
      setError(null);
    } catch (err) {
      setError(err instanceof ChronicleApiError ? err.message : "Could not run test.");
    } finally {
      setRunningTestId(null);
    }
  }

  async function handleDelete(testId: string) {
    try {
      await chronicleApi.deleteTest(testId);
      setTests((current) => current.filter((test) => test.test_id !== testId));
    } catch (err) {
      setError(err instanceof ChronicleApiError ? err.message : "Could not delete test.");
    } finally {
      setConfirmingDeleteId(null);
    }
  }

  if (tests.length === 0 && loading) {
    return <p className="panel-empty">Loading tests…</p>;
  }

  if (tests.length === 0 && error !== null) {
    return <p className="panel-error">{error}</p>;
  }

  if (tests.length === 0) {
    return <p className="panel-empty">No tests yet. Create your first test from any run.</p>;
  }

  return (
    <div className="test-list" data-testid="test-list">
      {error !== null && <p className="panel-error">{error}</p>}
      <ul>
        {tests.map((test) => {
          const badge = resultBadge(test.last_result);
          return (
            <li key={test.test_id} className="test-row">
              <button
                type="button"
                className="test-row-main"
                onClick={() => onSelectTest(test.test_id)}
              >
                <span className="test-row-name">{test.name}</span>
                <span className="test-row-meta">{truncateRunId(test.source_run_id)}</span>
                <span className="test-row-meta">
                  {test.last_run_at !== null ? formatRelativeTime(test.last_run_at) : "never run"}
                </span>
                <span className={`test-badge ${badge.className}`}>{badge.label}</span>
              </button>
              <div className="test-row-actions">
                <button
                  type="button"
                  onClick={() => handleRun(test.test_id)}
                  disabled={runningTestId === test.test_id}
                >
                  {runningTestId === test.test_id ? "Running…" : "Run"}
                </button>
                {confirmingDeleteId === test.test_id ? (
                  <span className="test-delete-confirm">
                    <button type="button" onClick={() => handleDelete(test.test_id)}>
                      Confirm delete
                    </button>
                    <button type="button" onClick={() => setConfirmingDeleteId(null)}>
                      Cancel
                    </button>
                  </span>
                ) : (
                  <button type="button" onClick={() => setConfirmingDeleteId(test.test_id)}>
                    Delete
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
