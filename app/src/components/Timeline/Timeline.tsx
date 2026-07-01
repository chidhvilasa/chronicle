import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { TIMELINE_MAX_ZOOM, TIMELINE_ZOOM_STEP } from "../../config";
import type { Timeline as TimelineData, TimelineLane, TimelineSegment } from "../../types";
import { TimelineChart } from "./TimelineChart";
import { TimelineControls, type SegmentFilter } from "./TimelineControls";
import { TokenUsageSummary } from "./TokenUsageSummary";

interface TimelineProps {
  runId: string | null;
  onSegmentSelect?: (segment: TimelineSegment) => void;
  onAgentSelect?: (agentName: string) => void;
}

const SKELETON_LANE_COUNT = 3;

const FILTER_TYPES: Record<Exclude<SegmentFilter, "all">, TimelineSegment["type"][]> = {
  llm: ["llm_call"],
  tools: ["tool_call"],
  errors: ["error"],
};

function applyFilter(lanes: TimelineLane[], filter: SegmentFilter): TimelineLane[] {
  if (filter === "all") return lanes;
  const allowed = new Set(FILTER_TYPES[filter]);
  return lanes.map((lane) => ({
    ...lane,
    segments: lane.segments.filter((segment) => allowed.has(segment.type)),
  }));
}

function hasAnySegments(lanes: TimelineLane[]): boolean {
  return lanes.some((lane) => lane.segments.length > 0);
}

/** Fetches a run's timeline and renders the token summary, controls, and swimlane chart. */
export function Timeline({ runId, onSegmentSelect, onAgentSelect }: TimelineProps) {
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<SegmentFilter>("all");
  const [zoom, setZoom] = useState(1);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    if (runId === null) {
      setTimeline(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    chronicleApi
      .getRunTimeline(runId)
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
  }, [runId, refreshToken]);

  useEffect(() => {
    setZoom(1);
    setFilter("all");
  }, [runId]);

  if (runId === null) {
    return <p className="panel-empty">Select a run to see its timeline.</p>;
  }

  if (loading) {
    return (
      <div className="timeline-skeleton" data-testid="timeline-skeleton">
        {Array.from({ length: SKELETON_LANE_COUNT }, (_, index) => (
          <div key={index} className="timeline-skeleton-lane" />
        ))}
      </div>
    );
  }

  if (error !== null) {
    return (
      <div className="panel-error-block">
        <p className="panel-error">{error}</p>
        <button type="button" onClick={() => setRefreshToken((n) => n + 1)}>
          Retry
        </button>
      </div>
    );
  }

  if (timeline === null || !hasAnySegments(timeline.lanes)) {
    return <p className="panel-empty">No events recorded for this run.</p>;
  }

  return (
    <div className="timeline-root" data-testid="timeline-root">
      <TokenUsageSummary lanes={timeline.lanes} />
      <TimelineControls
        filter={filter}
        onFilterChange={setFilter}
        onZoomIn={() => setZoom((z) => Math.min(z * TIMELINE_ZOOM_STEP, TIMELINE_MAX_ZOOM))}
        onZoomOut={() => setZoom((z) => Math.max(z / TIMELINE_ZOOM_STEP, 1))}
        onFitToScreen={() => setZoom(1)}
      />
      <TimelineChart
        lanes={applyFilter(timeline.lanes, filter)}
        zoom={zoom}
        onSegmentSelect={onSegmentSelect}
        onAgentSelect={onAgentSelect}
      />
    </div>
  );
}
