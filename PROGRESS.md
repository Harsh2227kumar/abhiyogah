# Progress

Status board maintained by the integrator (`tasks/08-integrator.md`). Stream agents log their own
progress at the bottom of their task files, not here. Tracking issue: #1.

_Last updated: 2026-10-20, by the integrator (final board)_

Every stream is complete and its stream issue (#2–#9) is closed. The full rule pack
(#16) is in `main`, and the end-to-end demo (UPI fraud complaint → deadlines and liability tier →
time travel past day 20 → IO breach and referral → clause-cited trace → the same result over MCP)
runs on it in `tests/e2e/test_demo.py` and `make demo` (`scripts/dev.py`). Every rule is `DRAFT` (B10 is
`FUTURE_DATED`); none is signed off, so nothing is `IN_FORCE`.

| Stream | Issue | Task file | State | Last merged PR | Needs the owner? |
|---|---|---|---|---|---|
| 00 Foundation | #2 (closed) | `tasks/00-foundation.md` | Complete; follow-ups done by the integrator | #12 | — |
| 01 Calendar | #3 (closed) | `tasks/01-calendar.md` | Complete | #14 | Q19 holidays vs NI Act (#13); overlay files are unsourced |
| 02 Rule pack | #4 (closed) | `tasks/02-rule-pack.md` | Complete | #16 | Sign-off of every rule; open questions below |
| 03 Engine | #5 (closed) | `tasks/03-engine.md` | Complete; runs every rule-pack scenario on the real calendar | #41 | — |
| 04 Platform | #6 (closed) | `tasks/04-platform.md` | Complete, including the definition-of-done E2E on the merged pack; bug #40 open | #39 | — |
| 05 Console | #7 (closed) | `tasks/05-console.md` | Complete | #33 | — |
| 06 Perception | #8 (closed) | `tasks/06-perception.md` | Complete | #36 | Choose an LLM provider and India region (`llm` extra, `.env.example`) |
| 07 MCP + RegWatch | #9 (closed) | `tasks/07-mcp-regwatch.md` | Complete | #37 | — |
| 08 Integrator | #10 | `tasks/08-integrator.md` | Complete with the final integrator PR | #34 | Merge the final integrator PR |

## Needs the owner
- **Rule sign-off.** Every obligation in `rules/obligations/` is an agent-written `DRAFT`. Only the
  owner sets `IN_FORCE` and `signed_off_by` (CLAUDE.md hard rule 1); until then the engine's results
  are decision support on draft rules.
- **Open regulatory questions** (`docs/open-questions.md`), each with a rule-change issue: Q14 external-TAT
  anchor (#15), Q15 RB-IOS 2021 commencement (#17), Q16 A15 limb mapping (#19), Q17 CRPC reply
  wording (#21), Q18 Ombudsman-stage extensions (#22), Q20 cl. 14(5)(c)-(e) IO routing (#26), Q21 complaint
  category taxonomy (#35), and Q19 the bank calendar question (#13); the last three were added as
  Q19-Q21 from the calendar, platform and perception Requests. Clock pause rules stay unresearched,
  so no obligation pauses (hard rule 3).
- **Bank holiday overlay.** `data/calendars/` files are unsourced (`source_url: null`), so working-day
  deadlines use Sundays, 2nd/4th Saturdays and the `holidays` package only.
- **Run `make demo` (Windows: `.\make demo`) once with normal Docker access.** It was verified against Postgres 16 with
  the migrations and API run on the host; the `ghcr.io/astral-sh/uv` image could not be pulled from
  the build sandbox.

## Open follow-ups (not blocking)
- #40: the worker appends an unchanged decision record each day for obligations anchored on `as_of`
  (A3 before RBI receipt, the A15 review check).
- Requests still open in task files: an API service layer for MCP (07 → 04), `ReviewKind.MANUAL_PERCEPTION`
  and perception in the worker (06 → 04), and a `REVIEW_DECIDED` event (04 → domain).
