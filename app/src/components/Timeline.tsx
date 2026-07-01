import type { ChronicleEvent } from "../types";

interface TimelineProps {
  events: ChronicleEvent[];
  selectedEventId: string | null;
  onSelectEvent: (eventId: string) => void;
}

/** Main panel rendering a run's events in chronological order. */
export function Timeline({ events, selectedEventId, onSelectEvent }: TimelineProps) {
  if (events.length === 0) {
    return (
      <section className="timeline" data-testid="timeline">
        <p className="timeline-empty">Select a run to see its timeline.</p>
      </section>
    );
  }

  return (
    <section className="timeline" data-testid="timeline">
      <ol className="timeline-list">
        {events.map((event) => (
          <li key={event.id}>
            <button
              type="button"
              className={
                event.id === selectedEventId ? "timeline-item active" : "timeline-item"
              }
              onClick={() => onSelectEvent(event.id)}
            >
              <span className="event-type">{event.event_type}</span>
              <span className="event-timestamp">
                {new Date(event.timestamp * 1000).toLocaleTimeString()}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
