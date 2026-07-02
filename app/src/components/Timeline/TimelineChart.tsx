import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import type {
  CustomSeriesRenderItemAPI,
  CustomSeriesRenderItemParams,
  CustomSeriesRenderItemReturn,
  DefaultLabelFormatterCallbackParams,
  ECharts,
} from "echarts";
import type { TimelineLane, TimelineSegment, TimelineSegmentType } from "../../types";

interface TimelineChartProps {
  lanes: TimelineLane[];
  zoom: number;
  onSegmentSelect?: (segment: TimelineSegment) => void;
  onAgentSelect?: (agentName: string) => void;
  /** event_ids that have a replayable snapshot; segments matching one show a "Replay from here" button on hover. */
  snapshotEventIds?: Set<string>;
  onReplayClick?: (segment: TimelineSegment) => void;
}

interface HoveredSegment {
  segment: TimelineSegment;
  x: number;
  y: number;
}

interface SegmentDatum {
  value: [number, number, number];
  segment: TimelineSegment;
  agentName: string;
  itemStyle: { color: string };
}

interface CartesianCoordSys {
  x: number;
  y: number;
  width: number;
  height: number;
}

const SEGMENT_COLORS: Record<TimelineSegmentType, string> = {
  llm_call: "#4285f4",
  tool_call: "#f59e0b",
  waiting: "rgba(156, 163, 175, 0.5)",
  error: "#ef4444",
  retry: "#eab308",
};

function buildSeriesData(lanes: TimelineLane[]): SegmentDatum[] {
  const data: SegmentDatum[] = [];
  lanes.forEach((lane, laneIndex) => {
    lane.segments.forEach((segment) => {
      data.push({
        value: [laneIndex, segment.start_time_ms, segment.start_time_ms + segment.duration_ms],
        segment,
        agentName: lane.agent_name,
        itemStyle: { color: SEGMENT_COLORS[segment.type] },
      });
    });
  });
  return data;
}

/** Draws one horizontal bar per data point; the canonical ECharts custom-series Gantt pattern. */
function renderItem(
  params: CustomSeriesRenderItemParams,
  api: CustomSeriesRenderItemAPI
): CustomSeriesRenderItemReturn {
  const laneIndex = api.value(0) as number;
  const start = api.coord([api.value(1), laneIndex]);
  const end = api.coord([api.value(2), laneIndex]);
  const laneSize = (api.size?.([0, 1]) ?? [0, 20]) as number[];
  const barHeight = Math.max(laneSize[1] * 0.6, 4);
  const coordSys = params.coordSys as unknown as CartesianCoordSys;

  const rectShape = echarts.graphic.clipRectByRect(
    {
      x: start[0],
      y: start[1] - barHeight / 2,
      width: Math.max(end[0] - start[0], 2),
      height: barHeight,
    },
    { x: coordSys.x, y: coordSys.y, width: coordSys.width, height: coordSys.height }
  );

  return (
    rectShape && {
      type: "rect",
      shape: rectShape,
      style: api.style(),
    }
  );
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => {
    switch (char) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      default:
        return "&#39;";
    }
  });
}

function formatTooltip(datum: SegmentDatum): string {
  const { segment, agentName } = datum;
  const lines = [
    `<strong>${escapeHtml(segment.type)}</strong>`,
    `Agent: ${escapeHtml(agentName)}`,
    `Duration: ${formatMs(segment.duration_ms)}`,
  ];
  if (segment.type === "tool_call" || segment.type === "llm_call") {
    lines.push(`${segment.type === "tool_call" ? "Tool" : "Model"}: ${escapeHtml(segment.label)}`);
  }
  if (segment.token_usage !== null) {
    lines.push(
      `Tokens: ${segment.token_usage.input_tokens ?? 0} in / ${segment.token_usage.output_tokens ?? 0} out`
    );
  }
  return lines.join("<br/>");
}

/** Horizontal swimlane timeline: one lane per agent, rendered via an ECharts custom series. */
export function TimelineChart({
  lanes,
  zoom,
  onSegmentSelect,
  onAgentSelect,
  snapshotEventIds,
  onReplayClick,
}: TimelineChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ECharts | null>(null);
  const onSegmentSelectRef = useRef(onSegmentSelect);
  onSegmentSelectRef.current = onSegmentSelect;
  const onAgentSelectRef = useRef(onAgentSelect);
  onAgentSelectRef.current = onAgentSelect;
  const snapshotEventIdsRef = useRef(snapshotEventIds);
  snapshotEventIdsRef.current = snapshotEventIds;
  const [hovered, setHovered] = useState<HoveredSegment | null>(null);
  const hideTimeoutRef = useRef<number | null>(null);

  function cancelHide() {
    if (hideTimeoutRef.current !== null) {
      window.clearTimeout(hideTimeoutRef.current);
      hideTimeoutRef.current = null;
    }
  }

  /** Delayed so the cursor can travel from the segment to the floating button without it vanishing. */
  function scheduleHide() {
    cancelHide();
    hideTimeoutRef.current = window.setTimeout(() => setHovered(null), 250);
  }

  useEffect(() => {
    if (containerRef.current === null) return;
    const chart = echarts.init(containerRef.current);
    chartRef.current = chart;

    chart.on("click", (params) => {
      if (params.componentType === "yAxis") {
        onAgentSelectRef.current?.(params.name);
        return;
      }
      const datum = params.data as SegmentDatum | undefined;
      if (datum) onSegmentSelectRef.current?.(datum.segment);
    });

    chart.on("mouseover", { seriesIndex: 0 }, (params) => {
      const datum = params.data as SegmentDatum | undefined;
      const eventId = datum?.segment.event_id ?? null;
      if (datum === undefined || eventId === null || !snapshotEventIdsRef.current?.has(eventId)) {
        return;
      }
      cancelHide();
      const zrEvent = (params as unknown as { event?: { offsetX: number; offsetY: number } }).event;
      setHovered({ segment: datum.segment, x: zrEvent?.offsetX ?? 0, y: zrEvent?.offsetY ?? 0 });
    });

    chart.on("mouseout", { seriesIndex: 0 }, () => scheduleHide());

    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (chart === null) return;

    chart.setOption(
      {
        tooltip: {
          formatter: (params: DefaultLabelFormatterCallbackParams | DefaultLabelFormatterCallbackParams[]) => {
            const single = Array.isArray(params) ? params[0] : params;
            const datum = single?.data as SegmentDatum | undefined;
            return datum ? formatTooltip(datum) : "";
          },
        },
        grid: { left: 120, right: 24, top: 16, bottom: 32 },
        xAxis: { type: "value", name: "ms from run start" },
        yAxis: {
          type: "category",
          data: lanes.map((lane) => lane.agent_name),
          inverse: true,
          triggerEvent: true,
        },
        dataZoom: [{ type: "inside", xAxisIndex: 0, filterMode: "none" }],
        series: [
          {
            type: "custom",
            renderItem,
            encode: { x: [1, 2], y: 0 },
            data: buildSeriesData(lanes),
          },
        ],
      },
      true
    );
  }, [lanes]);

  useEffect(() => {
    const chart = chartRef.current;
    if (chart === null) return;
    const span = 50 / zoom;
    chart.dispatchAction({
      type: "dataZoom",
      start: Math.max(0, 50 - span),
      end: Math.min(100, 50 + span),
    });
  }, [zoom]);

  return (
    <div className="timeline-chart-wrapper">
      <div ref={containerRef} className="timeline-chart" data-testid="timeline-chart" />
      {hovered !== null && (
        <button
          type="button"
          className="timeline-replay-button"
          style={{ left: hovered.x, top: Math.max(hovered.y - 32, 0) }}
          data-testid="replay-from-here-button"
          onMouseDown={(event) => event.preventDefault()}
          onMouseEnter={cancelHide}
          onMouseLeave={scheduleHide}
          onClick={() => onReplayClick?.(hovered.segment)}
        >
          Replay from here
        </button>
      )}
    </div>
  );
}
