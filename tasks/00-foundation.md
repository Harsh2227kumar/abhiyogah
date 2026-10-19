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
- [ ] GitHub Actions workflow `.github/workflows/ci.yml` running `make setup && make check` on push and PR.
- [ ] `domain/enums.py`: `DayBasis` (CALENDAR, WORKING), `BasisStatus` (EXPLICIT, INFERRED),
      `Verification` (PRIMARY_TEXT_READ, SECONDARY_ONLY, UNVERIFIED, CONFLICTING), `RuleStatus`
      (DRAFT, FUTURE_DATED, IN_FORCE, SUPERSEDED, REPEALED_BUT_SAVED), `Deontic` (OBLIGATION,
      PROHIBITION, PERMISSION), `Outcome` (FULLY_RESOLVED, PARTIALLY_RESOLVED, WHOLLY_REJECTED),
      `EntityType`, `Channel` (UPI_P2P, UPI_MERCHANT, IMPS, ATM, MICRO_ATM, CARD_TO_CARD, POS_CARD_PRESENT,
      CARD_NOT_PRESENT, AEPS, APBS, NACH, PPI_ON_US, PPI_OFF_US, OTHER), `AccountType` (for the B5 caps),
      `FactSource` (HUMAN, SYSTEM, LLM).
- [ ] `domain/money.py`: `Paise` NewType plus helpers `rupees(n) -> Paise` and `format_inr(p)`.
- [ ] `domain/events.py`: `EventType` enum with at least the events in the report's architecture diagram
      and clock table (BANK_RECEIVED, ACKNOWLEDGED, INFO_REQUESTED, OUTCOME_SET, IO_REFERRED, IO_DECIDED,
      FINAL_REPLY_SENT, CUSTOMER_REPORTED, ALERT_RECEIVED, SHADOW_CREDITED, REVERSAL_POSTED,
      LIABILITY_DETERMINED, RBI_RECEIVED, RBIO_DIRECTION_RECEIVED, WRITTEN_RESPONSE_FILED,
      AWARD_RECEIVED, ACCEPTANCE_LETTER_RECEIVED, COMPLIANCE_INTIMATED, APPEAL_FILED,
      ALL_DOCUMENTS_RECEIVED, CLAIM_SETTLED, FULL_REPAYMENT, DOCUMENTS_RELEASED). Also a `ComplaintEvent`
      model: event_id, complaint_id, type, occurred_at (business time), recorded_at (system time),
      payload, source (`FactSource`), and provenance (actor, or model + prompt_version + span).
- [ ] `domain/complaint.py`: an RBI-native fact model `ComplaintFacts` (bank_receipt_date,
      rbi_receipt_date, outcome, transaction_date_t, reversal_date_r, channel, account_type,
      amount_paise, home_branch_state, entity_type, external_tat_days, ...). Every field is optional;
      each value carries its provenance. Derive it by folding a list of `ComplaintEvent`.
- [ ] `domain/decision.py`: `DecisionRecord` with the fields listed under "Every decision leaves a record
      that can be replayed" in the report (complaint_id, obligation_id, obligation_version, clause,
      anchor_date, input facts with provenance, condition trace, computed deadline, calendar_version,
      result, compensation with formula, as_of, prev_hash, hash). Add a `Deadline` model (due_date,
      basis, basis_status, start_event, stop_event) and a `Breach` model.
- [ ] `registry/schema.py`: Pydantic model of one obligation YAML file, matching the report's example
      (`obligation_id, deontic, subject, instrument, instrument_ref, clause, source_url, applies_to,
      trigger, clock{start, stop, basis, basis_status, tz, pause}, parameters{name: {effective_date:
      {value, reference, verification}}}, overridden_by, valid_from, valid_to, status, verification,
      signed_off_by, supersedes_note, tests`). `pause` exists but defaults to `null`.
- [ ] `rules/README.md` explaining the obligation file format with the report's IO-CB-2026-14-1-b example,
      and `rules/scenarios/_schema.md` defining the scenario format: `obligation_ids`, `entity_profile`,
      `events: [{type, occurred_at, payload}]`, `as_of`, `expect: {deadlines, breaches, compensation_paise,
      required_actions}`. Write one hand-checked example scenario for A13 (20-day IO escalation).
- [ ] `tests/domain/` covering event folding into `ComplaintFacts` and `DecisionRecord` round-tripping.
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
