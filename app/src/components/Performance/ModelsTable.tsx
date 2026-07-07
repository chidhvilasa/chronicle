import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import type { ModelMetrics } from "../../types";
import { formatCostUsd, formatDurationMs } from "./format";

/** Per-model breakdown table; falls back to an upgrade notice if no model name was captured. */
export function ModelsTable() {
  const [models, setModels] = useState<ModelMetrics[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    chronicleApi
      .listMetricsModels()
      .then((fetched) => {
        if (!cancelled) setModels(fetched);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load model metrics.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error !== null) {
    return <p className="panel-error">{error}</p>;
  }

  const hasCapturedModelNames = models.some((model) => model.model_name !== "unknown");
  if (!hasCapturedModelNames) {
    return (
      <p className="panel-empty" data-testid="models-table-fallback">
        Model names not captured. Upgrade to chronicle-sdk 0.5.0 or higher to see per-model breakdown.
      </p>
    );
  }

  return (
    <table className="perf-table" data-testid="models-table">
      <thead>
        <tr>
          <th>Model</th>
          <th>Calls</th>
          <th>Avg Latency</th>
          <th>Input Tokens</th>
          <th>Output Tokens</th>
          <th>Estimated Cost</th>
        </tr>
      </thead>
      <tbody>
        {models.map((model) => (
          <tr key={model.model_name}>
            <td>{model.model_name}</td>
            <td>{model.call_count}</td>
            <td>{model.avg_latency_ms !== null ? formatDurationMs(model.avg_latency_ms) : "—"}</td>
            <td>{model.total_input_tokens}</td>
            <td>{model.total_output_tokens}</td>
            <td>{formatCostUsd(model.total_cost_usd)} (est.)</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
