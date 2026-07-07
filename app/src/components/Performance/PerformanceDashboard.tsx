import { useState } from "react";
import { LatencyTrendChart } from "./LatencyTrendChart";
import { ModelsTable } from "./ModelsTable";
import { PeriodSelector, type TrendRange } from "./PeriodSelector";
import { RunCostScatterChart } from "./RunCostScatterChart";
import { StatCards } from "./StatCards";
import { TokenCostTrendChart } from "./TokenCostTrendChart";
import { ToolsTable } from "./ToolsTable";

/** Performance tab: overview stat cards, trend charts, and aggregate tables. */
export function PerformanceDashboard() {
  const [range, setRange] = useState<TrendRange>("30D");

  return (
    <div className="perf-dashboard" data-testid="perf-dashboard">
      <StatCards />

      <div className="perf-charts-section">
        <PeriodSelector value={range} onChange={setRange} />
        <div className="perf-charts-row">
          <TokenCostTrendChart range={range} />
          <LatencyTrendChart range={range} />
        </div>
      </div>

      <div className="perf-tables-section">
        <h3 className="perf-section-title">Top Tools</h3>
        <ToolsTable />

        <RunCostScatterChart />

        <h3 className="perf-section-title">Model Breakdown</h3>
        <ModelsTable />
      </div>
    </div>
  );
}
