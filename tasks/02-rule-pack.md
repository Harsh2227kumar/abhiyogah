# 02 — Rule pack v0.1 and scenarios

- **Branch:** `agent/rules`
- **Phase:** 1 (parallel with 01, 03)
- **Depends on:** 00-foundation merged (schema and scenario format)
- **Owns:** `rules/obligations/`, `rules/scenarios/`, `src/abhiyogah/registry/` (except `schema.py`),
  `tests/registry/`, `docs/open-questions.md`
- **Goal:** encode the v0.1 obligations as reviewed DRAFT YAML, each with scenario timelines whose
  expected answers are **hand-computed from the regulation**, before the evaluator exists.

Source for every value: `docs/research/rbi-compliance-engine-gap-analysis.md` Tables A–C, the
"Formulas an engine can execute today" section and the clock table. Cite the clause; copy its
verification grade. **All files `status: DRAFT`, no `signed_off_by`.**

## Checklist

### Registry code
- [ ] `registry/loader.py`: load every `rules/obligations/*.yaml` into the schema models; a duplicate ID is an error.
- [ ] `registry/resolve.py`: `parameter_at(obligation, name, anchor_date)` returns the value whose effective
      date is the latest ≤ anchor (OpenFisca-style), or raises `NoParameterInForce`.
- [ ] `registry/lint.py` + `python -m abhiyogah.registry.lint` wired into `make rules`. Errors for: missing
      clause or source_url; IN_FORCE without PRIMARY_TEXT_READ and signed_off_by; overlapping validity
      periods for the same obligation; `overridden_by` pointing to an unknown ID; a test file that doesn't
      exist; a non-null `pause` (pause semantics not researched); parameters with no reference.

### Obligations (one file each, with ≥ 2 scenarios: one compliant, one breach, plus edge cases)
- [ ] A1 scheme router (RB-IOS 2021 vs 2026 by RBI receipt date, cl. 20(2))
- [ ] A2 30-day bank reply / max(30, external TAT) (RB-IOS cl. 10(1)(f))
- [ ] A3 90-day RBI filing window (cl. 10(1)(g)), including the 2021 comparator
- [ ] A13 IO auto-escalation: 20 days (14(1)(b)) and TAT − 10 days (14(1)(a))
- [ ] A14 three-state outcome (14(2))
- [ ] A15 no same-unit closure and senior review (14(3)–(4))
- [ ] A17 final decision within 30 days (14(9))
- [ ] A18 mandatory reply content (14(11)–(12)): as a checklist obligation consumed by reply QA
- [ ] B1 failed-transaction TATs: one parameter table covering every verified channel row, plus ₹100/day
- [ ] B2 illegible rows: encoded but `verification: UNVERIFIED`
- [ ] B5 limited liability tiers and account-type caps (paras 67–71, Tables 1–2)
- [ ] B6 shadow credit in 10 working days (para 72)
- [ ] B7 liability determination within 90 days (para 73)
- [ ] B10 1 Jan 2027 fraud regime: `FUTURE_DATED`, every draft figure `UNVERIFIED`
- [ ] A5, A6, A7, A8 RBI Ombudsman-stage clocks

### Open questions
- [ ] Keep `docs/open-questions.md` current: every flagged parameter links to its obligation ID.
- [ ] Write `STREAM COMPLETE`.

## Definition of done
`make rules` lints every file clean; each scenario's expected values include a short comment showing the
hand calculation; the owner can review each obligation against its clause in under five minutes.

## Requests

## Log
