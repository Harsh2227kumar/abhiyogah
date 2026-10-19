#!/usr/bin/env bash
# The plan's end-to-end demo against `docker compose up` (docs/plan.md, "End-to-end demo script").
#
# Starts Postgres, the API and the worker with the demo overrides (scripts/demo.compose.yml), applies
# the database migrations, then runs scripts/demo.py: a synthetic UPI fraud complaint, its deadlines
# and liability tier, a time travel past day 20 with the IO breach and referral, and the
# clause-cited explanation of the stored decision.
#
# Needs Docker with the compose plugin, python3 and a .env (cp .env.example .env). Synthetic data
# only. Stop the stack afterwards with: docker compose -f docker-compose.yml -f scripts/demo.compose.yml down
set -euo pipefail

cd "$(dirname "$0")/.."
API_URL="${ABHIYOGAH_DEMO_API_URL:-http://localhost:8000}"

if [[ ! -f .env ]]; then
  echo "No .env found. Create one first: cp .env.example .env (and set a password)." >&2
  exit 1
fi
command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

# Fresh keys for this run only; the API reads them from the environment, nothing is written to disk.
WRITER_KEY="demo-writer-$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
ADMIN_KEY="demo-admin-$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
export ABHIYOGAH_DEMO_API_KEYS="officer-demo:writer:${WRITER_KEY};admin-demo:admin:${ADMIN_KEY}"

compose() { docker compose -f docker-compose.yml -f scripts/demo.compose.yml "$@"; }

echo "==> Starting Postgres"
compose up -d --wait postgres

echo "==> Applying migrations (events, decision records, job queue)"
compose run --rm --no-deps api sh -c \
  "uv sync --frozen --no-dev && uv run --no-sync alembic upgrade head"
# procrastinate's schema can only be applied once; a second run reports it already exists.
compose run --rm --no-deps worker sh -c \
  "uv sync --frozen --no-dev && uv run --no-sync procrastinate --app=abhiyogah.worker.app.app schema --apply" \
  || echo "    (job-queue schema already present)"

echo "==> Starting the API and worker (recreated so they pick up this run's keys)"
compose up -d --force-recreate api worker

ABHIYOGAH_DEMO_API_URL="$API_URL" \
  ABHIYOGAH_DEMO_WRITER_KEY="$WRITER_KEY" \
  ABHIYOGAH_DEMO_ADMIN_KEY="$ADMIN_KEY" \
  python3 scripts/demo.py
