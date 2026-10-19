# Rule-pack conventions (rules stream)

How the obligation files in this folder use the schema fields whose meaning the schema leaves open:
trigger conditions, how a deadline is derived from the parameters, and the action codes. The engine
stream implements these as the "small set of Python clock and condition building blocks" from
`docs/plan.md` §6. If something here needs a schema change, it goes under **Requests** in
`tasks/02-rule-pack.md`.

## Trigger conditions

`trigger.condition` is one or more clauses joined by ` and ` (no `or`, no brackets). Each clause names a
`ComplaintFacts` field and compares its known value:

| Clause | True when |
|---|---|
| `<fact> in [A, B]` | the fact is known and its value is one of the listed values |
| `<fact> is set` | the fact is known |
| `<fact> is not set` | the fact is unknown |

A fact the condition needs that is unknown makes an `in` clause false; it never defaults to a value.
Each clause is one `ConditionTrace` entry in the decision record.

Limbs of one clause that override each other (A13: 20 days vs TAT − 10 days) use mutually exclusive
conditions (`external_tat_days is set` / `is not set`) **and** list the override in `overridden_by`, so
exactly one limb produces a deadline and the trace still names the override.

Facts the rule pack needs that `ComplaintFacts` does not have yet are requested in issue #20
(`issue_type`, the A15 and A18 facts, the cl. 14(5) exclusion category). Scenarios already set
them in payloads; until they exist those payload keys are ignored by folding.

## Validity and anchor dates

- `valid_from` / `valid_to` are checked against the `as_of` date: is this rule in the pack at the
  moment of evaluation? Outside them the result is `NOT_APPLICABLE`.
- Parameter versions are chosen at the **anchor date**: the `anchor` fact when the obligation names
  one (A1 uses `rbi_receipt_date`), else the clock start date. An obligation with neither resolves
  at the `as_of` date. An anchor date before a parameter's first effective date means the rule did
  not apply then: the result is `NOT_APPLICABLE`, and no earlier value is assumed. An anchor fact
  that is unknown (and has no stated stand-in) gives `INSUFFICIENT_FACTS`.

## Deadline building blocks

The clock spec gives the start, stop events, day basis and basis status. The parameters present on
the obligation select how the due date is computed from the start date `s` (an IST date):

| Parameters | Due date | Used by |
|---|---|---|
| `max_days` | `s + max_days` (in the clock's basis) | most clocks |
| `base_days` | `s + max(base_days, external_tat_days)`, or `s + base_days` when no external TAT is known | A2 |
| `io_review_days` | `s + external_tat_days − io_review_days` | A13 limb (a) |
| `tat_days_by_channel` | `T + table[channel]`, T = `transaction_date_t`; a channel not in the table (or listed in `follows_underlying_system`) gives `INSUFFICIENT_FACTS` | B1, B2 |
| `base_days` + `filing_window` | `max(s + max(base_days, external_tat_days), last_bank_communication_date) + filing_window` | A3 |

`filing_window` is `{days: n}` or `{years: n}`; adding years keeps the month and day (29 Feb is not
reached by any scenario and has no rule yet). A3's anchor is `rbi_receipt_date`; until RBI has
received the complaint, the `as_of` date stands in for it ("if it were filed now").

`external_tat_days` is the `ComplaintFacts` input supplied by the bank. It is counted from the bank's
receipt of the complaint; that anchor is an inference recorded as open question Q14.

Compensation per day of delay (`compensation_per_day_paise`, B1/B2): owed =
`per_day × days_late`, where days_late runs to the stop date, or to the `as_of` date while the clock
is `BREACHED` (accrued so far). Nothing is owed for `RUNNING` or `STOPPED_ON_TIME`.

Other parameters (amounts, caps, rates) are inputs to calculators and are named after what they
hold, with units in the name: `_days`, `_paise`, `_percent`.

## Results, outputs and required actions

- Obligations without a clock (the scheme router, classifications, checklists) end in
  `DETERMINED` when they produce an output. `DETERMINED` is not yet a `DecisionResult` member; it is
  requested under **Requests** in `tasks/02-rule-pack.md`.
- A scenario's `expect.outputs` maps an obligation ID to the values it determined, by output name:

  | Obligation | Output | Values |
  |---|---|---|
  | A1 `RBIOS-2026-20-2` | `scheme` | the `scheme` parameter in force at `rbi_receipt_date`: `RB-IOS-2021` or `RB-IOS-2026` |
  | A3 `RBIOS-2026-10-1-g` | `filed_in_time` | once `rbi_receipt_date` is known: `true` for `STOPPED_ON_TIME`, `false` for `STOPPED_LATE`; absent before filing |
  | A14 `IO-CB-2026-14-2` | `classified_at_closure` | `true` when `outcome` is set and `outcome_date` ≤ `final_reply_date` |
  | A15 `IO-CB-2026-14-3-4-closure` | `closed_by_other_unit` | `true` when `closing_unit` ≠ `handling_unit` (both needed, else `INSUFFICIENT_FACTS`) |
  | A15 `IO-CB-2026-14-3-4-review` | `senior_reviewed_before_io` | `true` when `senior_review_date` is set and, if `io_referred_date` is set, ≤ it |
  | A18 `IO-CB-2026-14-11-12` | `reply_complete`, `missing_elements` | `missing_elements` = `required_elements` (+ `required_elements_if_io_upheld` when `io_upheld` is true) not in `reply_elements`, sorted; `reply_complete` = it is empty |
  | A2 `RBIOS-2026-10-1-f` | `escalation_open` | `true` when the clock is `BREACHED` or `STOPPED_LATE` (no reply by the due date) or `customer_dissatisfied_date` is set, else `false` |

  Clock obligations may also have outputs; `DETERMINED` ones must.
- **Check obligations** have no clock: they test the complaint's state when the trigger fires (A14,
  A15, A18). They end `DETERMINED` with a boolean output naming what was checked. A failed check has
  no `Breach` entry (a breach needs a due date). It shows as the output `false` plus a required action
  while the failure can still be fixed.
- `deontic: PERMISSION` (a right of the complainant, such as A2 and A3) never produces a breach or a
  required action. Its clock result says whether the window has lapsed; what that means comes out as
  an output (`escalation_open`).

- A scenario's `expect.results` maps each obligation in `obligation_ids` to its `DecisionResult`,
  including results that have no deadline (`NOT_TRIGGERED`, `NOT_APPLICABLE`, `INSUFFICIENT_FACTS`).
  `expect.deadlines` lists only computed deadlines.
- A required action is emitted while the obligation is triggered and its clock has not stopped
  (`RUNNING` or `BREACHED`), and never after the stop event.

| Action code | Obligation | Meaning |
|---|---|---|
| `REFER_TO_IO` | A13 (both limbs) | Send the complaint to the Internal Ombudsman |
| `SENIOR_REVIEW` | A15 review limb | Have the outcome reviewed at a senior level before the IO referral (while not yet referred) |
| `SEND_FINAL_DECISION` | A17 | Communicate the bank's final decision to the complainant |
| `SEND_CORRECTED_REPLY` | A18 | Send the complainant a reply carrying the missing cl. 14(11)–(12) elements |
| `REVERSE_TRANSACTION` | B1, B2 | Complete the failed-transaction reversal (compensation keeps accruing) |
| `SET_OUTCOME` | A14 | Record one of the three cl. 14(2) outcomes for a complaint already replied to |

## Scenario inputs that are not regulatory values

Some scenarios need an input that the bank supplies, such as `external_tat_days`. Such inputs are
synthetic, chosen only to exercise the arithmetic, and the `hand_check` says so. They are never
presented as the value of a real RBI, NPCI or card-network TAT.
