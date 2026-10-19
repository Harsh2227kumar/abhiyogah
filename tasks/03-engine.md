# 03 — Clock engine, evaluator and calculators

- **Issue:** #5 (sub-issue of #1)
- **Branch:** `agent/engine`
- **Phase:** 1 (parallel with 01, 02)
- **Depends on:** 00-foundation merged. Uses 01's calendar and 02's rules once they are merged; until
  then, use the `BankCalendar` protocol with a test double, and the example scenario from 00.
- **Owns:** `src/abhiyogah/clocks/`, `src/abhiyogah/evaluator/`, `src/abhiyogah/calculators/`,
  `tests/clocks/`, `tests/evaluator/`, `tests/calculators/`, `tests/scenarios/` (the scenario runner)
- **Goal:** turn (obligations, events, calendar, as_of) into deadlines, breaches, compensation and
  `DecisionRecord`s, deterministically and replayably.

## Checklist

- [x] `clocks/`: a `Clock` built from an obligation's clock spec and a complaint's events: start, stop,
      (pause/resume supported but unused), day basis, IST dates, explicit rounding. `due_date(...)`,
      `state(as_of) -> RUNNING | STOPPED_ON_TIME | STOPPED_LATE | BREACHED`, `days_remaining(as_of)`.
- [x] Overrides: `overridden_by` (for example 20 days vs TAT − 10 days) resolves to one deadline with
      the reason recorded in the trace.
- [ ] `evaluator/`: `evaluate(complaint_events, obligations, calendar, as_of) -> list[DecisionRecord]`.
      For each applicable obligation: check applicability (entity profile), resolve parameters at the
      correct anchor date (bank receipt, RBI receipt or T, as the obligation says), build the clock and
      record a per-condition trace. Pure function; no I/O; `as_of` is required.
- [ ] Breach forecasting: `forecast(…, horizon_days)` lists deadlines falling due within the horizon.
- [ ] `calculators/failed_txn.py`: `100 × max(0, R − (T + n))` rupees in paise, payee/originator rule (B1).
- [ ] `calculators/limited_liability.py`: tier from `delay_working_days` (0 / min(txn, cap) / board
      policy), caps by account type (B5); shadow credit due date (B6); determination date (B7).
- [ ] `calculators/service_events.py`: the C-table formulas listed in the report (property documents
      ₹5,000/day, deceased deposits Bank Rate + 4%, card closure ₹500/day, credit information ₹100/day).
      Parameters always come from the registry, never from constants in code.
- [ ] Scenario runner `tests/scenarios/test_scenarios.py`: loads every `rules/scenarios/*.yaml`, runs the
      evaluator, compares deadlines, breaches and paise exactly. Wired into `make rules`.
- [ ] Replay test: evaluating the same events at the same `as_of` twice yields byte-identical records.
- [ ] Time-travel test: one complaint evaluated at day 5, 19, 20 and 21 shows the IO clock RUNNING then BREACHED.
- [ ] Write `STREAM COMPLETE`.

## Definition of done
Every scenario from stream 02 passes; mypy strict clean; import-linter confirms no I/O imports.

## Requests

- To the rule-pack stream (02), FYI on override scenarios: when an `overridden_by` obligation applies
  (e.g. IO-CB-2026-14-1-a), it reports the deadline, breach and actions; the overridden obligation
  (IO-CB-2026-14-1-b) reports `NOT_APPLICABLE` with the override in its trace and no deadline. If
  more than one override applies the engine raises `OverrideConflictError` rather than choosing.

## Log
- 2026-10-19 · item 1 done · clocks/: Clock (due_date/state/days_remaining/days_late, IST rounding, pauses supported but unused), BankCalendar protocol + FakeCalendar double, build_clock from facts · next: item 2 overrides
- 2026-10-19 · item 2 done · clocks/overrides.py: resolve_overrides picks one deadline (replacement, conflict is an error) and traces each override · next: item 3 evaluator
