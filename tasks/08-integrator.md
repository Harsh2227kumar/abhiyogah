# 08 — Integrator / QA

- **Branch:** works on `main` directly (the only agent allowed to push to `main`)
- **Phase:** from Phase 1 onward, running alongside the others
- **Depends on:** 00-foundation merged
- **Owns:** `main`, `PROGRESS.md`, `tests/e2e/`, `scripts/demo.*`, final say on merge conflicts
- **Goal:** keep `main` always green and keep every stream unblocked.

## Each session (repeat until all streams are complete)

1. `git fetch origin`. For each `origin/agent/*` branch with new commits:
   - check it out locally, merge `origin/main` into it, run `make check`;
   - if green: merge it into `main` with `git merge --no-ff`, run `make check` again, push `main`;
   - if red: don't merge. Add an unchecked item describing the failure to the top of that stream's task
     file **on that stream's branch** (commit as integrator), so the stream agent fixes it next.
2. Act on **Requests** sections: if a request targets a path whose owning stream is complete, implement
   it yourself on `main`.
3. Never edit regulatory values in `rules/` and never change a rule's status. Rule conflicts go to
   `docs/open-questions.md` for the owner.
4. Update `PROGRESS.md`: one row per stream (state, last merge, blocked?), plus anything that needs the owner.

## Checklist (one-off items)
- [ ] `tests/e2e/test_demo.py`: the plan's end-to-end demo script (UPI fraud complaint → deadlines →
      time-travel past day 20 → auto-escalation → clause-cited trace → MCP returns the same result).
- [ ] `scripts/demo.sh` that runs the demo against `docker compose up`.
- [ ] Release checklist in `docs/release.md` (rule-pack version, calendar version, migration notes).

## Log
