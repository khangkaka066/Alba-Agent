#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=runtime_password="$NEXUS_RUNTIME_DB_PASSWORD" <<'SQL'
CREATE ROLE nexus_runtime LOGIN INHERIT NOBYPASSRLS PASSWORD :'runtime_password';
SQL
