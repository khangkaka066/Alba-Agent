#!/usr/bin/env bash
# Run the API and the worker directly on this Mac, without the Docker VM for them, and run agent code in the macOS sandbox
# (packages/computer-sandbox/README.md, "Local mode"). Postgres, Redis and Qdrant are still needed: by default this script expects them on
# 127.0.0.1 (start only those three with docker-compose.host-ports.yml, or point NEXUS_DB_HOST / NEXUS_REDIS_HOST / NEXUS_QDRANT_URL at
# native installs).
#
#   ./scripts/run-local.sh setup     create .venv-local and install the API requirements
#   ./scripts/run-local.sh migrate   apply database migrations
#   ./scripts/run-local.sh api       start the API on 127.0.0.1:8000
#   ./scripts/run-local.sh worker    start the worker (thread pool: macOS cannot use the default prefork pool with Celery here)
#
# It reads .env (never writes it). Docker is not touched.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
VENV="${NEXUS_LOCAL_VENV:-$ROOT/.venv-local}"
PYTHON="${NEXUS_LOCAL_PYTHON:-python3}"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "run-local.sh is for macOS: the local sandbox uses sandbox-exec." >&2
  exit 64
fi

if [ "${1:-}" = "setup" ]; then
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet -r apps/api/requirements.txt
  echo "ready: $VENV"
  exit 0
fi

[ -x "$VENV/bin/python" ] || { echo "run './scripts/run-local.sh setup' first" >&2; exit 66; }
[ -f .env ] || { echo ".env is missing; run ./scripts/quickstart.sh first" >&2; exit 66; }
eval "$("$PYTHON" scripts/load_env.py .env)"

STATE="${NEXUS_LOCAL_STATE:-$HOME/.nexus-local}"
mkdir -p "$STATE/computers" "$STATE/artifacts" "$STATE/subscriptions"
export NEXUS_DB_HOST="${NEXUS_DB_HOST:-127.0.0.1}" NEXUS_DB_NAME="${NEXUS_POSTGRES_DB:-nexus}" NEXUS_DB_USER=nexus_runtime
export NEXUS_DB_PASSWORD="${NEXUS_RUNTIME_DB_PASSWORD:?NEXUS_RUNTIME_DB_PASSWORD is missing in .env}"
export NEXUS_MIGRATION_DATABASE_URL="postgresql+asyncpg://${NEXUS_POSTGRES_USER:-nexus}:${NEXUS_POSTGRES_PASSWORD:?NEXUS_POSTGRES_PASSWORD is missing in .env}@${NEXUS_DB_HOST}:5432/${NEXUS_POSTGRES_DB:-nexus}"
export NEXUS_SETUP_DATABASE_URL="$NEXUS_MIGRATION_DATABASE_URL"
export NEXUS_REDIS_HOST="${NEXUS_REDIS_HOST:-127.0.0.1}" NEXUS_QDRANT_URL="${NEXUS_QDRANT_URL:-http://127.0.0.1:6333}"
export NEXUS_COMPUTER_ROOT="$STATE/computers" NEXUS_SANDBOX_PROVIDER=local
export NEXUS_ARTIFACTS_DIR="$STATE/artifacts" NEXUS_SUBSCRIPTIONS_DIR="$STATE/subscriptions"
export NEXUS_SANDBOX_URL="http://127.0.0.1:8000/api/v1/sandboxes" NEXUS_LOCAL_MODE=true NEXUS_RELOAD=false
export NEXUS_PLUGIN_PATCHES="$ROOT/packages/agent-runtime/nexus_plugins/local-mode.yaml"
export OTEL_SDK_DISABLED=true CREWAI_DISABLE_TELEMETRY=true ANONYMIZED_TELEMETRY=false DO_NOT_TRACK=true LITELLM_TELEMETRY_DISABLED=true LITELLM_OFFLINE_MODE=true
PACKAGES="core-schema/python core-schema/templates model-gateway agent-runtime learning-transfer computer-sandbox rag-engine mcp-hub agent-skills builtin-tools"
export PYTHONPATH="$ROOT/apps/api$(for p in $PACKAGES; do printf ':%s/packages/%s' "$ROOT" "$p"; done)"

case "${1:-}" in
  migrate)
    NEXUS_DATABASE_URL="$NEXUS_MIGRATION_DATABASE_URL" exec "$VENV/bin/alembic" -c apps/api/alembic.ini upgrade head ;;
  api)
    exec "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 --proxy-headers ;;
  worker)
    unset NEXUS_MIGRATION_DATABASE_URL NEXUS_SETUP_DATABASE_URL NEXUS_REGISTRATION_TOKEN
    exec "$VENV/bin/celery" -A app.workers.jobs:celery_app worker --loglevel="${NEXUS_WORKER_LOG_LEVEL:-INFO}" --pool=threads --concurrency="${NEXUS_WORKER_CONCURRENCY:-2}" ;;
  *)
    echo "usage: $0 setup|migrate|api|worker" >&2; exit 64 ;;
esac
