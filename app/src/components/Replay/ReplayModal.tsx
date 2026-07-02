import { useEffect, useRef, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { REPLAY_POLL_INTERVAL_MS, REPLAY_POLL_TIMEOUT_MS } from "../../config";
import { useAppStore } from "../../store/useAppStore";
import type { Snapshot } from "../../types";

interface ReplayModalProps {
  runId: string;
  snapshotId: string;
  onClose: () => void;
}

function summarizeGraphState(snapshot: Snapshot): string {
  const messageCount = snapshot.messages.length;
  const lastToolResult = snapshot.tool_results[snapshot.tool_results.length - 1];
  const lastToolResultText =
    lastToolResult === undefined ? "none" : JSON.stringify(lastToolResult).slice(0, 200);
  return `${messageCount} message${messageCount === 1 ? "" : "s"} · last tool result: ${lastToolResultText}`;
}

/** Waits until `runId` shows up in `GET /runs` with a non-"running" status, or times out. */
async function waitForRunToFinish(runId: string): Promise<void> {
  const deadline = Date.now() + REPLAY_POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const runs = await chronicleApi.listRuns();
    const run = runs.find((candidate) => candidate.run_id === runId);
    if (run !== undefined && run.status !== "running") return;
    await new Promise((resolve) => setTimeout(resolve, REPLAY_POLL_INTERVAL_MS));
  }
  throw new ChronicleApiError("Timed out waiting for the replay to finish.");
}

/** Modal for replaying a run from a snapshot, with an optional JSON modifications editor. */
export function ReplayModal({ runId, snapshotId, onClose }: ReplayModalProps) {
  const selectRun = useAppStore((state) => state.selectRun);
  const setActivePanel = useAppStore((state) => state.setActivePanel);
  const setDiffPrefill = useAppStore((state) => state.setDiffPrefill);
  const showToast = useAppStore((state) => state.showToast);

  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [modificationsText, setModificationsText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;
    chronicleApi
      .getSnapshot(runId, snapshotId)
      .then((result) => {
        if (!cancelledRef.current) setSnapshot(result);
      })
      .catch((err: unknown) => {
        if (!cancelledRef.current) {
          setLoadError(err instanceof ChronicleApiError ? err.message : "Could not load snapshot.");
        }
      });
    return () => {
      cancelledRef.current = true;
    };
  }, [runId, snapshotId]);

  async function submitReplay(modifications: Record<string, unknown>) {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const { run_id: newRunId } = await chronicleApi.replay(runId, snapshotId, modifications);
      await waitForRunToFinish(newRunId);
      if (cancelledRef.current) return;
      selectRun(newRunId);
      onClose();
      showToast({
        message: "Replay complete. Compare with original?",
        actionLabel: "Compare",
        onAction: () => {
          setDiffPrefill({ runAId: runId, runBId: newRunId });
          setActivePanel("diff");
        },
      });
    } catch (err) {
      if (!cancelledRef.current) {
        setSubmitError(err instanceof ChronicleApiError ? err.message : "Replay failed.");
      }
    } finally {
      if (!cancelledRef.current) setSubmitting(false);
    }
  }

  function handleReplayAsIs() {
    void submitReplay({});
  }

  function handleReplayWithModifications() {
    const trimmed = modificationsText.trim();
    if (trimmed === "") {
      void submitReplay({});
      return;
    }
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(trimmed) as Record<string, unknown>;
    } catch {
      setSubmitError("Modifications must be valid JSON.");
      return;
    }
    void submitReplay(parsed);
  }

  return (
    <div className="modal-overlay" data-testid="replay-modal-overlay" onClick={onClose}>
      <div
        className="modal-content replay-modal"
        data-testid="replay-modal"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <h3>Replay run</h3>
          <button type="button" className="modal-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>

        {loadError !== null && <p className="panel-error">{loadError}</p>}

        {loadError === null && snapshot === null && <p className="panel-empty">Loading snapshot…</p>}

        {snapshot !== null && (
          <>
            <dl className="event-meta">
              <dt>Step</dt>
              <dd>{snapshot.step_index}</dd>
              <dt>Timestamp</dt>
              <dd>{new Date(snapshot.timestamp * 1000).toLocaleString()}</dd>
              <dt>Agent</dt>
              <dd>{snapshot.agent_name ?? "unknown"}</dd>
              <dt>Graph state</dt>
              <dd>{summarizeGraphState(snapshot)}</dd>
            </dl>

            <label className="replay-modifications-label">
              Modifications (optional JSON)
              <textarea
                className="replay-modifications-input"
                value={modificationsText}
                onChange={(event) => setModificationsText(event.target.value)}
                placeholder={'{ "override_key": "new_value" }'}
                rows={6}
                disabled={submitting}
              />
            </label>

            {submitError !== null && <p className="panel-error replay-error">{submitError}</p>}

            {submitting ? (
              <p className="replay-spinner" role="status">
                Replaying from step {snapshot.step_index}...
              </p>
            ) : (
              <div className="replay-modal-actions">
                <button type="button" onClick={handleReplayAsIs}>
                  Replay as-is
                </button>
                <button type="button" onClick={handleReplayWithModifications}>
                  Replay with modifications
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
