#!/bin/sh
set -eu

: "${PGHOST:=postgres}"
: "${PGPORT:=5432}"
: "${PGUSER:?PGUSER must be set}"
: "${PGDATABASE:?PGDATABASE must be set}"
: "${PGPASSWORD:?PGPASSWORD must be set}"
: "${NEXUS_BACKUP_RETENTION_DAYS:=14}"
: "${NEXUS_BACKUP_INTERVAL_SECONDS:=86400}"
export PGHOST PGPORT PGUSER PGDATABASE PGPASSWORD
umask 077
mkdir -p /backups

while :; do
    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    pg_dump --format=custom --no-owner --no-acl --file="/backups/nexus-${timestamp}.dump"
    find /backups -type f -name 'nexus-*.dump' -mtime "+${NEXUS_BACKUP_RETENTION_DAYS}" -delete
    sleep "$NEXUS_BACKUP_INTERVAL_SECONDS"
done
