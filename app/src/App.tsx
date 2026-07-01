import { useEffect, useState } from "react";
import { chronicleApi, ChronicleApiError } from "./api/client";
import { Sidebar } from "./components/Sidebar";
import { Timeline } from "./components/Timeline";
import { Inspector } from "./components/Inspector";
import type { ChronicleEvent, ChronicleRun } from "./types";
import "./App.css";

function App() {
  const [runs, setRuns] = useState<ChronicleRun[]>([]);
  const [events, setEvents] = useState<ChronicleEvent[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    chronicleApi
      .listRuns()
      .then(setRuns)
      .catch((err: unknown) => setErrorMessage(describeError(err)));
  }, []);

  useEffect(() => {
    if (selectedRunId === null) {
      setEvents([]);
      return;
    }
    chronicleApi
      .getRunTimeline(selectedRunId)
      .then(setEvents)
      .catch((err: unknown) => setErrorMessage(describeError(err)));
  }, [selectedRunId]);

  const selectedEvent = events.find((event) => event.id === selectedEventId) ?? null;

  return (
    <main className="app">
      <h1 className="app-title">Chronicle</h1>
      {errorMessage !== null && <p className="app-error">{errorMessage}</p>}
      <div className="app-body">
        <Sidebar runs={runs} selectedRunId={selectedRunId} onSelectRun={setSelectedRunId} />
        <Timeline
          events={events}
          selectedEventId={selectedEventId}
          onSelectEvent={setSelectedEventId}
        />
        <Inspector event={selectedEvent} />
      </div>
    </main>
  );
}

function describeError(err: unknown): string {
  if (err instanceof ChronicleApiError) {
    return err.message;
  }
  return "Something went wrong while talking to the Chronicle server.";
}

export default App;
