import type { Event } from "../../types";
import { summarizeTools } from "./summarize";

interface ToolInspectorProps {
  events: Event[];
  selectedToolName: string | null;
  onSelectTool: (toolName: string | null) => void;
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function summarizeJson(value: unknown): string {
  const text = JSON.stringify(value ?? {});
  return text.length > 60 ? `${text.slice(0, 60)}…` : text;
}

/** Tools tab: table of every tool used in the run, with an expandable per-call list. */
export function ToolInspector({ events, selectedToolName, onSelectTool }: ToolInspectorProps) {
  const tools = summarizeTools(events);
  const selected = tools.find((tool) => tool.toolName === selectedToolName) ?? null;

  if (tools.length === 0) {
    return <p className="panel-empty">No tool calls recorded for this run.</p>;
  }

  return (
    <div data-testid="tool-inspector">
      <table className="tool-table">
        <thead>
          <tr>
            <th>Tool</th>
            <th>Calls</th>
            <th>Success rate</th>
            <th>Avg. latency</th>
            <th>Tokens</th>
          </tr>
        </thead>
        <tbody>
          {tools.map((tool) => (
            <tr
              key={tool.toolName}
              className={tool.toolName === selectedToolName ? "tool-row active" : "tool-row"}
              onClick={() => onSelectTool(tool.toolName === selectedToolName ? null : tool.toolName)}
            >
              <td>{tool.toolName}</td>
              <td>{tool.callCount}</td>
              <td>{Math.round(tool.successRate * 100)}%</td>
              <td>{tool.averageLatencyMs !== null ? formatMs(tool.averageLatencyMs) : "—"}</td>
              <td>{tool.totalTokens.toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {selected !== null && (
        <div className="tool-call-list" data-testid="tool-call-list">
          <h3>Calls to {selected.toolName}</h3>
          <ul>
            {selected.calls.map((call) => (
              <li key={call.event_id} className={call.error === null ? "" : "tool-call-failed"}>
                <span>{new Date(call.timestamp * 1000).toLocaleTimeString()}</span>
                <span>{summarizeJson(call.data["arguments"] ?? call.data["args"])}</span>
                <span>{summarizeJson(call.data["result"] ?? call.data["response"])}</span>
                <span>{call.duration_ms !== null ? formatMs(call.duration_ms) : "—"}</span>
                <span>{call.error === null ? "success" : "error"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
