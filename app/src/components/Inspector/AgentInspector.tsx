import type { Event } from "../../types";
import { summarizeAgent } from "./summarize";

interface AgentInspectorProps {
  agentName: string | null;
  events: Event[];
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Agent tab: aggregate stats for whichever agent's lane header was clicked in the timeline. */
export function AgentInspector({ agentName, events }: AgentInspectorProps) {
  if (agentName === null) {
    return (
      <p className="panel-empty">
        Click an agent's lane header in the timeline to see its summary.
      </p>
    );
  }

  const summary = summarizeAgent(events, agentName);

  return (
    <div data-testid="agent-inspector">
      <h2>{summary.agentName}</h2>
      <dl className="event-meta">
        <dt>LLM calls</dt>
        <dd>{summary.llmCallCount}</dd>
        <dt>Tool calls</dt>
        <dd>{summary.toolCallCount}</dd>
        <dt>Total tokens</dt>
        <dd>{summary.totalTokens.toLocaleString()}</dd>
        <dt>Errors</dt>
        <dd>{summary.errorCount}</dd>
        <dt>Avg. LLM latency</dt>
        <dd>{summary.averageLlmLatencyMs !== null ? formatMs(summary.averageLlmLatencyMs) : "—"}</dd>
      </dl>

      <h3>Tools used</h3>
      {summary.toolUsage.length === 0 ? (
        <p className="panel-empty">This agent didn't call any tools.</p>
      ) : (
        <ul className="tool-usage-list">
          {summary.toolUsage.map((usage) => (
            <li key={usage.toolName}>
              <span>{usage.toolName}</span>
              <span>{usage.callCount} calls</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
