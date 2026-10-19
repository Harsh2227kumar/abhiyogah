# Abhiyogah console

Next.js (App Router, TypeScript strict, pnpm) console for Internal Ombudsman offices, compliance
officers and auditors.

```sh
pnpm install
ABHIYOGAH_API_URL=http://localhost:8000 ABHIYOGAH_API_KEY=<key> pnpm dev   # http://localhost:3000
pnpm check      # eslint + tsc --noEmit + vitest (also run by `make check` via `console-check`)
```

All data shown is synthetic.

## Engine API

The console talks to the engine only through `lib/api` (`getApi()`, server side). Its types in
`lib/api/generated/schema.ts` are generated from the repository's `openapi.json` by
openapi-typescript (`make openapi`); never write API types by hand. A test fails if the generated
file drifts from `openapi.json`.

| Variable | Meaning |
|---|---|
| `ABHIYOGAH_API_URL` | Base URL of the engine API, e.g. `http://localhost:8000` |
| `ABHIYOGAH_API_KEY` | Key sent as `X-API-Key`. Time travel (`as_of`) needs an ADMIN key; the API refuses it otherwise. |
| `ABHIYOGAH_TIME_TRAVEL` | `off` hides the admin time-travel control |

## Local demo (synthetic data)

From the repository root, start the API without Postgres (in-memory store; keys are at least 16
characters):

```sh
export ABHIYOGAH_API_KEYS="demo-admin:ADMIN:demo-admin-key-synthetic;demo-writer:WRITER:demo-writer-key-synthetic"
export ABHIYOGAH_PROFILE='{"entity_type":"COMMERCIAL_BANK","outlets":120,"outlets_as_on":"2025-03-31","home_branch_state":"MH"}'
export ABHIYOGAH_RULES_DIR=rules/obligations   # the DRAFT rule pack
uv run uvicorn abhiyogah.api.app:app --port 8000
```

Then, in `console/`:

```sh
ABHIYOGAH_API_URL=http://localhost:8000 ABHIYOGAH_WRITER_KEY=demo-writer-key-synthetic node scripts/seed-demo.mjs
ABHIYOGAH_API_URL=http://localhost:8000 ABHIYOGAH_API_KEY=demo-admin-key-synthetic pnpm dev
```

`seed-demo.mjs` posts five synthetic complaints dated relative to today (IST). On the board,
CMP-DEMO-0101's 20-day IO clock (`IO-CB-2026-14-1-b`) is due in two days; press "+1 day" three
times and the complaint view shows the breach and the REFER_TO_IO action, and the decision trace
shows the clause, parameters, condition trace, hash and chain status.

## Tests

`pnpm check` runs eslint, `tsc --noEmit` and vitest. Page tests replay real API responses from
`test/fixtures/api.json` through the real HTTP client. To refresh them, seed a fresh API as above
and run `ABHIYOGAH_API_URL=... ABHIYOGAH_API_KEY=<admin key> node scripts/record-fixtures.mjs`.
