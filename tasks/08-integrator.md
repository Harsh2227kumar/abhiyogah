# 08 — Integrator / QA

- **Issue:** #10 (sub-issue of #1)
- **Branch:** merges stream PRs into `main`; its own one-off work goes on `agent/integrator` with PRs like any other stream
- **Phase:** from Phase 1 onward, running alongside the others
- **Depends on:** 00-foundation merged
- **Owns:** `main`, `PROGRESS.md`, `tests/e2e/`, `scripts/demo.*`, final say on merge conflicts
- **Goal:** keep `main` always green and keep every stream unblocked.

## Each session (repeat until all streams are complete)

1. List open PRs into `main`. For each one, oldest first:
   - Check that CI (`make check`) is green on its latest commit and that it has no merge conflict. If it
     conflicts, comment asking the stream to merge `main`; don't resolve other streams' code yourself.
   - Review the diff against `CLAUDE.md`: owned paths only, the hard rules, tests for new behaviour,
     commit messages that reference the stream issue.
   - PRs touching `rules/obligations/` need the owner's approval. Comment that they wait on the owner,
     and never merge them yourself.
   - Otherwise merge with a **merge commit** (not squash, not rebase), so the per-item commits and the
     task-file history stay intact.
   - If a check fails or review finds a problem: comment on the PR with exactly what failed and ask the
     stream to add it as an unchecked fix item at the top of its task file. For a
     defect found after merge, open a bug issue (template `bug`) linked to the stream issue.
2. Act on **Requests** sections in task files. If the owning stream is complete, open an issue and do
   it yourself on `agent/integrator`.
3. Never edit regulatory values in `rules/` and never change a rule's status. Rule conflicts go to
   `docs/open-questions.md` and a `rule change` issue for the owner.
4. Update `PROGRESS.md` (via your own PR, or directly on `main` for a status-only edit, which is the one
   direct push allowed): one row per stream (state, last merged PR, blocked?), plus anything that needs
   the owner. When a stream's final PR merges, check that its issue was closed.

## Checklist (one-off items)
- [x] `tests/e2e/test_demo.py`: the plan's end-to-end demo script (UPI fraud complaint → deadlines →
      time-travel past day 20 → auto-escalation → clause-cited trace), on the real start-up path
      (YAML rule pack, real calendar) with DRAFT copies from PR #16 in `tests/e2e/rulepack/`.
- [x] e2e demo, MCP step: the MCP tools return the same result to an agent as the API.
- [x] e2e demo and `scripts/demo.sh` on the real rule pack: once #16 merges, point both at
      `rules/obligations/`, keep the hand-checked assertions, and delete `tests/e2e/rulepack/`.
- [x] `scripts/demo.sh` that runs the demo against `docker compose up`.
- [x] Release checklist in `docs/release.md` (rule-pack version, calendar version, migration notes).

## Log

- 2026-10-19 · #20 domain additions (DETERMINED, cl. 14(5)/A15/A18/B-table facts, SENIOR_REVIEWED, appellant, AEPS split) · PR #23 opened; rules stream must update `failed_txn_aeps_row_ambiguous.yaml` (uses removed `AEPS`) after merge · next: release checklist
- 2026-10-19 · release checklist done · `docs/release.md` (rule-pack, calendar, migration, replay steps) · next: e2e demo and `scripts/demo.sh` wait on the platform stream (API, store, docker compose)
- 2026-10-19 · #25 `DecisionRecord.outputs` (hashed, empty by default) · PR opened · next: e2e demo and `scripts/demo.sh` still wait on the platform stream
- 2026-10-19 · e2e demo test done · `tests/e2e/test_demo.py` (B6, B5 tier, A13 breach after time travel, sweep, REFER_TO_IO, cited explain, replay) on DRAFT copies of #16 · next: `scripts/demo.sh`
- 2026-10-19 · demo.sh done · `scripts/demo.sh` + `demo.compose.yml` (demo rule pack, profile, per-run API keys) + stdlib client `demo.py`; ran against Postgres 16 in Docker with migrations (the uv image pull from ghcr is blocked here, so API ran on the host) · next: MCP step (stream 07) and real rule pack (#16)
- 2026-10-19 · e2e MCP step done · `test_demo.py` step 5: `evaluate_complaint` (now and time-travelled), `get_deadlines` and `explain_decision` equal the API's JSON; demo.py points to the MCP server · next: real rule pack (waits on #16)
- 2026-10-19 · CI runs console checks · `.github/workflows/ci.yml` adds pnpm (pinned via console/package.json packageManager) and Node 22, so `make check` runs console-check in CI · next: real rule pack (waits on #16)
- 2026-10-20 · e2e demo on the real rule pack · test and demo.sh read `rules/obligations/`; demo copies deleted; the four demo rules were identical, so B5/B6/A13 assertions are unchanged; added hand-checked A17, A2, A3, B7 and A15 results the full pack applies to the same complaint · next: foundation/integrator Requests
