// This file exports a non-component constant (TREND_RANGE_DAYS) alongside the
// PeriodSelector component, so Vite/React Fast Refresh can only full-reload (not
// hot-patch) this file in dev - a DX-only tradeoff, not a runtime issue.
/* eslint-disable react-refresh/only-export-components */
export type TrendRange = "7D" | "30D" | "90D";

export const TREND_RANGE_DAYS: Record<TrendRange, number> = { "7D": 7, "30D": 30, "90D": 90 };

interface PeriodSelectorProps {
  value: TrendRange;
  onChange: (range: TrendRange) => void;
}

/** 7D/30D/90D range buttons shared by the token/cost and latency trend charts. */
export function PeriodSelector({ value, onChange }: PeriodSelectorProps) {
  return (
    <div className="perf-period-selector" data-testid="perf-period-selector">
      {(Object.keys(TREND_RANGE_DAYS) as TrendRange[]).map((range) => (
        <button
          key={range}
          type="button"
          className={range === value ? "perf-period-button active" : "perf-period-button"}
          onClick={() => onChange(range)}
        >
          {range}
        </button>
      ))}
    </div>
  );
}
