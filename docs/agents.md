# Running the build with parallel agents

How the Claude Code cloud sessions that build Abhiyogah are started, resumed after usage limits reset,
and merged. The rules every agent follows are in [`CLAUDE.md`](../CLAUDE.md); the work itself is in
[`tasks/`](../tasks/).

## Streams and phases

| Phase | Stream | Task file | Branch | Starts when |
|---|---|---|---|---|
| 0 | Foundation | `tasks/00-foundation.md` | `agent/foundation` | now (alone) |
| 1 | Calendar | `tasks/01-calendar.md` | `agent/calendar` | 00 merged |
| 1 | Rule pack | `tasks/02-rule-pack.md` | `agent/rules` | 00 merged |
| 1 | Engine | `tasks/03-engine.md` | `agent/engine` | 00 merged |
| 1→ | Integrator | `tasks/08-integrator.md` | `main` | 00 merged |
| 2 | Platform | `tasks/04-platform.md` | `agent/platform` | 03 merged |
| 2 | Console | `tasks/05-console.md` | `agent/console` | 00 merged (mock), 04 for real data |
| 3 | Perception | `tasks/06-perception.md` | `agent/perception` | 04 merged |
| 3 | MCP + RegWatch | `tasks/07-mcp-regwatch.md` | `agent/mcp-regwatch` | 04 merged |

Run **at most 3–4 agents at once**. They all draw from the same usage limit, so more agents means
faster progress per hour but the limit runs out sooner, and merging becomes the bottleneck.

## Starting a stream

Start one cloud session per stream (from claude.ai/code, or ask Claude in an orchestrator session to
create it). Point it at this repository and give it this prompt, changing the two names:

> You are the **calendar** agent for Abhiyogah. Your task file is `tasks/01-calendar.md` and your
> branch is `agent/calendar`. Follow `CLAUDE.md` exactly: sync your branch with `main`, read your task
> file and its Log, then work through the unchecked items in order. Commit and push after every item.
> Stop when the stream is complete or blocked.

If the session is created with a fixed outcome branch, use `agent/<stream>` so its pushes land there.

## Resuming after the usage limit resets

Sessions stop when the limit runs out. Nothing is lost, because each item is pushed as soon as it is done.
To resume automatically, give each running stream a **recurring scheduled task** (for example hourly)
that sends its session this message:

> Resume: follow the "Start of every session" steps in `CLAUDE.md` for your stream and continue with
> the next unchecked item. If your task file's last log line is `STREAM COMPLETE`, reply "complete"
> and do nothing else.

Notes:
- Hourly is a good default. A run that fires while you are still limited just fails, and the next run
  after the reset picks the work up.
- If a run fires while the agent is still busy, the message waits for the current turn to finish.
- When a stream logs `STREAM COMPLETE`, delete its scheduled task. Then start the streams it unblocks.
- Test the resume loop on the foundation stream on day one before relying on it overnight.

## Issues, PRs and merging

- Issue #1 tracks the whole MVP; issues #2–#10 are the streams (one per task file).
- Each stream opens a PR from `agent/<stream>` into `main` every few checklist items, linking its issue
  (`Part of #N`, and `Closes #N` in the final PR). The PR template asks for the items covered, the checks
  run and any rule changes.
- The integrator (stream 08) merges a PR only when CI is green and there's no conflict, using a merge
  commit. Stream agents never merge their own PRs.
- PRs touching `rules/obligations/` wait for your review.
- Bugs, rule changes and new work go in new issues using the templates in `.github/ISSUE_TEMPLATE/`.
- Recommended GitHub setting: protect `main` (require a PR and a green CI check before merging) once the
  foundation stream has added the CI workflow.

## What the owner (you) does

1. **Review rules PRs.** Agents only write `DRAFT` obligations. Reading each obligation against its clause,
   then setting `status: IN_FORCE` and `signed_off_by`, is your job and can't be delegated.
2. **Answer open questions** in [`docs/open-questions.md`](open-questions.md).
3. **Glance at [`PROGRESS.md`](../PROGRESS.md) daily** and at blocked streams.
4. **Start the next phase** when the integrator reports the previous phase merged.
