# 02 — Rule pack v0.1 and scenarios

- **Issue:** #4 (sub-issue of #1)
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
- [x] `registry/loader.py`: load every `rules/obligations/*.yaml` into the schema models; a duplicate ID is an error.
- [x] `registry/resolve.py`: `parameter_at(obligation, name, anchor_date)` returns the value whose effective
      date is the latest ≤ anchor (OpenFisca-style), or raises `NoParameterInForce`.
- [x] `registry/lint.py` + `python -m abhiyogah.registry.lint` wired into `make rules`. Errors for: missing
      clause or source_url; IN_FORCE without PRIMARY_TEXT_READ and signed_off_by; overlapping validity
      periods for the same obligation; `overridden_by` pointing to an unknown ID; a test file that doesn't
      exist; a non-null `pause` (pause semantics not researched); parameters with no reference.

### Obligations (one file each, with ≥ 2 scenarios: one compliant, one breach, plus edge cases)
- [x] A1 scheme router (RB-IOS 2021 vs 2026 by RBI receipt date, cl. 20(2))
- [x] A2 30-day bank reply / max(30, external TAT) (RB-IOS cl. 10(1)(f))
- [x] A3 90-day RBI filing window (cl. 10(1)(g)), including the 2021 comparator
- [x] A13 IO auto-escalation: 20 days (14(1)(b)) and TAT − 10 days (14(1)(a))
- [x] A14 three-state outcome (14(2))
- [x] A15 no same-unit closure and senior review (14(3)–(4)): obligation files
- [ ] A15 scenarios (≥ 2 per limb), once the A15 facts requested below exist in `ComplaintFacts`
- [x] A17 final decision within 30 days (14(9))
- [x] A18 mandatory reply content (14(11)–(12)): as a checklist obligation consumed by reply QA
- [ ] A18 scenarios (complete reply, missing elements, IO-upheld statement), once `reply_elements` and `io_upheld` exist
- [x] B1 failed-transaction TATs: one parameter table covering every verified channel row, plus ₹100/day
- [x] B2 illegible rows: encoded but `verification: UNVERIFIED`
- [x] B5 limited liability tiers and account-type caps (paras 67–71, Tables 1–2)
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

Tracked together in issue #20.

- `src/abhiyogah/domain/decision.py` (foundation/integrator): add `DecisionResult.DETERMINED` for obligations without a clock that produce an output (A1 scheme, A14/A15/A18 checks, B5 tier). Scenarios already use it; `tests/registry/test_scenario_files.py` accepts it until it exists. See `rules/obligations/_conventions.md`.
- `src/abhiyogah/domain/complaint.py` (foundation/integrator): add a `ComplaintFacts` fact for the IO cl. 14(5) exclusion category (for example `exclusion_category: Fact[str]` with values `14_5_a` … `14_5_e`). Without it, A14 cannot exempt out-of-purview complaints (cl. 14(5)(c)–(e)) and A16 cannot be encoded.
- `src/abhiyogah/domain/` (foundation/integrator), for A15: facts `handling_unit: Fact[str]` and `closing_unit: Fact[str]` (set from payloads), and an event `SENIOR_REVIEWED` that sets `senior_review_date: Fact[date]`. The A15 scenarios wait on these.
- `src/abhiyogah/domain/` (foundation/integrator), for A18: facts `reply_elements: Fact[list[str]]` (element codes found in the sent reply, from reply QA or a human) and `io_upheld: Fact[bool]` (from the `IO_DECIDED` payload). The A18 scenarios wait on these.
- `src/abhiyogah/domain/` (foundation/integrator), for B1–B7: a fact `issue_type` (values `FAILED_TRANSACTION`, `UNAUTHORISED_TRANSACTION`, open to more) so failed-transaction and limited-liability rules do not both trigger on every transaction complaint; and split `Channel.AEPS` into `AEPS_MERCHANT` (T+5, B1) and `AEPS_BENEFICIARY` (T+1, B2), since the annex has two AePS rows.
- `src/abhiyogah/domain/` (foundation/integrator), for B5: a fact `liability_fault` (values `BANK`, `THIRD_PARTY`, `CUSTOMER`), set by a human (never by an LLM) on the limited-liability case.

## Log
- 2026-10-19 · item 1 done · registry/loader.py + errors.py: load rules/obligations/*.yaml, duplicate ID is an error; tests/registry/test_loader.py · next: registry/resolve.py
- 2026-10-19 · item 2 done · registry/resolve.py parameter_at (latest effective ≤ anchor, else NoParameterInForce) with property test · next: registry/lint.py
- 2026-10-19 · A13 done (ahead of lint, because the linter refuses the foundation scenario until IO-CB-2026-14-1-b exists) · IO-CB-2026-14-1-a/-b with mutually exclusive limbs, 8 scenarios, `expect.results` key, rules/obligations/_conventions.md, Q14, scenario consistency test · next: registry/lint.py
- 2026-10-19 · item 3 done · registry/lint.py (citations, IN_FORCE gate, pause, references, file name, duplicates/overlap, overridden_by, test files, scenario obligation IDs); `make rules` runs it · next: A1 scheme router
- 2026-10-19 · A1 done · RBIOS-2026-20-2 router (`scheme` anchored at rbi_receipt_date; 2021 start UNVERIFIED, Q15/#17), 3 scenarios, `expect.outputs` + DETERMINED (requested from domain), validity/anchor conventions · next: A2
- 2026-10-19 · A2 done · RBIOS-2026-10-1-f as complainant PERMISSION (`base_days` 30, max with external TAT, output `escalation_open`), 5 scenarios; PERMISSION never breaches (convention + test) · next: A3
- 2026-10-19 · A3 done · RBIOS-2026-10-1-g PERMISSION with `base_days` + `filing_window` dated by rbi_receipt_date (2026: 90 days P; 2021: 1 year S, Q15), output `filed_in_time`, 5 scenarios incl. the 2025-receipt time-bar case · next: A14
- 2026-10-19 · A14 done · IO-CB-2026-14-2 check obligation (`allowed_outcomes` from 2026-06-30 at final_reply_date, output `classified_at_closure`, action SET_OUTCOME), 5 scenarios; anchor before first effective date → NOT_APPLICABLE; requested an exclusion-category fact for cl. 14(5) · next: A15
- 2026-10-19 · A15 obligation files done · IO-CB-2026-14-3-4-closure (PROHIBITION) and -review (check obligations, outputs + SENIOR_REVIEW action); clause split and 30 Jun date flagged as Q16; facts requested; scenarios split into a new item · next: A17
- 2026-10-19 · A17 done · IO-CB-2026-14-9 (30 calendar days, inferred, no pause), action SEND_FINAL_DECISION, 4 scenarios incl. combined A13+A17 and INFO_REQUESTED-does-not-pause · next: A18
- 2026-10-19 · A18 obligation file done · IO-CB-2026-14-11-12 checklist (`required_elements`, `required_elements_if_io_upheld`), outputs reply_complete/missing_elements, action SEND_CORRECTED_REPLY; Q17; facts requested; scenarios split into a new item · next: B1
- 2026-10-19 · B1 done · TAT-2019-FAILED-TXN with `tat_days_by_channel` (verified rows), `follows_underlying_system`, ₹100/day as 10000 paise; 5 scenarios; requested `issue_type` fact and AEPS channel split (#20) · next: B2
- 2026-10-19 · B2 done · TAT-2019-ILLEGIBLE-ROWS (CNP T+5, AePS beneficiary T+1, ₹100/day) all UNVERIFIED/Q5, 2 scenarios; Q5/Q6/Q9 now name obligation IDs · next: B5
- 2026-10-19 · B5 done · RBCCB-2025-67-71 determination (3/7 working-day tiers, Table 2 caps in paise, outputs delay_working_days/liability_tier/customer_liability_paise), 6 scenarios on MH June 2026 dates (holiday-free assumption stated, Q13); requested `liability_fault` fact (#20) · next: B6
