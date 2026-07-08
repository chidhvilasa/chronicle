# Security Audit — v0.8.0

This document summarizes the security-focused work done for the v0.8.0
release. It is a retrospective audit record, not a promise of
comprehensiveness — see "What Chronicle does NOT protect against" below for
the honest limits of this work. For how to report a new vulnerability, see
`SECURITY.md`.

## Executive summary

v0.8.0 was Chronicle's first release with a dedicated security pass. Prior
releases (v0.1.0–v0.7.0) focused on features; nothing had been specifically
audited for injection, resource-exhaustion, or data-integrity issues. This
release:

- Audited every SQL statement in `server/src/database.py` for injection —
  found none (all queries were already parameterized), but added regression
  tests proving it.
- Closed two real path-traversal/RCE-adjacent gaps: unvalidated
  `graph_module`/`graph_attr` reaching `importlib.import_module()`, and
  unvalidated `run_id` reaching a local file path.
- Added ingestion-time guards against oversized/malformed/replay-bombing
  payloads that had no limits before.
- Added a SHA-256 hash chain so tampering with stored trace data (not
  transport, not access — see scope below) is detectable after the fact.
- Ran a dependency audit (`pip-audit`, `npm audit`) and a secrets scan
  across the full git history.
- Fuzzed every public parser and hardened the replay engine against 10
  adversarial scenarios (corrupted JSON, invalid UTF-8, circular
  references, timestamp abuse, depth bombs).

No penetration test, no external audit, and no fuzzing beyond
Hypothesis-generated inputs against the endpoints listed below has been
performed. Chronicle remains a local-first, single-user developer tool with
no authentication layer, by design (see `SECURITY.md`'s scope section) —
this audit hardens that local trust boundary, it does not add a network
security perimeter.

## Completed work, by commit

### `03c7790` — SQL injection and path traversal hardening

- **SQL injection**: audited every statement in `server/src/database.py`.
  All queries already used parameterized `?` placeholders with values
  passed separately — no string interpolation into SQL anywhere. No
  vulnerability found; added regression tests (`test_security.py`) proving
  common injection payloads (`' OR '1'='1`, `'; DROP TABLE events; --`,
  etc.) are treated as literal, non-matching string values.
- **`POST /register` path/import injection**: `graph_module`/`graph_attr`
  had zero validation before being passed straight to
  `importlib.import_module()`. A request body could name an arbitrary
  importable module. Fixed with a strict allowlist regex (dotted
  identifiers only — no leading dot, no `..`, no slashes) rejecting
  anything else before it reaches `importlib`.
- **SDK local-fallback path traversal**: `chronicle_runs/{run_id}.json`
  built its file path directly from `run_id` with no validation. A
  `run_id` like `"../../etc/passwd"` could escape the intended directory.
  `write_local_events`/`write_local_snapshots` now require `run_id` to be a
  valid UUID, raising `InvalidRunIdError` (caught and logged as a warning,
  never crashing the agent) otherwise.
- **`ServerManager` subprocess hardening**: added a defensive check that
  `sys.executable` is a real file before spawning it — not an
  attacker-facing boundary (nothing externally-supplied flows into it),
  but a guard against a corrupted interpreter path silently failing later.

### `01662fd` — payload limits, timestamp validation, replay depth limit

- **Payload size limits**: `POST /events` now rejects (413) a batch of more
  than 1000 events, or any single event payload over 1MB, before any
  database work happens.
- **JSON depth limit**: request bodies nested more than 20 levels deep are
  rejected (400), with a `RecursionError` handler as a backstop for bodies
  too deep for Python's own JSON parser to finish parsing at all.
- **Timestamp validation**: events with a timestamp more than 1 hour in the
  future or more than 30 days in the past are rejected (400) at ingestion
  time only — replay reads of already-stored historical events are
  unaffected, since they must keep working regardless of age.
- **Integer overflow clamping**: token counts and `duration_ms` are clamped
  to a signed 32-bit range before reaching SQLite or any downstream
  consumer.
- **Replay depth limit**: `POST /replay` and `POST /tests/{id}/run` now
  reject (400) once a replay-of-a-replay chain would exceed 3 levels deep,
  preventing unbounded replay recursion.
- **Dependency audit**: `pip-audit`/`npm audit` found and fixed one CVE
  (`h11`, CVE-2025-43859, request smuggling — pinned to 0.16.0+) plus three
  non-CVE hardening upgrades (echarts XSS advisory, diff DoS in an unused
  path, vitest arbitrary-file-read in vitest-UI). Both audits report zero
  known vulnerabilities against Chronicle's actual runtime dependencies as
  of this release.
- **Secrets scan**: `git log --all -S` for password/secret/api_key/
  private-key patterns, plus a working-tree grep, both came back empty.
  `.env` is git-ignored; `.env.example` holds only placeholder values.

### `3ed601b` — trace integrity chain hashing

- Every event gets a `event_hash` (SHA-256 over its immutable fields) and a
  `chain_hash` binding it to every prior event in the run, recomputed from
  scratch whenever a run's events change (mirroring the existing
  recompute-from-source pattern used for run aggregates, so it holds even
  under out-of-order or replayed inserts).
- New `GET /runs/{run_id}/verify` endpoint and `chronicle verify` CLI
  command detect tampering (a changed `event_hash`) and structural
  breakage (a deleted/reordered/inserted event, via a broken `chain_hash`)
  after the fact.
- This detects tampering with data already at rest in the local SQLite
  file — it is **not** a cryptographic signature and does not prevent
  tampering (anyone with write access to the SQLite file can recompute the
  whole chain themselves). See scope note below.

### Also hardened this release (not separately requested, found along the way)

- **`b339c8e`** — 10 adversarial replay scenarios (corrupted JSON in any
  stored column, invalid UTF-8, circular graph state, future/negative
  timestamps, replay-depth abuse) surfaced and fixed several unhandled-500
  paths in `database.py`/`main.py`/the LangGraph adapter's `_json_safe`.
- **`4c0769f`** — Hypothesis fuzzing of `POST /events`, `GET
  /metrics/trends`, `GET /runs/{id}/graph`, `POST /replay`, and the SDK's
  `evaluate_assertion()`/serialization paths. Surfaced and fixed two real
  crashes in the assertion runner (invalid regex, non-numeric comparison
  target) that were previously unhandled all the way up through `POST
  /tests/{id}/run`.

## Deferred issues, with risk rating

None of these are believed exploitable over a network, since the server
binds to `127.0.0.1` by default — risk ratings below assume that boundary
holds (see `THREAT_MODEL.md` for what happens if it doesn't).

| Issue | Risk | Reason deferred |
| --- | --- | --- |
| No authentication on any server endpoint | Medium | By design for a localhost-only dev tool (see `SECURITY.md`); becomes High if a user manually binds the server to `0.0.0.0` or a public interface, which Chronicle does not prevent. |
| No rate limiting on any endpoint | Low | Local single-user tool; a local process spamming its own server is a self-inflicted resource problem, not a cross-boundary attack. |
| `chain_hash`/`event_hash` is a detection mechanism, not a prevention mechanism | Low | Anyone with write access to the SQLite file can recompute the entire chain and produce a self-consistent tamper. Full tamper-*prevention* would need append-only storage or external signing, out of scope for a local debugging tool. |
| Replay's `graph.invoke()` re-executes the agent's real tools (DB writes, API calls, side effects) | Medium | No dry-run/side-effect detection exists; carried forward from v0.4.0 (see `KNOWN_ISSUES.md`). Fixing this needs a sandboxing or side-effect-interception design that's out of scope for a security patch release. |
| No schema validation on replay `modifications` | Low | Bad input just surfaces as whatever error the target graph raises; the replay run is marked `"failed"` rather than crashing the server. |
| Local JSON fallback (`chronicle_runs/*.json`) is not concurrency-safe | Low | Read-modify-write race between multiple processes writing the same `run_id`; can drop events, cannot corrupt beyond that file. Single-process local dev is the primary use case. |
| `chronicle-server`'s optional runtime dependency on `chronicle-sdk` (for replay) widens the code executed by an untrusted graph module string | Medium | Mitigated by the `03c7790` allowlist regex on `graph_module`/`graph_attr`, but a legitimately-registered graph is still arbitrary Python code that runs with the server process's full privileges when replayed — this is inherent to "replay re-imports and re-invokes your agent code," not a bug to fix. |

## What Chronicle does NOT protect against

Be honest about the boundary: this audit hardened the server and SDK
against malformed/hostile *input* reaching well-defined endpoints. It does
**not**:

- Provide authentication, authorization, or any notion of a user account.
  Anyone who can reach the port Chronicle listens on can read, write, and
  delete every run.
- Encrypt data at rest. The SQLite database and `chronicle_runs/*.json`
  fallback files are plain, unencrypted files on disk.
- Encrypt data in transit. All traffic is plain HTTP, appropriate for
  `127.0.0.1` loopback traffic only.
- Prevent a registered, replayed graph from doing anything a normal Python
  program running as the server process could do — replay is "re-invoke
  your own agent code," not a sandbox.
- Detect or prevent supply-chain compromise of Chronicle's own
  dependencies beyond a point-in-time `pip-audit`/`npm audit` run at
  release time.
- Protect against a malicious actor with filesystem access to the machine
  Chronicle runs on. If they can read `chronicle_runs/`, the SQLite file,
  or memory, they can read everything Chronicle has recorded, including
  full LLM prompts/responses and tool arguments/results — which may
  contain secrets if the traced agent's own inputs/outputs did.
- Constitute a formal security audit by a third party. This document is a
  summary of first-party engineering work, not an independent review.
