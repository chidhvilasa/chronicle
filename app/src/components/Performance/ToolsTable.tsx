import { useEffect, useMemo, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { useAppStore } from "../../store/useAppStore";
import type { ToolMetrics } from "../../types";
import { formatDurationMs, formatPercent } from "./format";

type SortKey = keyof Pick<
  ToolMetrics,
  "tool_name" | "call_count" | "avg_latency_ms" | "p95_latency_ms" | "error_rate" | "total_tokens"
>;

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "tool_name", label: "Tool Name" },
  { key: "call_count", label: "Call Count" },
  { key: "avg_latency_ms", label: "Avg Latency" },
  { key: "p95_latency_ms", label: "P95 Latency" },
  { key: "error_rate", label: "Error Rate" },
  { key: "total_tokens", label: "Total Tokens" },
];

function compareValues(a: ToolMetrics, b: ToolMetrics, key: SortKey): number {
  const left = a[key];
  const right = b[key];
  if (left === null) return right === null ? 0 : 1;
  if (right === null) return -1;
  if (typeof left === "string" || typeof right === "string") {
    return String(left).localeCompare(String(right));
  }
  return left - right;
}

/** Top tools table: sortable client-side, clicking a tool name filters the run list sidebar. */
export function ToolsTable() {
  const [tools, setTools] = useState<ToolMetrics[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("call_count");
  const [sortDescending, setSortDescending] = useState(true);
  const setToolNameFilter = useAppStore((state) => state.setToolNameFilter);
  const toolNameFilter = useAppStore((state) => state.toolNameFilter);

  useEffect(() => {
    let cancelled = false;
    chronicleApi
      .listMetricsTools()
      .then((fetched) => {
        if (!cancelled) setTools(fetched);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load tool metrics.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const sortedTools = useMemo(() => {
    const copy = [...tools];
    copy.sort((a, b) => {
      const comparison = compareValues(a, b, sortKey);
      return sortDescending ? -comparison : comparison;
    });
    return copy;
  }, [tools, sortKey, sortDescending]);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDescending((prev) => !prev);
    } else {
      setSortKey(key);
      setSortDescending(true);
    }
  }

  if (error !== null) {
    return <p className="panel-error">{error}</p>;
  }

  if (tools.length === 0) {
    return <p className="panel-empty">No tool calls recorded yet.</p>;
  }

  return (
    <table className="perf-table" data-testid="tools-table">
      <thead>
        <tr>
          {COLUMNS.map((column) => (
            <th key={column.key} onClick={() => handleSort(column.key)} className="perf-table-sortable">
              {column.label}
              {sortKey === column.key ? (sortDescending ? " ▼" : " ▲") : ""}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sortedTools.map((tool) => (
          <tr key={tool.tool_name}>
            <td>
              <button
                type="button"
                className={tool.tool_name === toolNameFilter ? "perf-tool-link active" : "perf-tool-link"}
                onClick={() =>
                  setToolNameFilter(tool.tool_name === toolNameFilter ? null : tool.tool_name)
                }
              >
                {tool.tool_name}
              </button>
            </td>
            <td>{tool.call_count}</td>
            <td>{tool.avg_latency_ms !== null ? formatDurationMs(tool.avg_latency_ms) : "—"}</td>
            <td>{tool.p95_latency_ms !== null ? formatDurationMs(tool.p95_latency_ms) : "—"}</td>
            <td className={tool.error_rate > 0.05 ? "perf-error-rate-high" : undefined}>
              {formatPercent(tool.error_rate)}
            </td>
            <td>{tool.total_tokens}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
