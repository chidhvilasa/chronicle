import { memo, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import type { ECharts } from "echarts";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import type { TrendPoint } from "../../types";
import { TREND_RANGE_DAYS, type TrendRange } from "./PeriodSelector";

interface LatencyTrendChartProps {
  range: TrendRange;
}

function sameSeries(a: TrendPoint[], b: TrendPoint[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function lastNDays(points: TrendPoint[], days: number): TrendPoint[] {
  return points.slice(Math.max(0, points.length - days));
}

/** Line chart: avg and p95 LLM call latency per day, sharing the period selector's range. */
export const LatencyTrendChart = memo(function LatencyTrendChart({ range }: LatencyTrendChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ECharts | null>(null);
  const [avgPoints, setAvgPoints] = useState<TrendPoint[]>([]);
  const [p95Points, setP95Points] = useState<TrendPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchTrends() {
      try {
        const [avg, p95] = await Promise.all([
          chronicleApi.getMetricsTrends("day", "latency", "avg"),
          chronicleApi.getMetricsTrends("day", "latency", "p95"),
        ]);
        if (cancelled) return;
        setAvgPoints((prev) => (sameSeries(prev, avg) ? prev : avg));
        setP95Points((prev) => (sameSeries(prev, p95) ? prev : p95));
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load latency trends.");
        }
      }
    }

    fetchTrends();
    return () => {
      cancelled = true;
    };
  }, [range]);

  const visibleAvg = useMemo(() => lastNDays(avgPoints, TREND_RANGE_DAYS[range]), [avgPoints, range]);
  const visibleP95 = useMemo(() => lastNDays(p95Points, TREND_RANGE_DAYS[range]), [p95Points, range]);

  const option = useMemo(
    () => ({
      tooltip: { trigger: "axis" as const },
      legend: { data: ["Avg latency", "P95 latency"] },
      grid: { left: 56, right: 24, top: 40, bottom: 32 },
      xAxis: { type: "category" as const, data: visibleAvg.map((p) => p.bucket) },
      yAxis: { type: "value" as const, name: "ms" },
      series: [
        { name: "Avg latency", type: "line" as const, data: visibleAvg.map((p) => p.value) },
        { name: "P95 latency", type: "line" as const, data: visibleP95.map((p) => p.value) },
      ],
    }),
    [visibleAvg, visibleP95]
  );

  useEffect(() => {
    if (containerRef.current === null) return;
    const chart = echarts.init(containerRef.current);
    chartRef.current = chart;
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return (
    <div className="perf-chart-wrapper">
      <h3 className="perf-chart-title">LLM Latency</h3>
      {error !== null && <p className="panel-error">{error}</p>}
      <div ref={containerRef} className="perf-chart" data-testid="latency-trend-chart" />
    </div>
  );
});
