#!/bin/sh
set -eu

case "${1:-api}" in
  api)
    export NEXUS_DATABASE_URL="${NEXUS_MIGRATION_DATABASE_URL:?NEXUS_MIGRATION_DATABASE_URL is required for schema migrations}"
    alembic -c /workspace/apps/api/alembic.ini upgrade head
    unset NEXUS_DATABASE_URL NEXUS_MIGRATION_DATABASE_URL
    if [ "${NEXUS_RELOAD:-false}" = "true" ]; then
      # Open event streams must not hold a reload hostage: without a limit the old server waits for them forever.
      exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --reload --timeout-graceful-shutdown 3 \
        --reload-dir /workspace/apps/api/app --reload-dir /workspace/packages
    fi
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
    ;;
  worker)
    unset NEXUS_MIGRATION_DATABASE_URL NEXUS_SETUP_DATABASE_URL NEXUS_REGISTRATION_TOKEN
    exec celery -A app.workers.jobs:celery_app worker --beat --schedule=/tmp/nexus-celerybeat-schedule --loglevel="${NEXUS_WORKER_LOG_LEVEL:-INFO}" --concurrency="${NEXUS_WORKER_CONCURRENCY:-2}"
    ;;
  *)
    echo "Unknown service mode: $1" >&2
    exit 64
    ;;
esac
