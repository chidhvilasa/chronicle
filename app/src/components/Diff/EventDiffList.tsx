import type { EventDiffRow } from "./computeDiff";
import { promptOf } from "./computeDiff";
import { PromptDiff } from "./PromptDiff";

interface EventDiffListProps {
  rows: EventDiffRow[];
}

function MissingRow({ row }: { row: EventDiffRow }) {
  const present = row.eventA ?? row.eventB;
  const missingFrom = row.status === "missing_a" ? "Run A" : "Run B";
  return (
    <>
      <p className="diff-row-header">
        Step {row.index + 1}: {present?.event_type}
      </p>
      <p className="diff-missing-label">missing in {missingFrom}</p>
    </>
  );
}

function ComparedRow({ row }: { row: EventDiffRow }) {
  const isPromptComparable =
    row.eventA?.event_type === "llm_call" && row.eventB?.event_type === "llm_call";
  return (
    <>
      <p className="diff-row-header">
        Step {row.index + 1}: {row.eventA?.event_type}
      </p>
      <table className="diff-fields-table">
        <tbody>
          {row.fields.map((field) => (
            <tr key={field.label} className={field.differs ? "diff-field-different" : ""}>
              <th scope="row">{field.label}</th>
              <td>{field.a}</td>
              <td>{field.b}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {isPromptComparable && (
        <PromptDiff promptA={promptOf(row.eventA)} promptB={promptOf(row.eventB)} />
      )}
    </>
  );
}

/** Positional diff of two runs' events: same (no highlight), different (yellow), missing (red). */
export function EventDiffList({ rows }: EventDiffListProps) {
  if (rows.length === 0) {
    return <p className="panel-empty">Neither run has any events to compare.</p>;
  }

  return (
    <ol className="diff-event-list" data-testid="diff-event-list">
      {rows.map((row) => (
        <li key={row.index} className={`diff-row diff-row-${row.status}`}>
          {row.status === "same" || row.status === "different" ? (
            <ComparedRow row={row} />
          ) : (
            <MissingRow row={row} />
          )}
        </li>
      ))}
    </ol>
  );
}
