/** How often RunList polls `GET /runs`, in milliseconds. */
export const RUN_LIST_POLL_INTERVAL_MS = 3000;

/** How often the top nav re-checks server connectivity, in milliseconds. */
export const HEALTH_CHECK_INTERVAL_MS = 5000;

/** Timeout applied to every fetch call to the Chronicle server, in milliseconds. */
export const FETCH_TIMEOUT_MS = 5000;

/** Estimated cost per input token, in USD, for the timeline's token usage summary. */
export const COST_PER_INPUT_TOKEN_USD = 0.000003;

/** Estimated cost per output token, in USD, for the timeline's token usage summary. */
export const COST_PER_OUTPUT_TOKEN_USD = 0.000015;

/** Maximum zoom multiplier the timeline's zoom-in button can reach. */
export const TIMELINE_MAX_ZOOM = 8;

/** Multiplier applied to the current zoom level per zoom in/out click. */
export const TIMELINE_ZOOM_STEP = 1.5;

/** How often the replay modal polls `GET /runs` while waiting for a replay to finish, in ms. */
export const REPLAY_POLL_INTERVAL_MS = 1000;

/** How long the replay modal polls before giving up and showing a timeout error, in ms. */
export const REPLAY_POLL_TIMEOUT_MS = 60000;

/** How long a toast notification stays on screen before auto-dismissing, in ms. */
export const TOAST_DURATION_MS = 8000;

/** How often the Tests tab polls `GET /tests`, in ms. */
export const TEST_LIST_POLL_INTERVAL_MS = 5000;

/** How often the Performance tab's stat cards poll `GET /metrics/overview`, in ms. */
export const METRICS_POLL_INTERVAL_MS = 30000;

/** How often ServerStatus polls `GET /health` to detect whether the Chronicle server is up, in ms. */
export const SERVER_STATUS_POLL_INTERVAL_MS = 3000;
