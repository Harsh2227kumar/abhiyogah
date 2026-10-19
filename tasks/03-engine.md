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
- [x] `evaluator/`: `evaluate(complaint_events, obligations, calendar, as_of) -> list[DecisionRecord]`.
      For each applicable obligation: check applicability (entity profile), resolve parameters at the
      correct anchor date (bank receipt, RBI receipt or T, as the obligation says), build the clock and
      record a per-condition trace. Pure function; no I/O; `as_of` is required.
- [x] Breach forecasting: `forecast(…, horizon_days)` lists deadlines falling due within the horizon.
- [x] `calculators/failed_txn.py`: `100 × max(0, R − (T + n))` rupees in paise, payee/originator rule (B1).
- [x] `calculators/limited_liability.py`: tier from `delay_working_days` (0 / min(txn, cap) / board
      policy), caps by account type (B5); shadow credit due date (B6); determination date (B7).
- [x] `calculators/service_events.py`: the C-table formulas listed in the report (property documents
      ₹5,000/day, deceased deposits Bank Rate + 4%, card closure ₹500/day, credit information ₹100/day).
      Parameters always come from the registry, never from constants in code.
- [x] Align the evaluator with `rules/obligations/_conventions.md` (rule-pack PR #16): `is set` /
      `is not set`, an unknown fact makes a clause false, validity checked at `as_of`, duration
      parameters `max_days` / `base_days` / `io_review_days` / `base_days` + `filing_window` (A3, with
      `as_of` standing in for an unknown anchor that is the clock's own stop), `PERMISSION` never
      breaches or requires actions.
- [x] Follow the updated conventions: `FUTURE_DATED` rules are never evaluated, `tat_days_by_channel`
      / `follows_underlying_system` durations (B1, B2), one action per obligation with the convention
      codes (`REVERSE_TRANSACTION`, `SHADOW_CREDIT`, `SEND_FINAL_DECISION`, ...).
- [x] Conditions support `or` and parentheses (`and` binds tighter), for the A14 cl. 14(5) exemption
      "exclusion_category is not set or exclusion_category not in [...]" (rules request).
- [x] Filtered clock stops: a `stop_conditions` parameter maps a stop event to a condition checked
      against that event's own payload, so A8 stops only on `APPEAL_FILED` by the complainant and A7
      only on one by the bank (rules request; `ClockSpec.stop` itself stays a list of events).
- [ ] Clockless obligations end `DETERMINED` with `outputs` and required actions (A1 `scheme`; A14
      `classified_at_closure` + `SET_OUTCOME`; A15 `closed_by_other_unit`, `senior_reviewed_before_io`
      + `SENIOR_REVIEW`; A18 `reply_complete`/`missing_elements` + `SEND_CORRECTED_REPLY`), and clock
      obligations carry their outputs (A2 `escalation_open`, A3 `filed_in_time`, A6 `award_lapsed`,
      A8 `appeal_in_time`). Needs `DecisionRecord.outputs` (#25 → PR #28).
- [ ] B5 `RBCCB-2025-67-71` is a determination: its clock only counts `delay_working_days`; it ends
      `DETERMINED` with `delay_working_days`, `liability_tier`, `customer_liability_paise` (uses
      `calculators.limited_liability`).
- [ ] The scenario runner compares `outputs` exactly and runs on the real bank calendar
      (`load_bank_calendar`), not the test double.
- [ ] Scenario runner `tests/scenarios/test_scenarios.py`: loads every `rules/scenarios/*.yaml`, runs the
      evaluator, compares deadlines, breaches and paise exactly. Wired into `make rules`.
- [x] Replay test: evaluating the same events at the same `as_of` twice yields byte-identical records.
- [x] Time-travel test: one complaint evaluated at day 5, 19, 20 and 21 shows the IO clock RUNNING then BREACHED.
- [ ] Write `STREAM COMPLETE`.

## Definition of done
Every scenario from stream 02 passes; mypy strict clean; import-linter confirms no I/O imports.

## Requests

- To the rule-pack stream (02), FYI on override scenarios: when an `overridden_by` obligation applies
  (e.g. IO-CB-2026-14-1-a), it reports the deadline, breach and actions; the overridden obligation
  (IO-CB-2026-14-1-b) reports `NOT_APPLICABLE` with the override in its trace and no deadline. If
  more than one override applies the engine raises `OverrideConflictError` rather than choosing.
- To the rule-pack stream (02), FYI: the evaluator follows `rules/obligations/_conventions.md`. It
  also accepts `is known`/`is unknown`, `==`, `!=` and integer `<`/`>` clauses, and an optional
  `compensation_per_day_paise` parameter (per calendar day late) for B1 and the C-table.
- To the foundation/domain owner (same as the rule-pack request in issue #20): `DecisionResult.DETERMINED`
  and an `outputs` field on `DecisionRecord`, so clockless obligations (A1, A14, A15, A18) and outputs
  such as `escalation_open` can be reported. Today clockless obligations end `NOT_APPLICABLE` with
  an "obligation has a clock: false" trace line.
- Engine side, once 02 merges: switch `evaluator/parameters.parameter_at` to `registry/resolve.py`.

## Log
- 2026-10-19 · item 1 done · clocks/: Clock (due_date/state/days_remaining/days_late, IST rounding, pauses supported but unused), BankCalendar protocol + FakeCalendar double, build_clock from facts · next: item 2 overrides
- 2026-10-19 · item 2 done · clocks/overrides.py: resolve_overrides picks one deadline (replacement, conflict is an error) and traces each override · next: item 3 evaluator
- 2026-10-19 · item 3 done · evaluator/: evaluate() with applicability, trigger condition grammar, anchor/validity, dated parameters (max_days/min_days/tat_minus_days), clock, overrides, breach and required actions, per-step trace · next: item 4 forecast
- 2026-10-19 · item 4 done · evaluator/forecast.py: forecast()/forecast_records() list RUNNING deadlines due within a calendar-day horizon, soonest first · next: item 5 failed_txn calculator
- 2026-10-19 · item 5 done · calculators/failed_txn.py (per_day x max(0, R-(T+n)), recipient rule) + per_day.py; evaluator applies compensation_per_day_paise to late clocks · next: item 6 limited liability
- 2026-10-19 · item 6 done · calculators/limited_liability.py: delay_wd (receipt day excluded), ZERO/LIMITED/BOARD_POLICY/UNDETERMINED tiers with caps passed from the rule pack, shadow-credit and determination due dates · next: item 7 service events
- 2026-10-19 · item 7 done · calculators/service_events.py: property documents, deceased locker, deceased deposit interest (Decimal, explicit rounding), card closure (explicit late-day basis), credit information; all amounts/rates passed in · next: item 8 scenario runner
- 2026-10-19 · alignment item done · evaluator follows rules/_conventions.md: is set/is not set, unknown fact → clause false, validity at as_of, base_days/io_review_days/filing_window (as_of stands in for an unknown stop-fact anchor), PERMISSION never breaches or acts · next: DETERMINED/outputs blocked on #20; doing replay + time-travel tests while rules PR #16 is open
- 2026-10-19 · replay item done · tests/evaluator/test_replay.py: identical canonical JSON and sealed hashes across runs and shuffled inputs; later-recorded events don't change a past replay. Also fixed days_remaining on a non-working day after a working-day due date (found by hypothesis) · next: time-travel test
- 2026-10-19 · time-travel item done · tests/evaluator/test_time_travel.py: days 5/19/20 RUNNING, day 21 BREACHED, IST midnight boundary · next: scenario runner, waits on rules PR #16 (obligations not on main yet); DETERMINED/outputs waits on #20
- 2026-10-19 · runner harness done · tests/scenarios/runner.py + test_runner.py. Trial run on a local merge of rules (#16) + calendar (#14), not pushed: 12/26 scenarios pass, the other 14 only fail on DETERMINED/outputs (#20) · next: test_scenarios.py over rules/scenarios once #16 and #14 are on main
- 2026-10-19 · BLOCKED: test_scenarios.py needs rule-pack PR #16 (loader, obligations) and calendar PR #14 merged into main; DETERMINED/outputs needs the domain change in #20. Resume by merging origin/main.
- 2026-10-19 · resume · merged main (#18 engine, #14 calendar); clocks now re-export calendar.protocol.BankCalendar and a clock test runs on the real bank calendar · still BLOCKED: test_scenarios.py on rules PR #16, DETERMINED/outputs on #20
- 2026-10-19 · conventions item done · FUTURE_DATED never evaluated, tat_days_by_channel + follows_underlying_system, one action per obligation with convention codes. Local trial against rules branch: 40/72 scenarios pass; all 32 failures are DETERMINED/outputs (A1, A14, A15, A18, B5) · next: BLOCKED on #25 (DecisionRecord.outputs) and rules PR #16
- 2026-10-19 · or-conditions item done · evaluator/conditions.py: recursive-descent grammar with `or`, `and` (tighter) and parentheses; every clause still traced · next: filtered clock stops
- 2026-10-19 · filtered-stops item done · `stop_conditions` parameter: a stop event counts only if its own payload passes the condition; each candidate is traced · next: BLOCKED on #25 (DecisionRecord.outputs) and rules PR #16
