# Open regulatory questions

These are unknowns the research could not settle. Code must keep each one **configurable and flagged**,
never resolved by assumption. Only the owner closes a question, by writing the answer, the source and
the date below it. Agents may add new questions and link obligation IDs.

| # | Question | Why it matters | Affects | Status |
|---|---|---|---|---|
| Q1 | Final RB-IOS 2026 circular number | Citation in every RB-IOS obligation | A1–A11 | Open |
| Q2 | NBFC / SFB / PB / PPI / CIC variants of the IO Directions (the often-quoted 25-day CIC escalation is unverified) | Applicability profiles beyond commercial banks | A12, A13 | Open |
| Q3 | Clock pause semantics: does the 30-day RB-IOS / IO clock stop while waiting for customer documents? | Every complaint clock | A2, A13, A17 | Open (no obligation may pause) |
| Q4 | "Days" in RB-IOS and IO Directions: calendar days is an inference | Every deadline marked `basis_status: INFERRED` | A2–A8, A13, A17, B7 | Open |
| Q5 | Illegible failed-transaction TAT rows (CNP T+5, AePS beneficiary T+1, NACH-revoked) | B2 values are `UNVERIFIED` | B2: TAT-2019-ILLEGIBLE-ROWS (`tat_days_by_channel`, `compensation_per_day_paise`); TAT-2019-FAILED-TXN (NACH compensation also covers row 7b) | Open |
| Q6 | Claimed switch of TATs to working days from 1 Jan 2021 (single weak source; conflicts with RBI's definition of T) | Would change every B1 deadline | B1, B3: TAT-2019-FAILED-TXN, TAT-2019-ILLEGIBLE-ROWS (basis kept CALENDAR/EXPLICIT) | Open (treat as false) |
| Q7 | Final figures of the 1 Jan 2027 fraudulent e-transaction regime (draft: ≤ ₹50,000 compensated up to ₹25,000 or 85%; 30-day resolution) | B10 must stay `FUTURE_DATED` + `UNVERIFIED`; also how "up to ₹25,000 or 85%" combines, the day basis and the stop event | B10: RBCCB-2026-AMEND3-FRAUD (`max_days`, `small_value_ceiling_paise`, `compensation_cap_paise`, `compensation_percent`) | Open |
| Q8 | NPCI dispute stage TATs (credit adjustment, chargeback, re-presentment) | External TAT feeding A2 and A13 | B11 | Open |
| Q9 | Where the 2019 TAT circular sits in the 2025 consolidated directions | Citation for B1 | B1: TAT-2019-FAILED-TXN (`tat_days_by_channel`) | Open |
| Q10 | Credit-information complaint day basis (calendar vs working) | B12 deadline | B12 | Open (conflicting) |
| Q11 | Financial-statements complaint disclosure table | Reporting stream | D9 | Open |
| Q12 | DPDP Rule 7 start date (13 Nov 2026 vs ~13 May 2027) | Breach notification clock | D4 | Open (conflicting) |
| Q13 | State-wise bank holiday lists (NI Act) for each year in use | Calendar overlay data | calendar | Open |
| Q14 | Anchor of an external RBI/NPCI/card-network TAT: the engine counts `external_tat_days` from the bank's receipt of the complaint (an inference); it may instead run from the transaction or dispute date. Also: what applies when the TAT leaves fewer than 10 days for the IO | A13 limb (a) due date `receipt + TAT − 10`, and A2's `max(30, TAT)` | IO-CB-2026-14-1-a (`io_review_days`), RBIOS-2026-10-1-f | Open (#15) |
| Q15 | Commencement date of RB-IOS 2021 (12 Nov 2021 from background knowledge; the report gives none) | First effective date of the 2021 scheme in the A1 router and the A3 2021 comparator; earlier RBI receipts get no scheme | RBIOS-2026-20-2 (`scheme`), RBIOS-2026-10-1-g | Open (#17) |
| Q16 | IO Directions cl. 14(3)–(4): which limb (SOP, no same-unit closure, senior review) sits in which sub-clause, and so which one applies only from 30 Jun 2026; and what rank "a fairly senior level" means | Effective date and evidence needed for the A15 checks | IO-CB-2026-14-3-4-closure, IO-CB-2026-14-3-4-review | Open (#19) |
| Q17 | Exact CRPC postal and email address, and any prescribed wording, that a cl. 14(11)–(12) reply must carry; and which element sits in 14(11) vs 14(12) | Reply QA can only check that each element is present, not that it is correct | IO-CB-2026-14-11-12 (`required_elements`) | Open (#21) |

## Answers

_(owner: add `### Q<n>` with the answer, the source and the date)_
