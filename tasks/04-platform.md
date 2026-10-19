# 04 — Ledger, workflow, storage and API

- **Issue:** #6 (sub-issue of #1)
- **Branch:** `agent/platform`
- **Phase:** 2
- **Depends on:** 03-engine merged (evaluator API stable)
- **Owns:** `src/abhiyogah/ledger/`, `src/abhiyogah/workflow/`, `src/abhiyogah/store/`,
  `src/abhiyogah/api/`, `src/abhiyogah/worker/`, `alembic/`, `alembic.ini`, `tests/ledger/`,
  `tests/workflow/`, `tests/store/`, `tests/api/`, `tests/worker/`, `openapi.json`
- **Goal:** make the engine usable by a bank: persist events and decisions, enforce the IO workflow
  gates, and expose it all over a secured REST API with a scheduler that re-evaluates over time.

## Checklist

### Ledger (pure)
- [x] Canonical JSON serialisation of `DecisionRecord`; `hash = sha256(prev_hash + canonical_json)`.
- [x] `verify_chain(records)` that pinpoints the first broken link; tests that tamper with a record.

### Workflow (pure)
- [x] Three-state outcome gate (A14): closing a complaint requires one of the three outcomes.
- [x] No same-unit closure and senior review before IO (A15): `can_close(complaint, actor)` with reasons.
- [x] IO auto-escalation (A13): a PARTIALLY_RESOLVED / WHOLLY_REJECTED outcome produces a required
      `IO_REFERRED` action with the evaluator's deadline. Exclusion routing (A16) as data, not code branches.
- [x] Every "not a complaint" or "no deficiency" decision from perception creates a human-review task.

### Storage
- [x] SQLAlchemy 2 models + Alembic migrations: `events` (append-only, occurred_at + recorded_at),
      `decision_records` (hash-chained), `review_tasks`. DB-level guard against UPDATE/DELETE on evidence.
- [x] `@pytest.mark.db` tests, skipped without `DATABASE_URL`.

### API (FastAPI)
- [x] Role-based auth from day one (API keys with roles for v0; OIDC later). No unauthenticated write route.
- [x] `POST /complaints/{id}/events`, `GET /complaints/{id}` (facts, deadlines, breaches, actions),
      `GET /complaints/{id}/decisions`, `GET /decisions/{id}/explain` (rendered from the stored record),
      `GET /obligations`, `GET /board/deadlines?within_days=`.
- [x] `as_of` query parameter on reads, admin-only, for time-travel demos.
- [x] `make openapi` exports `openapi.json`.

### Worker
- [x] procrastinate periodic task: re-evaluate open complaints every N minutes and on each new event;
      append new decision records only when the result changed.
- [x] End-to-end test over the API with test obligations shaped like the rule pack (A13 limbs,
      a RBCCB-2025-72-like shadow-credit clock): post → deadlines → reject → time travel past day 20 →
      breach and IO referral → chain verifies (`tests/api/test_end_to_end.py`).
- [ ] Definition-of-done end-to-end against the merged rule pack: the UPI fraud demo returns the IO
      deadline, the shadow-credit deadline and the liability tier. Needs rule pack #16, engine #27
      (main's evaluator raises ParameterError on RBCCB-2025-67-71) and DecisionRecord outputs #28 in main.
- [ ] Write `STREAM COMPLETE`.

## Definition of done
End-to-end test: post the UPI fraud demo events → API returns IO deadline, shadow-credit deadline and
liability tier → time-travel past day 20 → breach and required IO referral appear → chain verifies.

## Requests

- docs/open-questions.md owner: add the cl. 14(5)(c)-(e) IO-routing question (#26) as the next Q; the workflow routes those limbs to human review until it is answered.
- console: `openapi.json` is published at the repo root; regenerate the client with `OPENAPI_SPEC=../openapi.json pnpm openapi` (or `make openapi`). The console typechecks against it as is. New: `ComplaintDetail` adds `deadlines`, `breaches`, `required_actions`, `review_tasks`; `ChainStatus` adds `reason` and `head`; every route needs `X-API-Key`.
- foundation (`.env.example`, `docker-compose.yml`): add `ABHIYOGAH_API_KEYS`, `ABHIYOGAH_PROFILE`, `ABHIYOGAH_RULES_DIR`, `ABHIYOGAH_REEVALUATE_MINUTES` placeholders (documented in `src/abhiyogah/api/settings.py`), and run `alembic upgrade head` plus `procrastinate --app=abhiyogah.worker.app.app schema --apply` (first run only) before the api and worker start. The `openapi` target in the Makefile was filled in by this stream (it was a stub).

## Log

- 2026-10-19 · item 1 done · ledger.chain: canonical_json, record_hash, seal_chain, chain_head on top of domain DecisionRecord helpers · next: verify_chain pinpointing the first broken link
- 2026-10-19 · item 2 done · ledger.verify_chain returns ChainStatus (verified, length, broken_at, reason, head); tamper/remove/reorder/unsealed tests + hypothesis · next: three-state outcome gate (A14)
- 2026-10-19 · item 3 done · workflow.outcome_gate + A16 exclusion routing table (c-e exempt, routed to human review, #26) · next: can_close with same-unit and senior-review checks (A15)
- 2026-10-19 · item 4 done · workflow.can_close(facts, actor): outcome gate + same-unit + senior review before IO + IO decision for adverse outcomes, all reasons cited · next: IO auto-escalation required action (A13)
- 2026-10-19 · item 5 done · workflow.io_escalation: REFER_TO_IO action with the evaluator's IO_REFERRED deadline; routing via EXCLUSION_ROUTES data · next: human-review tasks for perception 'not a complaint'/'no deficiency'
- 2026-10-19 · item 6 done · workflow.review: PerceptionFinding → ReviewTask for NOT_A_COMPLAINT/NO_DEFICIENCY (any source), plus routing review for cl. 14(5)(c)-(e) adverse outcomes · next: SQLAlchemy models + Alembic migrations
- 2026-10-19 · item 7 done · store: Store protocol, MemoryStore, SqlStore (advisory lock + unique chain link), Alembic 0001 with triggers refusing UPDATE/DELETE/TRUNCATE on events and decision_records; alembic check clean on local PG 16 · next: @pytest.mark.db tests
- 2026-10-19 · item 8 done · db tests: store contract on Postgres, migrations==models, triggers refuse UPDATE/DELETE/TRUNCATE, review task closes only via event, no forks, 16 concurrent appends verify; 30 passed against local PG 16, skipped without DATABASE_URL · next: API auth (API keys with roles)
- 2026-10-19 · item 9 done · api.auth: X-API-Key → Principal with ordered roles READER<WRITER<ADMIN, keys from ABHIYOGAH_API_KEYS held as SHA-256, constant-time lookup, require(role) dependency (route-wide 'no unauthenticated write' test lands with the routes) · next: API endpoints
- 2026-10-19 · item 10 done · api.app create_app/app: POST events (validated by folding, idempotent, 409 on reuse, re-evaluates), findings→review tasks, GET complaints/complaint/closure/decisions/decision/explain/obligations/board/review-tasks; worker.reevaluate appends only material changes; ledger.render_explanation; every route but /health needs a key (tested) · next: as_of admin-only on every read
- 2026-10-19 · item 11 done · as_of: ADMIN-only on all 6 read routes that take it (403 for reader/writer, discovered from the route table), offset required, echoed in the detail · next: make openapi
- 2026-10-19 · item 12 done · make openapi → python -m abhiyogah.api.openapi writes openapi.json (env-independent) and regenerates the console client where pnpm exists; staleness test; console typechecks against it (regeneration left to console, see Requests) · next: worker periodic re-evaluation
- 2026-10-19 · item 13 done · worker.app: procrastinate App (Psycopg or in-memory connector), periodic reevaluate_open every ABHIYOGAH_REEVALUATE_MINUTES + reevaluate_complaint task; worker.schedule sweeps only complaints time can change (RUNNING/BREACHED/INSUFFICIENT_FACTS, new rule version, validity edge crossed); append only on material change (trace excluded: it names as_of); API re-evaluates inline on each new event · next: end-to-end definition-of-done test, then STREAM COMPLETE
- 2026-10-19 · item 14 done · synthetic E2E (IO + shadow-credit-like clock) over the API passes; fix: events are kept and engine errors reported (201 + evaluation_error, 500 with message on reads, sweep continues) · next: rule-pack E2E
- 2026-10-19 · BLOCKED: DoD E2E needs #16 (rule pack), #27 (engine: tier/limits on RBCCB-2025-67-71) and #28 (outputs) merged into main. Resume: merge origin/main, run the UPI fraud demo through the API with rules/obligations, then STREAM COMPLETE.
