import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { METRICS_POLL_INTERVAL_MS } from "../../config";
import type { MetricsOverview } from "../../types";
import { formatCostUsd, formatDurationMs, formatTokenCount } from "./format";

type WeeklyTrend = "up" | "down" | "flat";

function computeWeeklyTrend(lastWeekCount: number, priorWeekCount: number): WeeklyTrend {
  if (lastWeekCount > priorWeekCount) return "up";
  if (lastWeekCount < priorWeekCount) return "down";
  return "flat";
}

const TREND_SYMBOL: Record<WeeklyTrend, string> = { up: "▲", down: "▼", flat: "—" };

/** Fetches the previous-week run count by splitting a 14-day `GET /metrics/runs` window in two. */
async function fetchWeeklyTrend(runsLast7Days: number): Promise<WeeklyTrend> {
  const fourteenDaysAgo = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString();
  const rows = await chronicleApi.listMetricsRuns({ fromDate: fourteenDaysAgo, limit: 1000 });
  const sevenDaysAgoMs = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const priorWeekCount = rows.filter((row) => row.created_at * 1000 < sevenDaysAgoMs).length;
  return computeWeeklyTrend(runsLast7Days, priorWeekCount);
}

function sameOverview(a: MetricsOverview | null, b: MetricsOverview): boolean {
  return a !== null && JSON.stringify(a) === JSON.stringify(b);
}

function StatCard({
  label,
  value,
  sublabel,
  isError,
}: {
  label: string;
  value: string;
  sublabel?: string;
  isError?: boolean;
}) {
  return (
    <div className="perf-stat-card" data-testid="perf-stat-card">
      <span className="perf-stat-label">{label}</span>
      <span className={isError ? "perf-stat-value perf-stat-value-error" : "perf-stat-value"}>{value}</span>
      {sublabel !== undefined && <span className="perf-stat-sublabel">{sublabel}</span>}
    </div>
  );
}

function StatCardsSkeleton() {
  return (
    <div className="perf-stat-cards" data-testid="perf-stat-cards-skeleton">
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className="perf-stat-card perf-stat-card-skeleton" />
      ))}
    </div>
  );
}

/** Overview stat cards row: fetches `GET /metrics/overview` on mount and every 30s. */
export function StatCards() {
  const [overview, setOverview] = useState<MetricsOverview | null>(null);
  const [weeklyTrend, setWeeklyTrend] = useState<WeeklyTrend>("flat");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchOverview() {
      setLoading(true);
      try {
        const fetched = await chronicleApi.getMetricsOverview();
        if (cancelled) return;
        setOverview((prev) => (sameOverview(prev, fetched) ? prev : fetched));
        setError(null);
        try {
          const trend = await fetchWeeklyTrend(fetched.runs_last_7_days);
          if (!cancelled) setWeeklyTrend(trend);
        } catch {
          // Weekly trend is a nice-to-have; a failure here shouldn't blank the cards.
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load metrics.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchOverview();
    const interval = setInterval(fetchOverview, METRICS_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (overview === null && loading) {
    return <StatCardsSkeleton />;
  }

  if (overview === null && error !== null) {
    return (
      <div className="perf-stat-cards-error">
        <p className="panel-error">{error}</p>
        <button
          type="button"
          onClick={() => {
            setError(null);
            setLoading(true);
            chronicleApi
              .getMetricsOverview()
              .then((fetched) => {
                setOverview(fetched);
                setError(null);
              })
              .catch((err) =>
                setError(err instanceof ChronicleApiError ? err.message : "Could not load metrics.")
              )
              .finally(() => setLoading(false));
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (overview === null) {
    return <StatCardsSkeleton />;
  }

  return (
    <div className="perf-stat-cards" data-testid="perf-stat-cards">
      <StatCard label="Total Runs" value={String(overview.total_runs)} />
      <StatCard label="Total Tokens" value={formatTokenCount(overview.total_tokens)} />
      <StatCard
        label="Total Cost"
        value={formatCostUsd(overview.total_cost_usd)}
        sublabel="est."
      />
      <StatCard label="Avg Run Duration" value={formatDurationMs(overview.avg_run_duration_ms)} />
      <StatCard
        label="Total Errors"
        value={String(overview.total_errors)}
        isError={overview.total_errors > 0}
      />
      <StatCard
        label="Runs This Week"
        value={String(overview.runs_last_7_days)}
        sublabel={TREND_SYMBOL[weeklyTrend]}
      />
    </div>
  );
}
