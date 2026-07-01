import type { DetailItem, Event, TimelineSegment } from "../../types";
import { isEventDetail } from "../../types";

interface EventInspectorProps {
  detail: DetailItem | null;
  events: Event[];
}

/** Resolves a selected segment to its full `Event` (segments only carry a summary + `event_id`). */
function resolveEvent(segment: TimelineSegment, events: Event[]): Event | null {
  if (segment.event_id === null) return null;
  return events.find((event) => event.event_id === segment.event_id) ?? null;
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function textField(data: Record<string, unknown>, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = data[key];
    if (typeof value === "string") return value;
  }
  return null;
}

function jsonField(data: Record<string, unknown>, ...keys: string[]): unknown {
  for (const key of keys) {
    if (key in data) return data[key];
  }
  return undefined;
}

function EventHeader({ event }: { event: Event }) {
  return (
    <>
      <span className={`event-type-badge type-${event.event_type}`}>{event.event_type}</span>
      <dl className="event-meta">
        <dt>Agent</dt>
        <dd>{event.agent_name ?? "unknown"}</dd>
        <dt>Timestamp</dt>
        <dd>{new Date(event.timestamp * 1000).toLocaleString()}</dd>
        <dt>Duration</dt>
        <dd>{event.duration_ms !== null ? formatMs(event.duration_ms) : "—"}</dd>
        <dt>Tokens</dt>
        <dd>
          {event.input_tokens ?? 0} in / {event.output_tokens ?? 0} out
        </dd>
      </dl>
    </>
  );
}

function LlmCallDetail({ event }: { event: Event }) {
  const prompt = textField(event.data, "prompt");
  const completion = textField(event.data, "completion", "response");
  return (
    <>
      <h3>Prompt</h3>
      <pre className="code-block" data-testid="llm-prompt">
        {prompt ?? "(no prompt recorded)"}
      </pre>
      <h3>Response</h3>
      <pre className="code-block" data-testid="llm-response">
        {completion ?? "(no response recorded)"}
      </pre>
    </>
  );
}

function ToolCallDetail({ event }: { event: Event }) {
  const args = jsonField(event.data, "arguments", "args");
  const result = jsonField(event.data, "result", "response");
  const succeeded = event.error === null;
  return (
    <>
      <dl className="event-meta">
        <dt>Tool</dt>
        <dd>{textField(event.data, "tool_name") ?? "unknown"}</dd>
        <dt>Status</dt>
        <dd className={succeeded ? "status-success" : "status-failed"}>
          {succeeded ? "success" : "error"}
        </dd>
      </dl>
      <h3>Arguments</h3>
      <pre className="code-block">{JSON.stringify(args ?? {}, null, 2)}</pre>
      <h3>Result</h3>
      <pre className="code-block">{JSON.stringify(result ?? {}, null, 2)}</pre>
    </>
  );
}

function ErrorDetail({ event }: { event: Event }) {
  const traceback = textField(event.data, "traceback", "stack_trace", "stack");
  return (
    <>
      <h3>Message</h3>
      <p className="detail-error">{event.error ?? "(no error message recorded)"}</p>
      <h3>Agent</h3>
      <p>{event.agent_name ?? "unknown"}</p>
      {traceback !== null && (
        <>
          <h3>Stack trace</h3>
          <pre className="code-block">{traceback}</pre>
        </>
      )}
    </>
  );
}

function FullEventDetail({ event }: { event: Event }) {
  return (
    <>
      <EventHeader event={event} />
      {event.event_type === "llm_call" && <LlmCallDetail event={event} />}
      {event.event_type === "tool_call" && <ToolCallDetail event={event} />}
      {event.event_type === "error" && <ErrorDetail event={event} />}
      {event.event_type !== "llm_call" && event.event_type !== "tool_call" && event.event_type !== "error" && (
        <pre className="code-block">{JSON.stringify(event.data, null, 2)}</pre>
      )}
    </>
  );
}

function SegmentOnlyDetail({ detail }: { detail: Exclude<DetailItem, Event> }) {
  return (
    <>
      <h2>{detail.type}</h2>
      <dl className="event-meta">
        <dt>Label</dt>
        <dd>{detail.label}</dd>
        <dt>Duration</dt>
        <dd>{formatMs(detail.duration_ms)}</dd>
      </dl>
      {detail.token_usage !== null && (
        <pre className="code-block">{JSON.stringify(detail.token_usage, null, 2)}</pre>
      )}
    </>
  );
}

/** Event tab: full detail for the selected timeline segment or event-list row. */
export function EventInspector({ detail, events }: EventInspectorProps) {
  if (detail === null) {
    return <p className="panel-empty">Select an event or segment to inspect its details.</p>;
  }

  if (isEventDetail(detail)) {
    return <FullEventDetail event={detail} />;
  }

  const event = resolveEvent(detail, events);
  if (event !== null) {
    return <FullEventDetail event={event} />;
  }
  return <SegmentOnlyDetail detail={detail} />;
}
