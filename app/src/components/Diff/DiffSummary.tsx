import type { RunStats } from "./computeDiff";

interface DiffSummaryProps {
  statsA: RunStats;
  statsB: RunStats;
}

function formatSeconds(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function formatSignedNumber(value: number, format: (n: number) => string): string {
  if (value === 0) return `±${format(0)}`;
  return value > 0 ? `+${format(value)}` : `-${format(Math.abs(value))}`;
}

/** Green when B improves on A (lower is better), red when B regresses, no color for a tie. */
function deltaClass(delta: number): string {
  if (delta === 0) return "";
  return delta < 0 ? "diff-delta-good" : "diff-delta-bad";
}

interface SummaryRowProps {
  label: string;
  a: string;
  b: string;
  delta: number;
  deltaLabel: string;
}

function SummaryRow({ label, a, b, delta, deltaLabel }: SummaryRowProps) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td>{a}</td>
      <td>{b}</td>
      <td className={deltaClass(delta)}>{deltaLabel}</td>
    </tr>
  );
}

/** Side-by-side run stats with the B-minus-A delta colored green (faster/cheaper/fewer) or red. */
export function DiffSummary({ statsA, statsB }: DiffSummaryProps) {
  const durationDelta = statsB.durationSeconds - statsA.durationSeconds;
  const tokensDelta = statsB.totalTokens - statsA.totalTokens;
  const costDelta = statsB.totalCostUsd - statsA.totalCostUsd;
  const errorDelta = statsB.errorCount - statsA.errorCount;
  const toolCallDelta = statsB.toolCallCount - statsA.toolCallCount;

  return (
    <table className="diff-summary-table" data-testid="diff-summary">
      <thead>
        <tr>
          <th scope="col"></th>
          <th scope="col">Run A</th>
          <th scope="col">Run B</th>
          <th scope="col">Δ (B − A)</th>
        </tr>
      </thead>
      <tbody>
        <SummaryRow
          label="Total duration"
          a={formatSeconds(statsA.durationSeconds)}
          b={formatSeconds(statsB.durationSeconds)}
          delta={durationDelta}
          deltaLabel={formatSignedNumber(durationDelta, (n) => `${n.toFixed(1)}s`)}
        />
        <SummaryRow
          label="Total tokens"
          a={statsA.totalTokens.toLocaleString()}
          b={statsB.totalTokens.toLocaleString()}
          delta={tokensDelta}
          deltaLabel={formatSignedNumber(tokensDelta, (n) => n.toLocaleString())}
        />
        <SummaryRow
          label="Total cost"
          a={`$${statsA.totalCostUsd.toFixed(4)}`}
          b={`$${statsB.totalCostUsd.toFixed(4)}`}
          delta={costDelta}
          deltaLabel={formatSignedNumber(costDelta, (n) => `$${n.toFixed(4)}`)}
        />
        <SummaryRow
          label="Error count"
          a={String(statsA.errorCount)}
          b={String(statsB.errorCount)}
          delta={errorDelta}
          deltaLabel={formatSignedNumber(errorDelta, (n) => String(n))}
        />
        <SummaryRow
          label="Total tool calls"
          a={String(statsA.toolCallCount)}
          b={String(statsB.toolCallCount)}
          delta={toolCallDelta}
          deltaLabel={formatSignedNumber(toolCallDelta, (n) => String(n))}
        />
      </tbody>
    </table>
  );
}
