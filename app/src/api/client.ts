import { FETCH_TIMEOUT_MS } from "../config";
import type {
  BackfillResult,
  ChronicleAssertion,
  ChronicleTest,
  Event,
  HealthStatus,
  MetricsOverview,
  ModelMetrics,
  ReplayResponse,
  Run,
  RunMetrics,
  Snapshot,
  SnapshotSummary,
  TestResult,
  Timeline,
  ToolMetrics,
  TrendMetric,
  TrendPeriod,
  TrendPoint,
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
  listTests: (): Promise<ChronicleTest[]> => request("/tests"),
  getTest: (testId: string): Promise<ChronicleTest> => request(`/tests/${testId}`),
  createTest: (params: {
    name: string;
    sourceRunId: string;
    sourceSnapshotId: string | null;
    assertions: Omit<ChronicleAssertion, "assertion_id">[];
  }): Promise<ChronicleTest> =>
    request("/tests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: params.name,
        source_run_id: params.sourceRunId,
        source_snapshot_id: params.sourceSnapshotId,
        assertions: params.assertions,
      }),
    }),
  deleteTest: (testId: string): Promise<void> => request(`/tests/${testId}`, { method: "DELETE" }),
  runTest: (testId: string): Promise<TestResult> =>
    request(`/tests/${testId}/run`, { method: "POST" }),
  getTestHistory: (testId: string): Promise<TestResult[]> => request(`/tests/${testId}/history`),
  getMetricsOverview: (): Promise<MetricsOverview> => request("/metrics/overview"),
  listMetricsRuns: (params?: {
    limit?: number;
    offset?: number;
    fromDate?: string;
    toDate?: string;
    framework?: string;
    status?: string;
  }): Promise<RunMetrics[]> => {
    const query = new URLSearchParams();
    if (params?.limit !== undefined) query.set("limit", String(params.limit));
    if (params?.offset !== undefined) query.set("offset", String(params.offset));
    if (params?.fromDate !== undefined) query.set("from_date", params.fromDate);
    if (params?.toDate !== undefined) query.set("to_date", params.toDate);
    if (params?.framework !== undefined) query.set("framework", params.framework);
    if (params?.status !== undefined) query.set("status", params.status);
    const qs = query.toString();
    return request(`/metrics/runs${qs ? `?${qs}` : ""}`);
  },
  getMetricsTrends: (period: TrendPeriod, metric: TrendMetric, stat?: "avg" | "p95"): Promise<TrendPoint[]> =>
    request(`/metrics/trends?period=${period}&metric=${metric}${stat ? `&stat=${stat}` : ""}`),
  listMetricsTools: (): Promise<ToolMetrics[]> => request("/metrics/tools"),
  listMetricsModels: (): Promise<ModelMetrics[]> => request("/metrics/models"),
  backfillMetrics: (): Promise<BackfillResult> => request("/metrics/backfill", { method: "POST" }),
};
