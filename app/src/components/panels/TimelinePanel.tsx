import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { useAppStore } from "../../store/useAppStore";
import type { Timeline } from "../../types";

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Main-panel "Timeline" tab: per-agent lanes of llm_call/tool_call/waiting/error segments. */
export function TimelinePanel() {
  const selectedRunId = useAppStore((state) => state.selectedRunId);
  const selectedDetail = useAppStore((state) => state.selectedDetail);
  const setSelectedDetail = useAppStore((state) => state.setSelectedDetail);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (selectedRunId === null) {
      setTimeline(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    chronicleApi
      .getRunTimeline(selectedRunId)
      .then((result) => {
        if (!cancelled) setTimeline(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load the timeline.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  if (selectedRunId === null) {
    return <p className="panel-empty">Select a run to see its timeline.</p>;
  }
  if (loading) {
    return <p className="panel-empty">Loading timeline…</p>;
  }
  if (error !== null) {
    return <p className="panel-error">{error}</p>;
  }
  if (timeline === null || timeline.lanes.length === 0) {
    return <p className="panel-empty">This run has no events yet.</p>;
  }

  return (
    <div className="timeline-panel" data-testid="timeline-panel">
      {timeline.lanes.map((lane) => (
        <div key={lane.agent_name} className="timeline-lane">
          <div className="timeline-lane-label">{lane.agent_name}</div>
          <div className="timeline-lane-segments">
            {lane.segments.map((segment, index) => (
              <button
                key={`${lane.agent_name}-${index}`}
                type="button"
                className={
                  selectedDetail === segment
                    ? `timeline-segment segment-${segment.type} active`
                    : `timeline-segment segment-${segment.type}`
                }
                onClick={() => setSelectedDetail(segment)}
                title={`${segment.label} (${formatMs(segment.duration_ms)})`}
              >
                {segment.label}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
