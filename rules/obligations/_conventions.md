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

## Deadline building blocks

The clock spec gives the start, stop events, day basis and basis status. The parameters present on
the obligation select how the due date is computed from the start date `s` (an IST date):

| Parameters | Due date | Used by |
|---|---|---|
| `max_days` | `s + max_days` (in the clock's basis) | most clocks |
| `base_days` | `s + max(base_days, external_tat_days)`, or `s + base_days` when no external TAT is known | A2 |
| `io_review_days` | `s + external_tat_days − io_review_days` | A13 limb (a) |

`external_tat_days` is the `ComplaintFacts` input supplied by the bank. It is counted from the bank's
receipt of the complaint; that anchor is an inference recorded as open question Q14.

Other parameters (amounts, caps, rates) are inputs to calculators and are named after what they
hold, with units in the name: `_days`, `_paise`, `_percent`.

## Results and required actions

- A scenario's `expect.results` maps each obligation in `obligation_ids` to its `DecisionResult`,
  including results that have no deadline (`NOT_TRIGGERED`, `NOT_APPLICABLE`, `INSUFFICIENT_FACTS`).
  `expect.deadlines` lists only computed deadlines.
- A required action is emitted while the obligation is triggered and its clock has not stopped
  (`RUNNING` or `BREACHED`), and never after the stop event.

| Action code | Obligation | Meaning |
|---|---|---|
| `REFER_TO_IO` | A13 (both limbs) | Send the complaint to the Internal Ombudsman |

## Scenario inputs that are not regulatory values

Some scenarios need an input that the bank supplies, such as `external_tat_days`. Such inputs are
synthetic, chosen only to exercise the arithmetic, and the `hand_check` says so. They are never
presented as the value of a real RBI, NPCI or card-network TAT.
