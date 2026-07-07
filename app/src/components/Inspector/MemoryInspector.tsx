import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import type { MemorySnapshot } from "../../types";

interface MemoryInspectorProps {
  runId: string | null;
}

function formatTimestamp(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString();
}

function summaryLabel(snapshot: MemorySnapshot): string {
  const changedLabel = snapshot.keys_changed.length === 1 ? "key" : "keys";
  return `+${snapshot.keys_added.length} keys, -${snapshot.keys_removed.length} keys, ~${snapshot.keys_changed.length} ${changedLabel}`;
}

function formatValue(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

/** Memory tab: a timeline of memory_update events on the left, a key-level diff on the right. */
export function MemoryInspector({ runId }: MemoryInspectorProps) {
  const [snapshots, setSnapshots] = useState<MemorySnapshot[]>([]);
  const [emptyMessage, setEmptyMessage] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [showUnchanged, setShowUnchanged] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSnapshots([]);
    setEmptyMessage(null);
    setSelectedEventId(null);
    setError(null);
    setShowUnchanged(false);
    if (runId === null) return;
    let cancelled = false;
    chronicleApi
      .getRunMemory(runId)
      .then((fetched) => {
        if (cancelled) return;
        setSnapshots(fetched.snapshots);
        setEmptyMessage(fetched.message);
        if (fetched.snapshots.length > 0) setSelectedEventId(fetched.snapshots[0].event_id);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load memory updates.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (runId === null) {
    return <p className="panel-empty">Select a run to inspect its memory.</p>;
  }
  if (error !== null) {
    return <p className="panel-error">{error}</p>;
  }
  if (snapshots.length === 0) {
    return (
      <p className="panel-empty">
        {emptyMessage ?? "No memory updates recorded for this run."}
      </p>
    );
  }

  const selected = snapshots.find((snapshot) => snapshot.event_id === selectedEventId) ?? null;
  const unchangedKeys =
    selected === null
      ? []
      : Array.from(
          new Set([...Object.keys(selected.memory_before), ...Object.keys(selected.memory_after)])
        ).filter(
          (key) =>
            !selected.keys_added.includes(key) &&
            !selected.keys_removed.includes(key) &&
            !selected.keys_changed.includes(key)
        );

  return (
    <div className="memory-inspector" data-testid="memory-inspector">
      <ul className="memory-timeline">
        {snapshots.map((snapshot) => (
          <li key={snapshot.event_id}>
            <button
              type="button"
              className={snapshot.event_id === selectedEventId ? "memory-row active" : "memory-row"}
              onClick={() => setSelectedEventId(snapshot.event_id)}
            >
              <span>Step {snapshot.step_index}</span>
              <span>{snapshot.agent_name ?? "unknown"}</span>
              <span>{formatTimestamp(snapshot.timestamp)}</span>
              <span>{summaryLabel(snapshot)}</span>
            </button>
          </li>
        ))}
      </ul>

      <div className="memory-detail">
        {selected === null ? (
          <p className="panel-empty">Select a memory update to view its diff.</p>
        ) : (
          <>
            {selected.keys_added.map((key) => (
              <div key={`added-${key}`} className="memory-key-row memory-key-added">
                <strong>{key}</strong>
                <pre className="code-block">{formatValue(selected.memory_after[key])}</pre>
              </div>
            ))}
            {selected.keys_removed.map((key) => (
              <div key={`removed-${key}`} className="memory-key-row memory-key-removed">
                <strong>{key}</strong>
                <pre className="code-block">{formatValue(selected.memory_before[key])}</pre>
              </div>
            ))}
            {selected.keys_changed.map((key) => (
              <div key={`changed-${key}`} className="memory-key-row memory-key-changed">
                <strong>{key}</strong>
                <div className="memory-key-changed-values">
                  <pre className="code-block">{formatValue(selected.memory_before[key])}</pre>
                  <pre className="code-block">{formatValue(selected.memory_after[key])}</pre>
                </div>
              </div>
            ))}

            {unchangedKeys.length > 0 && (
              <button type="button" onClick={() => setShowUnchanged((value) => !value)}>
                {showUnchanged ? "Hide unchanged keys" : "Show unchanged keys"}
              </button>
            )}
            {showUnchanged &&
              unchangedKeys.map((key) => (
                <div key={`unchanged-${key}`} className="memory-key-row memory-key-unchanged">
                  <strong>{key}</strong>
                  <pre className="code-block">{formatValue(selected.memory_after[key])}</pre>
                </div>
              ))}
          </>
        )}
      </div>
    </div>
  );
}
