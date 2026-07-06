import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import type { AssertionType, ChronicleAssertion, OnFail, SnapshotSummary } from "../../types";

interface CreateTestModalProps {
  sourceRunId: string;
  onClose: () => void;
}

const ASSERTION_TYPES: { value: AssertionType; label: string; needsTarget: boolean }[] = [
  { value: "output_contains", label: "Output contains", needsTarget: true },
  { value: "output_not_contains", label: "Output does not contain", needsTarget: true },
  { value: "output_matches_regex", label: "Output matches regex", needsTarget: true },
  { value: "tool_called", label: "Tool called", needsTarget: true },
  { value: "tool_not_called", label: "Tool not called", needsTarget: true },
  { value: "token_count_under", label: "Token count under", needsTarget: true },
  { value: "latency_under_ms", label: "Latency under (ms)", needsTarget: true },
  { value: "no_errors", label: "No errors", needsTarget: false },
  { value: "custom", label: "Custom", needsTarget: true },
];

interface AssertionDraft {
  key: string;
  assertion_type: AssertionType;
  target: string;
  agent_name: string;
  on_fail: OnFail;
}

let draftCounter = 0;

function newDraft(): AssertionDraft {
  draftCounter += 1;
  return {
    key: `draft-${draftCounter}`,
    assertion_type: "output_contains",
    target: "",
    agent_name: "",
    on_fail: "fail",
  };
}

/** Opened from a run card's "Create Test" button; saves a `ChronicleTest` sourced from that run. */
export function CreateTestModal({ sourceRunId, onClose }: CreateTestModalProps) {
  const [name, setName] = useState("");
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [snapshotId, setSnapshotId] = useState<string | null>(null);
  const [assertions, setAssertions] = useState<AssertionDraft[]>([newDraft()]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    chronicleApi
      .listRunSnapshots(sourceRunId)
      .then((result) => {
        if (cancelled) return;
        setSnapshots(result);
        if (result.length > 0) setSnapshotId(result[0].snapshot_id);
      })
      .catch(() => {
        if (!cancelled) setSnapshots([]);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceRunId]);

  function updateAssertion(key: string, patch: Partial<AssertionDraft>) {
    setAssertions((current) => current.map((draft) => (draft.key === key ? { ...draft, ...patch } : draft)));
  }

  function removeAssertion(key: string) {
    setAssertions((current) => current.filter((draft) => draft.key !== key));
  }

  async function handleSave() {
    if (name.trim() === "") {
      setError("Test name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload: Omit<ChronicleAssertion, "assertion_id">[] = assertions.map((draft) => ({
        assertion_type: draft.assertion_type,
        target: draft.target,
        agent_name: draft.agent_name.trim() === "" ? null : draft.agent_name,
        on_fail: draft.on_fail,
      }));
      await chronicleApi.createTest({
        name,
        sourceRunId,
        sourceSnapshotId: snapshotId,
        assertions: payload,
      });
      onClose();
    } catch (err) {
      setError(err instanceof ChronicleApiError ? err.message : "Could not create test.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" data-testid="create-test-modal-overlay" onClick={onClose}>
      <div
        className="modal-content create-test-modal"
        data-testid="create-test-modal"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <h3>Create test</h3>
          <button type="button" className="modal-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>

        <label className="create-test-field">
          Test name
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="agent still greets the user"
            required
          />
        </label>

        <label className="create-test-field">
          Source run
          <input type="text" value={sourceRunId} readOnly />
        </label>

        <label className="create-test-field">
          Snapshot
          <select
            aria-label="Snapshot"
            value={snapshotId ?? ""}
            onChange={(event) => setSnapshotId(event.target.value || null)}
          >
            {snapshots.length === 0 && <option value="">No snapshots available</option>}
            {snapshots.map((snapshot) => (
              <option key={snapshot.snapshot_id} value={snapshot.snapshot_id}>
                {`Step ${snapshot.step_index} - ${snapshot.agent_name ?? "unknown"} - ${new Date(
                  snapshot.timestamp * 1000
                ).toLocaleString()}`}
              </option>
            ))}
          </select>
        </label>

        <div className="create-test-assertions">
          <h4>Assertions</h4>
          {assertions.map((assertion) => {
            const meta = ASSERTION_TYPES.find((type) => type.value === assertion.assertion_type);
            return (
              <div key={assertion.key} className="assertion-row" data-testid="assertion-row">
                <select
                  aria-label="Assertion type"
                  value={assertion.assertion_type}
                  onChange={(event) =>
                    updateAssertion(assertion.key, { assertion_type: event.target.value as AssertionType })
                  }
                >
                  {ASSERTION_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
                {meta?.needsTarget && (
                  <input
                    type="text"
                    aria-label="Target"
                    value={assertion.target}
                    onChange={(event) => updateAssertion(assertion.key, { target: event.target.value })}
                    placeholder="target"
                  />
                )}
                <input
                  type="text"
                  aria-label="Agent name"
                  value={assertion.agent_name}
                  onChange={(event) => updateAssertion(assertion.key, { agent_name: event.target.value })}
                  placeholder="agent name (optional)"
                />
                <label className="assertion-on-fail">
                  <input
                    type="checkbox"
                    checked={assertion.on_fail === "warn"}
                    onChange={(event) =>
                      updateAssertion(assertion.key, { on_fail: event.target.checked ? "warn" : "fail" })
                    }
                  />
                  Warn only
                </label>
                <button
                  type="button"
                  aria-label="Remove assertion"
                  onClick={() => removeAssertion(assertion.key)}
                >
                  Remove
                </button>
              </div>
            );
          })}
          <button type="button" onClick={() => setAssertions((current) => [...current, newDraft()])}>
            Add assertion
          </button>
        </div>

        {error !== null && <p className="panel-error">{error}</p>}

        <div className="modal-actions">
          <button type="button" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save Test"}
          </button>
        </div>
      </div>
    </div>
  );
}
