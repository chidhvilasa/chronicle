import { memo, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import type { ECharts } from "echarts";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import type { TrendPoint } from "../../types";
import { TREND_RANGE_DAYS, type TrendRange } from "./PeriodSelector";

interface TokenCostTrendChartProps {
  range: TrendRange;
}

function sameSeries(a: TrendPoint[], b: TrendPoint[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function lastNDays(points: TrendPoint[], days: number): TrendPoint[] {
  return points.slice(Math.max(0, points.length - days));
}

/** Line chart: tokens/day (left axis) and estimated cost/day (right axis, dashed). */
export const TokenCostTrendChart = memo(function TokenCostTrendChart({
  range,
}: TokenCostTrendChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ECharts | null>(null);
  const [tokenPoints, setTokenPoints] = useState<TrendPoint[]>([]);
  const [costPoints, setCostPoints] = useState<TrendPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchTrends() {
      try {
        const [tokens, cost] = await Promise.all([
          chronicleApi.getMetricsTrends("day", "tokens"),
          chronicleApi.getMetricsTrends("day", "cost"),
        ]);
        if (cancelled) return;
        setTokenPoints((prev) => (sameSeries(prev, tokens) ? prev : tokens));
        setCostPoints((prev) => (sameSeries(prev, cost) ? prev : cost));
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load token/cost trends.");
        }
      }
    }

    fetchTrends();
    return () => {
      cancelled = true;
    };
  }, [range]);

  const visibleTokens = useMemo(() => lastNDays(tokenPoints, TREND_RANGE_DAYS[range]), [tokenPoints, range]);
  const visibleCost = useMemo(() => lastNDays(costPoints, TREND_RANGE_DAYS[range]), [costPoints, range]);

  const option = useMemo(
    () => ({
      tooltip: { trigger: "axis" as const },
      legend: { data: ["Tokens", "Cost (est.)"] },
      grid: { left: 56, right: 56, top: 40, bottom: 32 },
      xAxis: { type: "category" as const, data: visibleTokens.map((p) => p.bucket) },
      yAxis: [
        { type: "value" as const, name: "tokens" },
        { type: "value" as const, name: "USD" },
      ],
      series: [
        {
          name: "Tokens",
          type: "line" as const,
          data: visibleTokens.map((p) => p.value),
          yAxisIndex: 0,
        },
        {
          name: "Cost (est.)",
          type: "line" as const,
          data: visibleCost.map((p) => p.value),
          yAxisIndex: 1,
          lineStyle: { type: "dashed" as const },
        },
      ],
    }),
    [visibleTokens, visibleCost]
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
      <h3 className="perf-chart-title">Tokens &amp; Cost</h3>
      {error !== null && <p className="panel-error">{error}</p>}
      <div ref={containerRef} className="perf-chart" data-testid="token-cost-trend-chart" />
    </div>
  );
});
