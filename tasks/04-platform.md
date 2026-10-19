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
- [ ] SQLAlchemy 2 models + Alembic migrations: `events` (append-only, occurred_at + recorded_at),
      `decision_records` (hash-chained), `review_tasks`. DB-level guard against UPDATE/DELETE on evidence.
- [ ] `@pytest.mark.db` tests, skipped without `DATABASE_URL`.

### API (FastAPI)
- [ ] Role-based auth from day one (API keys with roles for v0; OIDC later). No unauthenticated write route.
- [ ] `POST /complaints/{id}/events`, `GET /complaints/{id}` (facts, deadlines, breaches, actions),
      `GET /complaints/{id}/decisions`, `GET /decisions/{id}/explain` (rendered from the stored record),
      `GET /obligations`, `GET /board/deadlines?within_days=`.
- [ ] `as_of` query parameter on reads, admin-only, for time-travel demos.
- [ ] `make openapi` exports `openapi.json`.

### Worker
- [ ] procrastinate periodic task: re-evaluate open complaints every N minutes and on each new event;
      append new decision records only when the result changed.
- [ ] Write `STREAM COMPLETE`.

## Definition of done
End-to-end test: post the UPI fraud demo events → API returns IO deadline, shadow-credit deadline and
liability tier → time-travel past day 20 → breach and required IO referral appear → chain verifies.

## Requests

- docs/open-questions.md owner: add the cl. 14(5)(c)-(e) IO-routing question (#26) as the next Q; the workflow routes those limbs to human review until it is answered.

## Log

- 2026-10-19 · item 1 done · ledger.chain: canonical_json, record_hash, seal_chain, chain_head on top of domain DecisionRecord helpers · next: verify_chain pinpointing the first broken link
- 2026-10-19 · item 2 done · ledger.verify_chain returns ChainStatus (verified, length, broken_at, reason, head); tamper/remove/reorder/unsealed tests + hypothesis · next: three-state outcome gate (A14)
- 2026-10-19 · item 3 done · workflow.outcome_gate + A16 exclusion routing table (c-e exempt, routed to human review, #26) · next: can_close with same-unit and senior-review checks (A15)
- 2026-10-19 · item 4 done · workflow.can_close(facts, actor): outcome gate + same-unit + senior review before IO + IO decision for adverse outcomes, all reasons cited · next: IO auto-escalation required action (A13)
- 2026-10-19 · item 5 done · workflow.io_escalation: REFER_TO_IO action with the evaluator's IO_REFERRED deadline; routing via EXCLUSION_ROUTES data · next: human-review tasks for perception 'not a complaint'/'no deficiency'
- 2026-10-19 · item 6 done · workflow.review: PerceptionFinding → ReviewTask for NOT_A_COMPLAINT/NO_DEFICIENCY (any source), plus routing review for cl. 14(5)(c)-(e) adverse outcomes · next: SQLAlchemy models + Alembic migrations
