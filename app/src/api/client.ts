import { FETCH_TIMEOUT_MS } from "../config";
import type {
  Event,
  HealthStatus,
  ReplayResponse,
  Run,
  Snapshot,
  SnapshotSummary,
  Timeline,
} from "../types";

const DEFAULT_SERVER_URL = "http://127.0.0.1:7823";

/** Human-readable error thrown when the Chronicle server can't be reached or returns a failure. */
export class ChronicleApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ChronicleApiError";
  }
}

interface ServerErrorBody {
  error?: string;
  detail?: string;
}

async function parseErrorDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as ServerErrorBody;
    return typeof body.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${DEFAULT_SERVER_URL}${path}`, {
      ...init,
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ChronicleApiError(
        "Chronicle server did not respond in time. Is it running?"
      );
    }
    throw new ChronicleApiError(
      "Could not reach the Chronicle server. Is it running?"
    );
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    throw new ChronicleApiError(
      detail ?? `Chronicle server returned an error (${response.status})`,
      response.status
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const chronicleApi = {
  listRuns: (): Promise<Run[]> => request("/runs"),
  listRunEvents: (runId: string): Promise<Event[]> => request(`/runs/${runId}/events`),
  getRunTimeline: (runId: string): Promise<Timeline> => request(`/runs/${runId}/timeline`),
  deleteRun: (runId: string): Promise<void> => request(`/runs/${runId}`, { method: "DELETE" }),
  checkHealth: (): Promise<HealthStatus> => request("/health"),
  listRunSnapshots: (runId: string): Promise<SnapshotSummary[]> =>
    request(`/runs/${runId}/snapshots`),
  getSnapshot: (runId: string, snapshotId: string): Promise<Snapshot> =>
    request(`/runs/${runId}/snapshots/${snapshotId}`),
  replay: (runId: string, snapshotId: string, modifications: Record<string, unknown>): Promise<ReplayResponse> =>
    request("/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, snapshot_id: snapshotId, modifications }),
    }),
};
