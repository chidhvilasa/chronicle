import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "../../api/client";
import { useAppStore } from "../../store/useAppStore";
import type { Event } from "../../types";

/** Main-panel "Inspector" tab: flat chronological list of a run's raw events. */
export function InspectorPanel() {
  const selectedRunId = useAppStore((state) => state.selectedRunId);
  const selectedDetail = useAppStore((state) => state.selectedDetail);
  const setSelectedDetail = useAppStore((state) => state.setSelectedDetail);
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (selectedRunId === null) {
      setEvents([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    chronicleApi
      .listRunEvents(selectedRunId)
      .then((result) => {
        if (!cancelled) setEvents(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ChronicleApiError ? err.message : "Could not load events.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  if (selectedRunId === null) {
    return <p className="panel-empty">Select a run to inspect its events.</p>;
  }
  if (loading) {
    return <p className="panel-empty">Loading events…</p>;
  }
  if (error !== null) {
    return <p className="panel-error">{error}</p>;
  }
  if (events.length === 0) {
    return <p className="panel-empty">This run has no events yet.</p>;
  }

  return (
    <ul className="event-list" data-testid="inspector-panel">
      {events.map((event) => (
        <li key={event.event_id}>
          <button
            type="button"
            className={selectedDetail === event ? "event-row active" : "event-row"}
            onClick={() => setSelectedDetail(event)}
          >
            <span className="event-type">{event.event_type}</span>
            <span className="event-agent">{event.agent_name ?? "unknown"}</span>
            <span className="event-timestamp">
              {new Date(event.timestamp * 1000).toLocaleTimeString()}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
