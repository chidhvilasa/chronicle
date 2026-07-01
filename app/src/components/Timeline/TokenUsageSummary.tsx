import { COST_PER_INPUT_TOKEN_USD, COST_PER_OUTPUT_TOKEN_USD } from "../../config";
import type { TimelineLane } from "../../types";

interface TokenUsageSummaryProps {
  lanes: TimelineLane[];
}

function sumTokens(lanes: TimelineLane[]): { inputTokens: number; outputTokens: number } {
  let inputTokens = 0;
  let outputTokens = 0;
  for (const lane of lanes) {
    for (const segment of lane.segments) {
      if (segment.token_usage !== null) {
        inputTokens += segment.token_usage.input_tokens ?? 0;
        outputTokens += segment.token_usage.output_tokens ?? 0;
      }
    }
  }
  return { inputTokens, outputTokens };
}

/** Summary bar above the timeline: total input/output tokens and an estimated cost. */
export function TokenUsageSummary({ lanes }: TokenUsageSummaryProps) {
  const { inputTokens, outputTokens } = sumTokens(lanes);
  const estimatedCostUsd =
    inputTokens * COST_PER_INPUT_TOKEN_USD + outputTokens * COST_PER_OUTPUT_TOKEN_USD;

  return (
    <div className="token-usage-summary" data-testid="token-usage-summary">
      <span>
        Input tokens: <strong>{inputTokens.toLocaleString()}</strong>
      </span>
      <span>
        Output tokens: <strong>{outputTokens.toLocaleString()}</strong>
      </span>
      <span>
        Estimated cost: <strong>${estimatedCostUsd.toFixed(4)}</strong>
      </span>
    </div>
  );
}
