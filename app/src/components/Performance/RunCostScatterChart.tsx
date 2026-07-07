import { memo, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import type { ECharts } from "echarts";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { useAppStore } from "../../store/useAppStore";
import type { RunMetrics } from "../../types";
import { formatCostUsd, formatDurationMs } from "./format";

interface ScatterDatum {
  value: [number, number];
  run: RunMetrics;
}

const MIN_SYMBOL_SIZE = 8;
const MAX_SYMBOL_SIZE = 40;

function sameRuns(a: RunMetrics[], b: RunMetrics[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function symbolSizeFor(totalTokens: number, maxTokens: number): number {
  if (maxTokens <= 0) return MIN_SYMBOL_SIZE;
  const ratio = Math.min(1, totalTokens / maxTokens);
  return MIN_SYMBOL_SIZE + ratio * (MAX_SYMBOL_SIZE - MIN_SYMBOL_SIZE);
}

/** Scatter plot: one point per run, duration vs. estimated cost, sized by tokens, colored by errors. */
export const RunCostScatterChart = memo(function RunCostScatterChart() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ECharts | null>(null);
  const [runs, setRuns] = useState<RunMetrics[]>([]);
  const [error, setError] = useState<string | null>(null);
  const selectRun = useAppStore((state) => state.selectRun);

  useEffect(() => {
    let cancelled = false;
    chronicleApi
      .listMetricsRuns({ limit: 200 })
      .then((fetched) => {
        if (!cancelled) setRuns((prev) => (sameRuns(prev, fetched) ? prev : fetched));
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load run cost data.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const data = useMemo<ScatterDatum[]>(
    () => runs.map((run) => ({ value: [run.total_duration_ms, run.estimated_cost_usd], run })),
    [runs]
  );
  const maxTokens = useMemo(() => Math.max(0, ...runs.map((run) => run.total_tokens)), [runs]);

  const option = useMemo(
    () => ({
      tooltip: {
        formatter: (params: unknown) => {
          const datum = (params as { data?: ScatterDatum }).data;
          if (!datum) return "";
          const { run } = datum;
          return [
            `<strong>${run.run_id}</strong>`,
            `Duration: ${formatDurationMs(run.total_duration_ms)}`,
            `Cost: ${formatCostUsd(run.estimated_cost_usd)} (est.)`,
            `Tokens: ${run.total_tokens}`,
            `Errors: ${run.error_count}`,
          ].join("<br/>");
        },
      },
      grid: { left: 64, right: 24, top: 24, bottom: 48 },
      xAxis: { type: "value" as const, name: "duration (ms)" },
      yAxis: { type: "value" as const, name: "cost (est. USD)" },
      series: [
        {
          type: "scatter" as const,
          data,
          symbolSize: (_value: number[], params: { data?: ScatterDatum }) =>
            symbolSizeFor(params.data?.run.total_tokens ?? 0, maxTokens),
          itemStyle: {
            color: (params: { data?: ScatterDatum }) =>
              (params.data?.run.error_count ?? 0) > 0 ? "#ef4444" : "#2e9e4f",
          },
        },
      ],
    }),
    [data, maxTokens]
  );

  useEffect(() => {
    if (containerRef.current === null) return;
    const chart = echarts.init(containerRef.current);
    chartRef.current = chart;
    chart.on("click", (params) => {
      const datum = (params.data as ScatterDatum | undefined)?.run;
      if (datum) selectRun(datum.run_id);
    });
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return (
    <div className="perf-chart-wrapper">
      <h3 className="perf-chart-title">Run Cost vs. Duration</h3>
      {error !== null && <p className="panel-error">{error}</p>}
      <div ref={containerRef} className="perf-chart" data-testid="run-cost-scatter-chart" />
    </div>
  );
});
