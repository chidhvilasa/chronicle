# Threat Model

This document describes who Chronicle is built for, who might attack it,
where the trust boundaries are between its three components, and what
mitigates each threat as of v0.8.0. See `SECURITY_AUDIT.md` for the work
that produced these mitigations, and `SECURITY.md` for how to report a new
vulnerability.

## Users

Chronicle is built for **Python developers building AI agents** — a single
developer, running Chronicle locally alongside the agent process they're
debugging, on their own machine. It is not built for multi-tenant use, a
shared team server, or any deployment where the person running Chronicle
and the person whose data it's recording are different people.

## Attackers / threat sources

Three realistic sources of hostile input, in order of how directly this
release's work addresses them:

1. **Malicious or corrupted trace files.** A `chronicle_runs/{run_id}.json`
   fallback file, or the SQLite database itself, could be hand-edited,
   corrupted by a crashed write, or come from a run someone else shared
   with you. Chronicle must not crash or execute anything when reading
   damaged or adversarially-crafted trace data.
2. **Hostile tool outputs.** The agent Chronicle is tracing calls real
   tools (web requests, shell commands, retrieval) whose outputs are
   attacker-influenced in the general case (e.g. a tool that fetches web
   content). Chronicle records that data — a hostile tool output should be
   able to make itself *ugly* in the timeline, never able to make Chronicle
   itself misbehave (crash, execute code, corrupt other runs).
3. **Local network.** Anything else on the same machine, or the same LAN if
   the loopback boundary is ever broken (e.g. a misconfigured port forward,
   a container network that exposes 127.0.0.1 more broadly than intended).
   Chronicle has no authentication layer and assumes this boundary holds
   (see `SECURITY.md`); it does not defend against a network attacker who
   can already reach the port.

Explicitly **not** modeled: a malicious package maintainer publishing a
compromised `chronicle-sdk`/`chronicle-server` release (supply-chain
compromise of Chronicle's own distribution), or a remote attacker with no
network path to the machine at all.

## Trust boundaries

```
                    trust boundary A                trust boundary B
                    (process/HTTP)                   (HTTP, loopback only)
                          │                                 │
 ┌────────────────┐       │       ┌────────────────┐        │       ┌──────────────────┐
 │  agent process   │      │       │  chronicle-server │      │       │  chronicle-app     │
 │  + chronicle-sdk │◀─────┼──────▶│  (FastAPI)         │◀─────┼──────▶│  (Tauri desktop)    │
 │                  │  P1  │       │                    │  P2  │       │                    │
 └────────┬─────────┘      │       └─────────┬──────────┘      │       └──────────────────────┘
          │                │                 │                │
          │ P3 (local file)│                 │ P4 (local file)│
          ▼                │                 ▼                │
 ┌────────────────────┐    │       ┌────────────────────┐     │
 │ chronicle_runs/*.json│  │       │  SQLite (chronicle.db)│   │
 │ (fallback, no server) │  │       │  events/runs/snapshots │   │
 └────────────────────┘    │       └────────────────────┘     │
                            │                                  │
                  data crosses this boundary            data crosses this boundary
                  as JSON over HTTP POST                as JSON over HTTP GET
                  (P1: POST /events, /snapshots,         (P2: GET /runs, /runs/{id}/*,
                   /register)                             /runs/{id}/verify, etc.)
```

- **P1 — SDK → server (`POST /events`/`/snapshots`/`/register`)**: the
  agent process is trusted to run its own code, but the *content* of an
  event (a tool's arguments/results, an LLM prompt/response, a graph
  module/attr string) is not trusted once it crosses into the server. This
  is the boundary `01662fd`'s payload/depth/timestamp limits and
  `03c7790`'s `graph_module` allowlist protect.
- **P2 — server → app (`GET /runs/...`)**: the desktop app trusts the
  server's response shape (it's the same codebase's API contract) but not
  necessarily its *content* — a tampered or corrupted database row must
  render safely (no XSS via a crafted event's `data` field reaching the
  DOM unsanitized) rather than crash the UI.
- **P3 — SDK → local file (`chronicle_runs/{run_id}.json`)**: this is the
  fallback path when the server is unreachable. `run_id` used to flow
  unvalidated into a file path (path traversal via `run_id`); `03c7790`
  closed this by requiring `run_id` to be a valid UUID before it's used.
- **P4 — server → SQLite**: internal to the server process; not
  attacker-reachable directly (SQLite is not exposed on the network), but
  every value written here originated from P1 or P2, so this is where
  `3ed601b`'s hash chain lives to detect if something changed the data
  after it was written, by any means (including a bug elsewhere in the
  server, not just an external attacker).

Everything to the left of P1 (the agent's own code, its real tool calls,
its LLM provider) is entirely outside Chronicle's trust boundary — Chronicle
observes and records, it does not sandbox or gate the agent's real
behavior (see `SECURITY_AUDIT.md`'s "What Chronicle does NOT protect
against").

## Mitigations in place after v0.8.0

| Boundary | Threat | Mitigation |
| --- | --- | --- |
| P1 | SQL injection via any event field | All queries parameterized (`?` placeholders); verified by `test_security.py`. |
| P1 | Arbitrary module import via `POST /register` | Dotted-identifier allowlist regex before `importlib.import_module()`. |
| P1 | Resource exhaustion via oversized/deeply-nested batches | 1000 events/request, 1MB/event, 20-level JSON depth, all enforced pre-database. |
| P1 | Replay-of-replay recursion bombing | Depth-3 limit on replay chains via `metadata.replay_depth`. |
| P1 | Integer overflow in token/duration fields | Clamped to signed 32-bit range in `EventIn.to_row()`. |
| P1 | Backdated/future-dated event injection | Timestamps outside [-30d, +1h] rejected at ingestion. |
| P2/P4 | Undetected tampering with stored trace data | SHA-256 event + chain hash, checked via `GET /runs/{id}/verify` / `chronicle verify`. |
| P2/P4 | Corrupted JSON in any stored column crashing the server | `CorruptedDataError` → clean 400, not an unhandled 500 (`b339c8e`). |
| P2/P4 | Invalid UTF-8 in a stored column crashing the server | `text_factory` replaces invalid bytes with U+FFFD instead of raising. |
| P3 | Path traversal via `run_id` in the local JSON fallback | `run_id` must parse as a UUID (`InvalidRunIdError` otherwise, logged and dropped, never crashing the agent). |
| Hostile tool output | Circular-reference graph state hanging/crashing snapshot capture | `_json_safe()` tracks visited container ids per branch; cycles replaced with a marker. |
| Hostile tool output | A malformed regex/non-numeric target crashing assertion evaluation | `evaluate_assertion()` fails the assertion with a reason instead of raising (`4c0769f`). |
| Dependencies | Known CVEs in transitive dependencies | `h11` pinned past CVE-2025-43859; echarts/diff/vitest upgraded past known advisories; `pip-audit`/`npm audit` clean at release time. |

## What isn't mitigated (see also `SECURITY_AUDIT.md`)

No authentication at any boundary, no encryption at rest or in transit, no
sandboxing of replayed agent code, and no protection against someone with
filesystem access to the host machine. These are accepted, documented
trade-offs for a local-first single-user developer tool, not oversights —
see `SECURITY.md`'s scope section for the reasoning.
