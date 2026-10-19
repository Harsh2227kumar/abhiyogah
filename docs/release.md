# Release checklist

A release is a tag on `main` (`vYYYY.MM.DD`, or `vYYYY.MM.DD.N` for a second one on the same day).
It ships three things that change on their own schedules: the code, the **rule pack** (`rules/`)
and the **bank calendar** (`data/calendars/` plus the `holidays` package). A decision record already
names the versions it used (`obligation_version`, `calendar_version`), so a release must make those
versions traceable to a tag and must never change what an old record replays to.

The integrator runs this list. Items marked **owner** need the human owner; agents never tick them.

## 1. `main` is ready

- [ ] Every PR meant for this release is merged, and no open PR into `main` is half-way through a
      batch that the release depends on.
- [ ] CI is green on the commit being tagged, and `make check` passes in a fresh clone
      (`make setup && make check`).
- [ ] `PROGRESS.md` is current. Any stream marked blocked is named in the release notes.

## 2. Rule pack

- [ ] `make rules` passes: the linter loads every obligation and every scenario file passes.
- [ ] No obligation is `IN_FORCE` without `verification: PRIMARY_TEXT_READ` and `signed_off_by`
      (the linter enforces this; check that the check ran, not just that CI is green).
- [ ] **Owner:** every status change to `IN_FORCE`, `SUPERSEDED` or `REPEALED_BUT_SAVED` since the
      last release was made by the owner, in a PR the owner approved.
- [ ] Release notes list obligations added, changed (by ID, with the clause), and changed in status,
      using `git diff <last-tag>..HEAD -- rules/obligations/`.
- [ ] Each changed regulatory value cites its clause and carries the report's verification grade.
      Nothing was edited to make a scenario pass.
- [ ] `docs/open-questions.md`: the notes list the questions still open that affect rules in this
      release, so a bank knows which parameters are flagged.
- [ ] Rule-pack version: the notes record the tag and, for each changed obligation, its
      `obligation_version` (`sha256:` of the obligation's canonical JSON, as written in decision
      records). An unchanged obligation keeps its hash across releases.

## 3. Calendar

- [ ] Overlay files exist for every state the profiles use, for the current year and the next one
      (deadlines near December cross into January).
- [ ] Unsourced overlay files (`Overlay.unsourced()`, `source_url: null`) are listed in the notes.
      While any remain, working-day deadlines for those states are not authoritative.
- [ ] The `holidays` package version in `uv.lock` is the one tested. A change to it, or to any
      overlay file, changes `calendar_version`; the notes record the old and new values.

## 4. Data and migrations

- [ ] Migrations are forward-only and additive. Events and decision records are append-only
      (hard rule 7): no migration drops, truncates or rewrites evidence tables or columns.
- [ ] Each migration is listed in the notes with what it changes and whether it needs a backfill.
      A backfill writes new records; it never edits old ones.
- [ ] A migration that renames an enum value used in stored events (for example the `Channel.AEPS`
      split in #20) says how old events are read: old values stay readable, and corrections arrive as
      new `FACTS_RECORDED` events.
- [ ] The decision-record hash chain verifies before and after migrating (`verify_chain`).

## 5. Replay and re-evaluation

- [ ] Replaying a sample of stored decision records at their own `as_of`, rule version and calendar
      version gives byte-identical records.
- [ ] Complaints in flight are re-evaluated under the new pack (plan §5 step 7). Differences from
      the previous evaluation are listed for the owner. New records are appended; old ones stay.

## 6. Tag and publish

- [ ] Tag `main` with an annotated tag whose message is the release notes (code changes, rule-pack
      changes, calendar version, migrations, open questions).
- [ ] `openapi.json` and the console client were regenerated (`make openapi`) if the API changed.
- [ ] **Owner:** approves the release notes before the tag is shared with any bank.
