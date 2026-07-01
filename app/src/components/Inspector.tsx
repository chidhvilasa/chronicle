import type { ChronicleEvent } from "../types";

interface InspectorProps {
  event: ChronicleEvent | null;
}

/** Right-hand panel showing the full payload of the selected event. */
export function Inspector({ event }: InspectorProps) {
  if (event === null) {
    return (
      <aside className="inspector" data-testid="inspector">
        <p className="inspector-empty">Select an event to inspect its payload.</p>
      </aside>
    );
  }

  return (
    <aside className="inspector" data-testid="inspector">
      <h2>{event.event_type}</h2>
      <dl>
        <dt>Event ID</dt>
        <dd>{event.id}</dd>
        <dt>Run ID</dt>
        <dd>{event.run_id}</dd>
      </dl>
      <pre>{JSON.stringify(event.payload, null, 2)}</pre>
    </aside>
  );
}
