import type { ChronicleEvent, ChronicleRun } from "../types";

const DEFAULT_SERVER_URL = "http://127.0.0.1:7823";

/** Human-readable error thrown when the Chronicle server can't be reached or returns a failure. */
export class ChronicleApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ChronicleApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${DEFAULT_SERVER_URL}${path}`, init);
  } catch {
    throw new ChronicleApiError(
      "Could not reach the Chronicle server. Is it running?"
    );
  }
  if (!response.ok) {
    throw new ChronicleApiError(
      `Chronicle server returned an error (${response.status})`,
      response.status
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const chronicleApi = {
  listRuns: (): Promise<ChronicleRun[]> => request("/runs"),
  listRunEvents: (runId: string): Promise<ChronicleEvent[]> =>
    request(`/runs/${runId}/events`),
  getRunTimeline: (runId: string): Promise<ChronicleEvent[]> =>
    request(`/runs/${runId}/timeline`),
  deleteRun: (runId: string): Promise<void> =>
    request(`/runs/${runId}`, { method: "DELETE" }),
};
