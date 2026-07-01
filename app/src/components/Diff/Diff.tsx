import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { useAppStore } from "../../store/useAppStore";
import type { Event } from "../../types";
import { buildEventDiffRows, computeRunStats } from "./computeDiff";
import { DiffSummary } from "./DiffSummary";
import { EventDiffList } from "./EventDiffList";
import { RunSelector } from "./RunSelector";

/** Runs with more events than this on either side still render, but show a warning first. */
const LARGE_RUN_EVENT_THRESHOLD = 500;

/** Diff tab: pick two runs and compare their duration/tokens/cost/errors/tool calls and events. */
export function Diff() {
  const runs = useAppStore((state) => state.runs);
  const [runAId, setRunAId] = useState<string | null>(null);
  const [runBId, setRunBId] = useState<string | null>(null);
  const [eventsA, setEventsA] = useState<Event[]>([]);
  const [eventsB, setEventsB] = useState<Event[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (runAId === null || runBId === null) {
      setEventsA([]);
      setEventsB([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([chronicleApi.listRunEvents(runAId), chronicleApi.listRunEvents(runBId)])
      .then(([resultA, resultB]) => {
        if (!cancelled) {
          setEventsA(resultA);
          setEventsB(resultB);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load runs to diff.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runAId, runBId]);

  const runA = runs.find((run) => run.run_id === runAId) ?? null;
  const runB = runs.find((run) => run.run_id === runBId) ?? null;
  const isLargeDiff =
    eventsA.length > LARGE_RUN_EVENT_THRESHOLD || eventsB.length > LARGE_RUN_EVENT_THRESHOLD;

  return (
    <div className="diff-root" data-testid="diff-root">
      <RunSelector
        runs={runs}
        runAId={runAId}
        runBId={runBId}
        onSelectRunA={setRunAId}
        onSelectRunB={setRunBId}
      />

      {loading && <p className="panel-empty">Loading runs to diff…</p>}
      {error !== null && <p className="panel-error">{error}</p>}

      {!loading && error === null && (runA === null || runB === null) && (
        <p className="panel-empty">Select two runs to compare.</p>
      )}

      {!loading && error === null && runA !== null && runB !== null && (
        <>
          {isLargeDiff && (
            <p className="diff-warning" data-testid="diff-large-warning">
              One of these runs has more than {LARGE_RUN_EVENT_THRESHOLD} events — the diff below
              may take a moment to scroll through.
            </p>
          )}
          <DiffSummary statsA={computeRunStats(runA, eventsA)} statsB={computeRunStats(runB, eventsB)} />
          <EventDiffList rows={buildEventDiffRows(eventsA, eventsB)} />
        </>
      )}
    </div>
  );
}
