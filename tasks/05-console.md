# 05 — Web console

- **Branch:** `agent/console`
- **Phase:** 2 (can start scaffolding once 00 is merged; real data needs 04's `openapi.json`)
- **Depends on:** 00-foundation; 04-platform for the live API
- **Owns:** `console/`
- **Goal:** the screens an Internal Ombudsman, compliance officer or auditor uses.

## Checklist

- [ ] Next.js App Router + TypeScript strict + pnpm in `console/`; lint, typecheck and test scripts; add
      them to `make check` via a `console-check` target (skipped when pnpm isn't installed).
- [ ] Generated API client from `openapi.json` (openapi-typescript). Until 04 lands, use a mock server
      built from the same types.
- [ ] Deadline board: complaints by next deadline, colour by days remaining, filter by obligation/channel.
- [ ] Complaint view: event timeline, facts with provenance badges (human/system/LLM), clocks, breaches,
      required actions.
- [ ] Decision replay: one decision record rendered as a clause-cited trace (obligation, version, anchor
      date, inputs, comparison, deadline, calendar version), plus the hash and chain status.
- [ ] Rule browser: obligations with clause, source link, verification grade and status; DRAFT and
      UNVERIFIED clearly marked.
- [ ] Time-travel control (admin) that sets `as_of` for demos.
- [ ] Indian formats throughout: ₹ with lakh/crore grouping, DD-MM-YYYY, IST.
- [ ] Write `STREAM COMPLETE`.

## Definition of done
The plan's end-to-end demo can be clicked through in the console against a local API.

## Requests

## Log
