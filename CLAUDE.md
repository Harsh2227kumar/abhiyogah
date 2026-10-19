# Abhiyogah — instructions for every agent

Abhiyogah is an RBI complaint-compliance engine. Banks send complaint events. The engine returns
deadlines, breaches, compensation and required actions, each with a traceable, clause-cited decision
record. Read [`docs/plan.md`](docs/plan.md) for the product and architecture, and
[`docs/research/rbi-compliance-engine-gap-analysis.md`](docs/research/rbi-compliance-engine-gap-analysis.md)
for the regulation (rule catalogue Tables A–D, formulas, clock table, example obligation YAML).

Several agents build this in parallel, each in its own cloud session and branch. Sessions stop when
usage limits run out and resume later from a fresh clone, so **Git is the only memory**.

## Start of every session (including resumes)

1. Identify your stream from the prompt (for example "you are the calendar agent, `tasks/01-calendar.md`").
2. `git fetch origin && git checkout agent/<stream>` (create it from `origin/main` if missing), then
   `git merge origin/main` to pick up other streams' work. Resolve conflicts only in files you own.
3. Read this file, your task file, and the **Log** section at the bottom of your task file.
4. Check your task file's **Depends on** list. If a dependency is not merged into `main` yet, work on
   the items that don't need it, or write "BLOCKED: <reason>" in your log and stop.
5. Take the first unchecked `- [ ]` item and work on it.

## While working

- Work in small steps. After **each** checklist item: run `make check`, tick the box (`- [x]`), add one
  log line, commit, and `git push -u origin agent/<stream>`. Never end a session with unpushed work.
- Edit only the paths listed under **Owns** in your task file. If you need a change elsewhere (for
  example in `src/abhiyogah/domain/`), add a line under **Requests** in your task file describing it
  and work around it; the owner of that path picks it up.
- If an item turns out wrong or too big, split it into new unchecked items in your task file rather
  than skipping it. Don't silently drop items.
- When every item is checked, write `STREAM COMPLETE` as the last log line, push, and stop. When a
  resume prompt arrives after that, reply that the stream is complete and do nothing else.

Log line format (newest at the bottom, one line per item):
`- 2026-10-19 · item 3 done · <what changed> · next: <next item or blocker>`

## GitHub workflow: issues, commits, pull requests

- **Issues.** Tracking issue #1 has one sub-issue per stream (the number is in your task file's header).
  Anything found outside your current item goes in a **new issue** using a template from
  `.github/ISSUE_TEMPLATE/` (bug, rule change, task), never as a silent fix in an unrelated commit.
  Regulatory questions go in `docs/open-questions.md` **and** a "rule change" issue.
- **Commits.** Conventional style with scope = stream, and the stream issue in the body:
  `feat(calendar): add 2nd/4th Saturday overlay` + `Part of #3`. Use `fix:`, `test:`, `docs:`,
  `refactor:`, `chore:` as fits. One checklist item per commit where possible.
- **Pull requests.** Open a PR from `agent/<stream>` into `main` when a coherent batch of items is done
  (roughly every 2–4 items, or anything another stream is waiting for), and when the stream is complete.
  - Title: `feat(<stream>): <what the batch delivers>`.
  - Body: fill in `.github/PULL_REQUEST_TEMPLATE.md`. Write `Part of #N` for a batch and `Closes #N`
    only in the PR that completes the stream.
  - Keep pushing to the same branch while the PR is open. After it is merged, merge `origin/main` back
    into your branch and keep going; the next batch gets a new PR.
  - Never merge your own PR. The integrator (or the owner) merges when CI is green. PRs that touch
    `rules/obligations/` also need the owner's review.
- **Never** push to `main` directly (except the integrator, see `tasks/08-integrator.md`), force-push a
  shared branch, or rewrite history that has been pushed.

## Hard rules (never break these)

1. **Agents never decide the law.** Every obligation you write in `rules/` has `status: DRAFT` and no
   `signed_off_by`. Only the human owner sets `IN_FORCE` and `signed_off_by`. The registry linter must
   refuse to load an `IN_FORCE` rule that lacks `verification: PRIMARY_TEXT_READ` and `signed_off_by`.
2. **Never invent a regulatory value.** Every day count, ₹ amount, cap, TAT or effective date must come
   from the research report or a primary RBI/NPCI text, cited by clause. Copy the report's verification
   grade (P/S/U/C → `PRIMARY_TEXT_READ`/`SECONDARY_ONLY`/`UNVERIFIED`/`CONFLICTING`). If a value is
   missing or uncertain, make it a flagged parameter and add it to
   [`docs/open-questions.md`](docs/open-questions.md). Don't guess.
3. **No invented pause rules.** Clock pause semantics are "not researched". Clocks support pausing, but
   no obligation may pause until an open question is resolved by the owner.
4. **LLMs never decide breach, escalation, liability or compensation.** LLMs only perceive (classify,
   extract, translate) and draft. Their outputs are facts with provenance (model, prompt version, span),
   and any "not a complaint" or "no deficiency" result goes to human review.
5. **The deterministic core stays pure.** `domain`, `registry`, `calendar`, `clocks`, `evaluator`,
   `calculators`, `workflow` and `ledger` must not import `api`, `store`, `worker`, `perception`, `mcp`,
   `regwatch`, any database driver, HTTP client or LLM SDK. `make check` enforces this with
   import-linter.
6. **Business events, not processing events.** Fields like acknowledged/resolved/replied are set only
   by real business events (`BANK_RECEIVED`, `FINAL_REPLY_SENT`, ...), never because some processing
   step finished.
7. **Evidence is never deleted.** Events and decision records are append-only. Corrections are new
   records. No `DELETE` endpoints for evidence.
8. **No real customer data, secrets or PII** in the repo, tests or logs. Use synthetic data. Real
   Aadhaar/PAN/account numbers must never appear, even in fixtures.
9. Never skip, disable or weaken a test to get green. Never commit with `make check` failing.
10. Don't write model identifiers or session links into code, docs or commit messages.

## Conventions

**Python (3.12, `uv`).** Pydantic v2 models, `mypy --strict`, `ruff` (lint + format), `pytest`, and
`hypothesis` for calendar and clock properties. Public functions have type hints and a one-line docstring.

- **Dates and times:** a datetime is always timezone-aware. Store UTC; do day arithmetic on
  `datetime.date` in `Asia/Kolkata`. Never call `date.today()`/`datetime.now()` inside the core. Pass
  `as_of` explicitly, so evaluations are replayable and tests can time-travel.
- **Money:** integer paise (`Paise = NewType("Paise", int)`), never float. Format as ₹ only at the edges.
- **Day basis is explicit:** every duration is `CALENDAR` or `WORKING`, with `basis_status`
  (`EXPLICIT`/`INFERRED`). There is no bare `timedelta(days=n)` for a regulatory deadline.
- **IDs:** obligation IDs follow `<SOURCE>-<YEAR>-<CLAUSE>` (for example `IO-CB-2026-14-1-b`,
  `RBIOS-2026-10-1-f`, `TAT-2019-UPI-P2P`, `RBCCB-2025-72`). Event types are `UPPER_SNAKE`.
- **Errors:** raise typed exceptions from the core. No bare `except`.

**TypeScript (console).** Next.js App Router, `strict: true`, `pnpm`. The API client is generated
from `openapi.json` (`make openapi`); never hand-write API types.

## Commands

| Command | What it does |
|---|---|
| `make setup` | `uv sync` (and `pnpm install` in `console/` once it exists) |
| `make check` | ruff format check + ruff lint + mypy strict + import-linter + pytest (+ rule linter + scenario suite) |
| `make test` | pytest only |
| `make rules` | lint `rules/` and run every scenario file |
| `make openapi` | export `openapi.json` from the API and regenerate the console client |
| `make up` | `docker compose up` (Postgres + api + worker), only where Docker exists |

Tests that need Postgres are marked `@pytest.mark.db` and are skipped when `DATABASE_URL` is unset,
so the core suite always runs in a plain cloud container.

## Repository map

```
CLAUDE.md            this file
PROGRESS.md          integrator-maintained status board (other agents don't edit it)
docs/plan.md         product plan and architecture
docs/agents.md       how the parallel agents are launched, resumed and merged
docs/open-questions.md   regulatory unknowns; never resolved by assumption
docs/research/       the research report (source for rules/)
tasks/NN-*.md        one checklist per work stream: owner, branch, owned paths, items, log
src/abhiyogah/       the Python package (layout in docs/plan.md §4)
rules/               obligations/*.yaml and scenarios/*.yaml
console/             Next.js console
tests/               pytest suites
```
