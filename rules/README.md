# The RBI rule pack

`rules/` holds the rule pack: one YAML file per obligation in `obligations/`, and timeline tests in
`scenarios/`. The Pydantic model that parses an obligation file is
[`src/abhiyogah/registry/schema.py`](../src/abhiyogah/registry/schema.py); the scenario format is in
[`scenarios/_schema.md`](scenarios/_schema.md).

Every value in this directory comes from the research report
([`docs/research/rbi-compliance-engine-gap-analysis.md`](../docs/research/rbi-compliance-engine-gap-analysis.md))
or a primary RBI/NPCI text, cited by clause. Agents never invent a value and never set `IN_FORCE`
(see the hard rules in [`CLAUDE.md`](../CLAUDE.md)).

## One obligation file

The report's example for the ordinary limb of A13 (IO Directions 2026 cl. 14(1)(b), auto-escalation
to the Internal Ombudsman within 20 days of receipt), written the way an agent must write it:

```yaml
obligation_id: IO-CB-2026-14-1-b
deontic: OBLIGATION
subject: bank
instrument: "RBI (Commercial Banks – Internal Ombudsman) Directions, 2026"
instrument_ref: "RBI/CEPD/2025-26/381; CEPD.PRD.No.S1027/13.01.019/2025-26"
clause: "14(1)(b)"
source_url: "https://sbi.bank.in/documents/53471/53742/11082026_Annexure+I-RBI+Commercial+Banks-Internal+Ombudsman+Directions+2026.pdf/7a497eab-60d3-155f-e5cd-357b80ebda24"
applies_to: {entity_type: COMMERCIAL_BANK, min_outlets: 10, outlets_as_on: 2025-03-31}
trigger: {event: OUTCOME_SET, condition: "outcome in [PARTIALLY_RESOLVED, WHOLLY_REJECTED]"}
clock: {start: BANK_RECEIVED, stop: IO_REFERRED, basis: CALENDAR, basis_status: INFERRED, tz: Asia/Kolkata}
parameters:
  max_days:
    "2026-01-14": {value: 20, reference: "cl. 14(1)(b)", verification: PRIMARY_TEXT_READ, open_question: Q4}
overridden_by: [IO-CB-2026-14-1-a]   # external RBI/NPCI/card TAT: due = TAT_deadline - 10 days
valid_from: 2026-01-14
valid_to: null
status: DRAFT
verification: PRIMARY_TEXT_READ
supersedes_note: "MD-IO 2023 (29 Dec 2023); clause mapping not verified"
tests: [io_20d_ordinary_breach.yaml, io_tat_minus_10_upi.yaml, io_fully_resolved_no_escalation.yaml]
```

Three differences from the report's text, all deliberate:

- `status: DRAFT` and no `signed_off_by`. The report shows `IN_FORCE`; only the owner may set that.
- Enum values are `UPPER_SNAKE` everywhere, so `entity_type` is `COMMERCIAL_BANK`, not
  `commercial_bank`.
- Each dated parameter value carries its own `verification` grade, and `open_question` when it is
  flagged (here Q4: "days" read as calendar days is an inference).

## Fields

| Field | Required | Meaning |
|---|---|---|
| `obligation_id` | yes | `<SOURCE>-<YEAR>-<CLAUSE>`, e.g. `IO-CB-2026-14-1-b`, `RBIOS-2026-10-1-f`, `TAT-2019-UPI-P2P`, `RBCCB-2025-72`. Unique across the pack. The file is named `<obligation_id>.yaml`. |
| `deontic` | yes | `OBLIGATION` (must), `PROHIBITION` (must not) or `PERMISSION` (may). |
| `subject` | yes | Who is bound, e.g. `bank`, `complainant`. |
| `instrument` | yes | Full title of the instrument. |
| `instrument_ref` | no | Circular / notification number(s). Leave out, and add an open question, if unknown (e.g. Q1 for RB-IOS 2026). |
| `clause` | yes | Clause or paragraph, as written in the instrument. |
| `source_url` | yes | URL of the text the clause was read in. |
| `applies_to` | yes | `entity_type` (one `EntityType` or a list), optional `min_outlets` and `outlets_as_on`. |
| `trigger` | yes | `event` (an `EventType`) and optional `condition` over `ComplaintFacts` field names. |
| `clock` | no | `start`: an `EventType`, or a `ComplaintFacts` date field when the anchor is a fact (e.g. `transaction_date_t`). `stop`: one event or a list (any one stops the clock). `basis`: `CALENDAR`/`WORKING`. `basis_status`: `EXPLICIT`/`INFERRED`. `tz`: always `Asia/Kolkata`. `pause`: must stay `null` (open question Q3). |
| `anchor` | no | `ComplaintFacts` date field that selects parameter versions (e.g. `rbi_receipt_date` for the scheme router). Defaults to the clock start. |
| `parameters` | no | `name: {effective_date: {value, reference, verification, open_question?}}`. The value in force on the anchor date is the one with the latest effective date on or before it. Day counts, ₹ amounts (in paise), caps and TATs live here, never in code. |
| `overridden_by` | no | IDs of obligations that replace this one's deadline when they apply (A13: TAT − 10 days overrides 20 days). |
| `valid_from`, `valid_to` | `valid_from` yes | Validity of this version of the obligation. `valid_to: null` means open-ended. |
| `status` | yes | `DRAFT`, `FUTURE_DATED`, `IN_FORCE`, `SUPERSEDED`, `REPEALED_BUT_SAVED`. Agents write `DRAFT` (or `FUTURE_DATED` for notified-but-not-started rules such as B10). |
| `verification` | yes | Report grade: P → `PRIMARY_TEXT_READ`, S → `SECONDARY_ONLY`, U → `UNVERIFIED`, C → `CONFLICTING`. |
| `signed_off_by` | no | Set by the owner only, together with `IN_FORCE`. |
| `supersedes_note` | no | Free text on what this replaced. |
| `tests` | no | Scenario files in `scenarios/` that exercise this obligation. |

The schema refuses an `IN_FORCE` file without `verification: PRIMARY_TEXT_READ` and `signed_off_by`.
The registry linter (`make rules`) adds the policy checks.
