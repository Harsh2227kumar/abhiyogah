# Scenario file format

A scenario is a hand-checked timeline: a sequence of business events for one synthetic complaint, the
moment it is evaluated (`as_of`), and the exact deadlines, breaches, compensation and required actions
the engine must produce. The scenario runner (`tests/scenarios/`, engine stream) loads every
`rules/scenarios/*.yaml` except files starting with `_`, runs the evaluator and compares results
exactly. `make rules` runs it.

Scenarios are written **before** the evaluator code that satisfies them, from the report's catalogue
(Tables A–C) and formulas. Every expected number must be derivable by hand from the cited clause; write
the working in `hand_check`. Data is synthetic: no real names, account numbers, Aadhaar or PAN.

## Fields

```yaml
name: io_20d_ordinary_breach          # equals the file name without .yaml
description: one sentence             # what the timeline tests
obligation_ids: [IO-CB-2026-14-1-b]   # obligations evaluated; others in the pack are ignored
hand_check: |                         # the arithmetic, with clause citations
  ...
entity_profile:                       # the bank the complaint is against
  entity_type: COMMERCIAL_BANK        # EntityType
  outlets: 120                        # number of outlets in India (optional)
  outlets_as_on: 2025-03-31           # date of that count (optional)
  home_branch_state: MH               # ISO 3166-2:IN code without "IN-" (optional)
events:                               # in any order; each becomes a ComplaintEvent
  - type: BANK_RECEIVED               # EventType
    occurred_at: 2026-08-03T10:30:00+05:30   # business time, offset required
    recorded_at: 2026-08-03T10:31:00+05:30   # optional; defaults to occurred_at
    payload: {}                       # optional; keys named after ComplaintFacts fields become facts
    source: SYSTEM                    # optional FactSource; defaults to SYSTEM
as_of: 2026-08-25T18:00:00+05:30      # evaluation time, offset required
expect:
  deadlines:                          # every deadline computed for the listed obligations
    - {obligation_id: IO-CB-2026-14-1-b, due_date: 2026-08-23, result: BREACHED}
  breaches:
    - {obligation_id: IO-CB-2026-14-1-b, due_date: 2026-08-23, days_late: 2}
  compensation_paise: {}              # obligation_id -> integer paise owed at as_of
  required_actions:
    - {obligation_id: IO-CB-2026-14-1-b, action: REFER_TO_IO}
```

## Rules

- **Times.** `occurred_at`, `recorded_at` and `as_of` are ISO 8601 with an explicit UTC offset.
  Day arithmetic uses the Asia/Kolkata calendar date of each instant.
- **Events.** The runner assigns `event_id` = `<name>-<index>` (index from 1 in file order),
  `complaint_id` = `SCN-<name>`, and provenance `{source, actor: "scenario"}`; with `source: LLM` it
  uses `model: "scenario"` and `prompt_version: "scenario"`. Folding follows
  `abhiyogah.domain.complaint.fold_events`.
- **Deadlines.** `due_date` is the last day on which the stop event is on time. For a calendar-day
  duration of `n` days from a start date `s`, `due_date = s + n` (the start day itself is not counted).
  Working-day durations follow the obligation's calendar and are spelled out in `hand_check`.
- **`result`** is a `DecisionResult`: `NOT_APPLICABLE`, `NOT_TRIGGERED`, `INSUFFICIENT_FACTS`,
  `RUNNING`, `STOPPED_ON_TIME`, `STOPPED_LATE` or `BREACHED`. `BREACHED` means no stop event and the
  `as_of` date is after `due_date`.
- **`breaches`** lists every breach. `days_late` = stop date − `due_date` when stopped late, else
  `as_of` date − `due_date`.
- **`deadlines`, `breaches` and `required_actions`** are compared as sets: no missing and no extra
  entries. An empty list means "none". Leaving a key out also means "none".
- **`compensation_paise`** maps `obligation_id` to an integer amount in paise; obligations that owe
  nothing are left out.
- **`required_actions`** use `UPPER_SNAKE` action codes. Codes in use so far:
  `REFER_TO_IO` (A13: send the complaint to the Internal Ombudsman).
- **Obligations** named in `obligation_ids` must exist in `rules/obligations/` (rule-pack stream).
  Until they do, the runner reports the scenario as failing, not skipped.
