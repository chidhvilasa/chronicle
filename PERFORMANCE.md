# Performance — v0.8.0

Results from the stress test suite added in `7249c35`
(`server/tests/test_performance.py`). All 7 tests seed one 10,000-event run
once (module-scoped fixture, since generating and ingesting 10k events is
itself the expensive part) and check the run against 7 latency/throughput
thresholds.

## Thresholds: 7/7 passed

| # | Operation | Threshold | Measured (this machine) | Result |
| - | --- | --- | --- | --- |
| 1 | Ingest 10,000 events (20 batches of 500 via `POST /events`) | < 30s | ~1.8s | Pass |
| 2 | `GET /runs/{id}/events` (all 10,000) | < 2s | ~0.12s | Pass |
| 3 | `GET /runs/{id}/timeline` | < 3s | ~0.13s | Pass |
| 4 | `GET /runs/{id}/graph` | < 5s | ~0.09s | Pass |
| 5 | `GET /metrics/overview` | < 500ms | ~5ms | Pass |
| 6 | `GET /metrics/trends` | < 1s | ~2ms | Pass |
| 7 | `GET /runs/{id}/verify` (recompute + check the full hash chain) | < 60s | ~0.12s | Pass |

Measured on the development machine (Windows, local SQLite file, no
concurrent load). These thresholds are set an order of magnitude or more
above what was actually measured — they exist to catch algorithmic
regressions (an accidental O(n²) loop, a missing index) in CI on
potentially slower hardware, not to represent a tight performance budget.
Exact numbers will vary by machine; treat the pass/fail column, not the
absolute milliseconds, as the durable signal.

## What was optimized

- **Composite SQLite indexes** matching the query shapes actually used by
  the server, so SQLite can satisfy a filter + sort in a single index scan
  instead of a filter followed by a separate sort step:
  - `idx_events_run_id_timestamp` — backs `WHERE run_id = ? ORDER BY
    timestamp ASC` (`GET /runs/{id}/events`, timeline/graph building, hash
    chain recomputation).
  - `idx_snapshots_run_id_step_index` — backs `WHERE run_id = ? ORDER BY
    step_index ASC` (`GET /runs/{id}/snapshots`, replay's snapshot lookup).
  - `idx_test_results_test_id_created_at` — backs `WHERE test_id = ? ORDER
    BY created_at DESC LIMIT ?` (test history views).
- No query logic changes were needed beyond adding these indexes — the
  existing queries already had the right `WHERE`/`ORDER BY` shape, they
  just weren't index-covered before this pass.

## Known scaling limits

- **Runs over 100,000 events are not officially supported.** The stress
  suite validates 10,000 events per run; nothing in the schema or query
  layer hard-caps a run's size, but no test exercises 10x that volume, and
  several code paths that recompute state from scratch on every write (run
  aggregates, the hash chain in `3ed601b`) get proportionally slower as a
  single run's event count grows. A very long-running or extremely
  chatty agent should expect degraded ingest/verify latency well before
  this point, not a hard failure at exactly 100,000.
- **The hash chain (`3ed601b`) is recomputed from scratch on every write
  that touches a run's events**, not incrementally extended. This is O(n)
  per write rather than O(1); fine at the tested scale (10k events, ~0.12s
  to verify), but a pathological workload with very frequent small writes
  to a very large run would pay this cost repeatedly.
- **`POST /metrics/backfill` is synchronous with no batching** (carried
  from v0.5.0, see `KNOWN_ISSUES.md`) — a database with many hundreds of
  complete runs can make a single backfill call slow, independent of any
  one run's size.
- **These thresholds were measured against SQLite on local disk, single
  connection, no concurrent writers.** Chronicle's target deployment
  (single developer, local machine, one agent process at a time) matches
  this, but the numbers above don't say anything about behavior under
  concurrent multi-process write load.
