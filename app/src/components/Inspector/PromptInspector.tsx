import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { useAppStore } from "../../store/useAppStore";
import type { PromptDetail, PromptDiffResult, PromptMessage, PromptSummary } from "../../types";

interface PromptInspectorProps {
  runId: string | null;
}

function formatTimestamp(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString();
}

/** Rough token estimate (~4 chars/token) since the server only reports a per-prompt total. */
function estimateTokens(content: string): number {
  return Math.max(1, Math.ceil(content.length / 4));
}

function PromptMessageRow({ message }: { message: PromptMessage }) {
  return (
    <li className={`prompt-message prompt-message-${message.role}`}>
      <div className="prompt-message-header">
        <span className="prompt-message-role">{message.role}</span>
        <span className="prompt-message-tokens">~{estimateTokens(message.content)} tok</span>
      </div>
      <pre className="code-block">{message.content}</pre>
    </li>
  );
}

/** Prompts tab: a step list on the left, full prompt content (and optional diff) on the right. */
export function PromptInspector({ runId }: PromptInspectorProps) {
  const allRuns = useAppStore((state) => state.runs);
  const [summaries, setSummaries] = useState<PromptSummary[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PromptDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);
  const [compareRunId, setCompareRunId] = useState<string | null>(null);
  const [compareSummaries, setCompareSummaries] = useState<PromptSummary[]>([]);
  const [diff, setDiff] = useState<PromptDiffResult | null>(null);

  useEffect(() => {
    setSummaries([]);
    setSelectedEventId(null);
    setDetail(null);
    setError(null);
    setComparing(false);
    setDiff(null);
    if (runId === null) return;
    let cancelled = false;
    chronicleApi
      .getRunPrompts(runId)
      .then((fetched) => {
        if (!cancelled) setSummaries(fetched);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load prompts.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  useEffect(() => {
    setDiff(null);
    if (runId === null || selectedEventId === null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    chronicleApi
      .getRunPrompt(runId, selectedEventId)
      .then((fetched) => {
        if (!cancelled) setDetail(fetched);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, selectedEventId]);

  useEffect(() => {
    if (compareRunId === null) {
      setCompareSummaries([]);
      return;
    }
    let cancelled = false;
    chronicleApi
      .getRunPrompts(compareRunId)
      .then((fetched) => {
        if (!cancelled) setCompareSummaries(fetched);
      })
      .catch(() => {
        if (!cancelled) setCompareSummaries([]);
      });
    return () => {
      cancelled = true;
    };
  }, [compareRunId]);

  function startComparing() {
    setComparing(true);
    setCompareRunId(runId);
  }

  async function handleCompareWith(targetEventId: string) {
    if (runId === null || selectedEventId === null || compareRunId === null) return;
    try {
      const result = await chronicleApi.getPromptsDiff({
        runIdA: runId,
        eventIdA: selectedEventId,
        runIdB: compareRunId,
        eventIdB: targetEventId,
      });
      setDiff(result);
    } catch {
      setDiff(null);
    }
  }

  if (runId === null) {
    return <p className="panel-empty">Select a run to inspect its prompts.</p>;
  }
  if (error !== null) {
    return <p className="panel-error">{error}</p>;
  }
  if (summaries.length === 0) {
    return <p className="panel-empty">No prompts recorded for this run.</p>;
  }

  return (
    <div className="prompt-inspector" data-testid="prompt-inspector">
      <ul className="prompt-list">
        {summaries.map((summary) => (
          <li key={summary.event_id}>
            <button
              type="button"
              className={summary.event_id === selectedEventId ? "prompt-row active" : "prompt-row"}
              onClick={() => setSelectedEventId(summary.event_id)}
            >
              <span>Step {summary.step_index}</span>
              <span>{summary.agent_name ?? "unknown"}</span>
              <span>{formatTimestamp(summary.timestamp)}</span>
              <span>{summary.total_tokens} tokens</span>
            </button>
          </li>
        ))}
      </ul>

      <div className="prompt-detail">
        {detail === null ? (
          <p className="panel-empty">Select a prompt to view its content.</p>
        ) : (
          <>
            {detail.system_prompt !== null && (
              <details className="prompt-system-prompt">
                <summary>System prompt</summary>
                <pre className="code-block">{detail.system_prompt}</pre>
              </details>
            )}
            <ul className="prompt-messages">
              {[...detail.user_messages, ...detail.assistant_messages].map((message, index) => (
                <PromptMessageRow key={index} message={message} />
              ))}
            </ul>

            {!comparing ? (
              <button type="button" onClick={startComparing}>
                Compare with another prompt
              </button>
            ) : (
              <div className="prompt-compare" data-testid="prompt-compare">
                <label>
                  Run
                  <select
                    value={compareRunId ?? ""}
                    onChange={(event) => setCompareRunId(event.target.value || null)}
                  >
                    {allRuns.map((run) => (
                      <option key={run.run_id} value={run.run_id}>
                        {run.run_id}
                      </option>
                    ))}
                  </select>
                </label>
                <ul className="prompt-compare-list">
                  {compareSummaries
                    .filter((summary) => summary.event_id !== selectedEventId)
                    .map((summary) => (
                      <li key={summary.event_id}>
                        <button type="button" onClick={() => handleCompareWith(summary.event_id)}>
                          Step {summary.step_index} ({summary.agent_name ?? "unknown"})
                        </button>
                      </li>
                    ))}
                </ul>
              </div>
            )}

            {diff !== null && (
              <div className="prompt-diff-result" data-testid="prompt-diff-result">
                <div className="prompt-diff-stats">
                  <span className="diff-added">+{diff.additions}</span>
                  <span className="diff-removed">-{diff.deletions}</span>
                  <span className="diff-same">{diff.unchanged} unchanged</span>
                </div>
                {/*
                  Safe: diff_html is built server-side entirely from html.escape()'d text
                  wrapped in a fixed set of <span class="add"|"del"|"same"> tags (see
                  server/src/prompt_diff.py) - no raw prompt content, attributes, or other
                  tags ever reach the DOM unescaped.
                */}
                <pre
                  className="code-block prompt-diff-html"
                  dangerouslySetInnerHTML={{ __html: diff.diff_html }}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
