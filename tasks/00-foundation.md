# 00 — Foundation (architect)

- **Issue:** #2 (sub-issue of #1)
- **Branch:** `agent/foundation`
- **Phase:** 0. Runs alone; every other stream waits for it to be merged into `main`.
- **Depends on:** nothing
- **Owns:** `pyproject.toml`, `uv.lock`, `Makefile`, `.importlinter`, `.github/workflows/`, `docker-compose.yml`,
  `.env.example`, `src/abhiyogah/__init__.py`, `src/abhiyogah/domain/`, `src/abhiyogah/registry/schema.py`,
  every other package's `__init__.py` stub, `tests/conftest.py`, `tests/domain/`, `rules/README.md`,
  `rules/scenarios/_schema.md`
- **Goal:** fix the contracts that all other streams build against, so they can work in parallel
  without stepping on each other.

## Checklist

- [x] `pyproject.toml` for Python 3.12 with uv: package `abhiyogah` under `src/`. Runtime deps: pydantic>=2,
      pyyaml, holidays, fastapi, uvicorn, sqlalchemy>=2, psycopg[binary]>=3, alembic, procrastinate,
      httpx, structlog. Dev deps: pytest, hypothesis, mypy, ruff, import-linter, types-PyYAML. Ruff and
      mypy (`strict = true`) configured in `pyproject.toml`.
- [x] Empty subpackages with `__init__.py` and a one-line docstring each: domain, registry, calendar,
      clocks, evaluator, calculators, workflow, ledger, store, api, worker, perception, mcp, regwatch,
      reporting (layout in `docs/plan.md` §4).
- [x] `.importlinter` contract: the core (domain, registry, calendar, clocks, evaluator, calculators,
      workflow, ledger) must not import store, api, worker, perception, mcp, regwatch, sqlalchemy,
      psycopg, httpx, fastapi or any LLM SDK. Also `domain` imports nothing else from `abhiyogah`.
- [x] `Makefile` with the targets listed in `CLAUDE.md` (`setup`, `check`, `test`, `rules`, `openapi`,
      `up`). `rules` and `openapi` may print "not implemented yet" for now. `make check` must pass.
- [x] GitHub Actions workflow `.github/workflows/ci.yml` running `make setup && make check` on push and PR.
- [x] `domain/enums.py`: `DayBasis` (CALENDAR, WORKING), `BasisStatus` (EXPLICIT, INFERRED),
      `Verification` (PRIMARY_TEXT_READ, SECONDARY_ONLY, UNVERIFIED, CONFLICTING), `RuleStatus`
      (DRAFT, FUTURE_DATED, IN_FORCE, SUPERSEDED, REPEALED_BUT_SAVED), `Deontic` (OBLIGATION,
      PROHIBITION, PERMISSION), `Outcome` (FULLY_RESOLVED, PARTIALLY_RESOLVED, WHOLLY_REJECTED),
      `EntityType`, `Channel` (UPI_P2P, UPI_MERCHANT, IMPS, ATM, MICRO_ATM, CARD_TO_CARD, POS_CARD_PRESENT,
      CARD_NOT_PRESENT, AEPS, APBS, NACH, PPI_ON_US, PPI_OFF_US, OTHER), `AccountType` (for the B5 caps),
      `FactSource` (HUMAN, SYSTEM, LLM).
- [x] `domain/money.py`: `Paise` NewType plus helpers `rupees(n) -> Paise` and `format_inr(p)`.
- [x] `domain/events.py`: `EventType` enum with at least the events in the report's architecture diagram
      and clock table (BANK_RECEIVED, ACKNOWLEDGED, INFO_REQUESTED, OUTCOME_SET, IO_REFERRED, IO_DECIDED,
      FINAL_REPLY_SENT, CUSTOMER_REPORTED, ALERT_RECEIVED, SHADOW_CREDITED, REVERSAL_POSTED,
      LIABILITY_DETERMINED, RBI_RECEIVED, RBIO_DIRECTION_RECEIVED, WRITTEN_RESPONSE_FILED,
      AWARD_RECEIVED, ACCEPTANCE_LETTER_RECEIVED, COMPLIANCE_INTIMATED, APPEAL_FILED,
      ALL_DOCUMENTS_RECEIVED, CLAIM_SETTLED, FULL_REPAYMENT, DOCUMENTS_RELEASED). Also a `ComplaintEvent`
      model: event_id, complaint_id, type, occurred_at (business time), recorded_at (system time),
      payload, source (`FactSource`), and provenance (actor, or model + prompt_version + span).
- [x] `domain/complaint.py`: an RBI-native fact model `ComplaintFacts` (bank_receipt_date,
      rbi_receipt_date, outcome, transaction_date_t, reversal_date_r, channel, account_type,
      amount_paise, home_branch_state, entity_type, external_tat_days, ...). Every field is optional;
      each value carries its provenance. Derive it by folding a list of `ComplaintEvent`.
- [x] `domain/decision.py`: `DecisionRecord` with the fields listed under "Every decision leaves a record
      that can be replayed" in the report (complaint_id, obligation_id, obligation_version, clause,
      anchor_date, input facts with provenance, condition trace, computed deadline, calendar_version,
      result, compensation with formula, as_of, prev_hash, hash). Add a `Deadline` model (due_date,
      basis, basis_status, start_event, stop_event) and a `Breach` model.
- [x] `registry/schema.py`: Pydantic model of one obligation YAML file, matching the report's example
      (`obligation_id, deontic, subject, instrument, instrument_ref, clause, source_url, applies_to,
      trigger, clock{start, stop, basis, basis_status, tz, pause}, parameters{name: {effective_date:
      {value, reference, verification}}}, overridden_by, valid_from, valid_to, status, verification,
      signed_off_by, supersedes_note, tests`). `pause` exists but defaults to `null`.
- [x] `rules/README.md` explaining the obligation file format with the report's IO-CB-2026-14-1-b example,
      and `rules/scenarios/_schema.md` defining the scenario format: `obligation_ids`, `entity_profile`,
      `events: [{type, occurred_at, payload}]`, `as_of`, `expect: {deadlines, breaches, compensation_paise,
      required_actions}`. Write one hand-checked example scenario for A13 (20-day IO escalation).
- [x] `tests/domain/` covering event folding into `ComplaintFacts` and `DecisionRecord` round-tripping.
- [ ] `docker-compose.yml` (postgres:16, api, worker) and `.env.example` with placeholders only.
- [ ] Update `PROGRESS.md` to mark Phase 0 done. Write `STREAM COMPLETE`.

## Definition of done
`make check` is green on a fresh clone; CI is green; the domain and schema contracts are documented in
docstrings; other streams can start without editing `domain/` beyond small additions via Requests.

## Requests
_(other streams add requests for changes to owned paths here)_

## Log
- 2026-10-19 · item 1 done · pyproject.toml (uv, py3.12, ruff + mypy strict), uv.lock, package root, tests/conftest.py with db skip · next: item 2 subpackages
- 2026-10-19 · item 2 done · 15 subpackage stubs with docstrings + import smoke test · next: item 3 .importlinter
- 2026-10-19 · item 3 done · .importlinter: core-is-pure (no store/api/worker/perception/mcp/regwatch, DB, HTTP, LLM SDKs) + domain-is-leaf; verified it catches a planted httpx import · next: item 4 Makefile
- 2026-10-19 · item 4 done · Makefile (setup/check/test/rules/openapi/up); `rules` auto-runs registry.lint and tests/scenarios once they exist; make check green · next: item 5 CI workflow
- 2026-10-19 · item 5 done · .github/workflows/ci.yml runs make setup && make check on push and PR (uv, py3.12) · next: item 6 domain/enums.py
- 2026-10-19 · item 6 done · domain/enums.py: StrEnums with value == UPPER_SNAKE name (YAML uses COMMERCIAL_BANK etc.); B5 cap amounts left to the rule pack · next: item 7 domain/money.py
- 2026-10-19 · item 7 done · domain/money.py: Paise NewType, rupees() (int only), format_inr() with lakh/crore grouping, hypothesis round-trip · next: item 8 domain/events.py
- 2026-10-19 · item 8 done · domain/events.py: EventType (task list + BANK_COMMUNICATION_SENT, CUSTOMER_DISSATISFIED, FACTS_RECORDED), frozen ComplaintEvent; `source` lives in Provenance (event.source is a shortcut), LLM provenance requires model + prompt_version · next: item 9 domain/complaint.py
- 2026-10-19 · item 9 done · domain/complaint.py: Fact[T] (value + provenance + event_id + recorded_at), ComplaintFacts (all optional, IST dates), fold_events(complaint_id, events, known_at) with documented correction rules; domain/tz.py (IST, ist_date) and domain/errors.py · next: item 10 domain/decision.py
- 2026-10-19 · item 10 done · domain/decision.py: DecisionRecord (+ parameters used, required_actions), DecisionResult, Deadline, Breach, Compensation, InputFact, ConditionTrace; canonical_json/seal/verify_chain for the SHA-256 chain · next: item 11 registry/schema.py
- 2026-10-19 · item 11 done · registry/schema.py: Obligation (+ AppliesTo, Trigger, ClockSpec, ClockPause, ParameterValue); clock.start may be an event or a ComplaintFacts date (e.g. transaction_date_t); stop is a list; optional `anchor`; parameter values need verification; IN_FORCE without PRIMARY_TEXT_READ + signed_off_by is refused at parse time · next: item 12 rules/README.md + scenario schema
- 2026-10-19 · item 12 done · rules/README.md (field table, report example as DRAFT), rules/scenarios/_schema.md (format + runner conventions, due = start + n), example rules/scenarios/io_20d_ordinary_breach.yaml (due 2026-08-23, 2 days late) with a domain test of its hand check · next: item 13 tests/domain
- 2026-10-19 · item 13 done · tests/domain: folding unit tests + hypothesis properties (order independence, known_at == prefix fold), DecisionRecord JSON round-trip and hash-chain tamper tests · next: item 14 docker-compose + .env.example
