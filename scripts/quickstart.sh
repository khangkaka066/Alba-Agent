#!/usr/bin/env bash
# One-command setup: checks the machine, creates .env with generated secrets, starts the stack.
#
#   ./scripts/quickstart.sh           check, prepare .env if it does not exist, then start the stack
#   ./scripts/quickstart.sh --check   only report problems; change nothing and start nothing
#
# An existing .env is never overwritten: only keys that are empty in it are filled in.
# NEXUS_ENV_FILE points the script at another file (used by tests).
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="${NEXUS_ENV_FILE:-.env}"
MIN_DOCKER_MEMORY_MB=5500
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

problems=0
warn() { printf 'PROBLEM  %s\n' "$1"; problems=$((problems + 1)); }
note() { printf 'ok       %s\n' "$1"; }

# --- the machine ------------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  warn "docker is not installed. Install Docker Desktop (macOS/Windows) or Docker Engine (Linux)."
elif ! docker info >/dev/null 2>&1; then
  warn "the Docker daemon is not answering. Start Docker Desktop, wait until it is idle, and run this again."
else
  note "docker daemon answers"
  memory_bytes="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)"
  memory_mb=$((memory_bytes / 1024 / 1024))
  if [ "$memory_mb" -lt "$MIN_DOCKER_MEMORY_MB" ]; then
    warn "Docker has ${memory_mb} MB of memory; at least ${MIN_DOCKER_MEMORY_MB} MB is needed or runs time out (8 GB is comfortable). Raise it in Docker Desktop > Settings > Resources."
  else
    note "docker memory ${memory_mb} MB"
  fi
fi

if ! docker compose version >/dev/null 2>&1; then
  warn "the 'docker compose' plugin is missing."
fi
command -v openssl >/dev/null 2>&1 || warn "openssl is needed to generate secrets."

port_in_use() {
  if command -v lsof >/dev/null 2>&1; then lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; else return 1; fi
}
for port in "${NEXUS_API_PORT:-8000}" "${NEXUS_WEB_PORT:-3000}"; do
  if port_in_use "$port"; then
    # A port held by this project's own stack is fine; anything else blocks the start.
    if docker ps --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
      note "port ${port} is held by a running container"
    else
      warn "port ${port} is already in use by another program."
    fi
  fi
done

# --- .env -------------------------------------------------------------------------------------
SECRET_HEX_KEYS="NEXUS_POSTGRES_PASSWORD NEXUS_RUNTIME_DB_PASSWORD NEXUS_REDIS_PASSWORD NEXUS_SECRET_KEY NEXUS_API_KEY_PEPPER"
SECRET_BASE64_KEYS="NEXUS_CREDENTIAL_ENCRYPTION_KEY_BASE64"

empty_secrets() {
  for key in $SECRET_HEX_KEYS $SECRET_BASE64_KEYS; do
    grep -Eq "^${key}=$" "$ENV_FILE" && echo "$key"
  done
  return 0
}

fill_key() {  # fill_key KEY VALUE: set KEY only where it is currently empty
  local tmp
  tmp="$(mktemp)"
  awk -v key="$1" -v value="$2" 'BEGIN{FS=OFS="="} $1==key && NF==2 && $2=="" {print key, value; next} {print}' "$ENV_FILE" > "$tmp"
  cat "$tmp" > "$ENV_FILE"
  rm -f "$tmp"
}

if [ -f "$ENV_FILE" ]; then
  missing="$(empty_secrets)"
  if [ -n "$missing" ]; then
    if [ "$CHECK_ONLY" -eq 1 ]; then
      warn "$ENV_FILE has empty secrets: $(echo "$missing" | tr '\n' ' ')(run without --check to generate them)"
    else
      for key in $missing; do
        case " $SECRET_BASE64_KEYS " in
          *" $key "*) fill_key "$key" "$(openssl rand -base64 32)" ;;
          *) fill_key "$key" "$(openssl rand -hex 32)" ;;
        esac
      done
      note "filled empty secrets in $ENV_FILE: $(echo "$missing" | tr '\n' ' ')"
    fi
  else
    note "$ENV_FILE has every secret set"
  fi
elif [ "$CHECK_ONLY" -eq 1 ]; then
  warn "$ENV_FILE does not exist (run without --check to create it from .env.example)"
else
  cp .env.example "$ENV_FILE"
  for key in $SECRET_HEX_KEYS; do fill_key "$key" "$(openssl rand -hex 32)"; done
  for key in $SECRET_BASE64_KEYS; do fill_key "$key" "$(openssl rand -base64 32)"; done
  note "created $ENV_FILE with generated secrets"
fi

# --- Linux: the sandbox needs the docker socket's group and a writable artifact directory ------
if [ "$(uname -s)" = "Linux" ] && [ -S /var/run/docker.sock ] && [ "$CHECK_ONLY" -eq 0 ] && [ -f "$ENV_FILE" ]; then
  gid="$(stat -c '%g' /var/run/docker.sock)"
  grep -Eq '^NEXUS_DOCKER_GID=$' "$ENV_FILE" && fill_key NEXUS_DOCKER_GID "$gid"
  mkdir -p data/artifacts
  [ "$(stat -c '%u' data/artifacts)" = "10001" ] || printf 'NOTE     run: sudo chown -R 10001 data/artifacts\n'
fi

if [ "$problems" -gt 0 ]; then
  printf '\n%s problem(s) found; fix them and run this again.\n' "$problems"
  exit 1
fi
[ "$CHECK_ONLY" -eq 1 ] && { printf '\nEverything needed is in place.\n'; exit 0; }

# --- start --------------------------------------------------------------------------------------
docker compose --env-file "$ENV_FILE" up -d --build
printf '\nOpen http://localhost:%s and connect a model under Settings.\n' "${NEXUS_WEB_PORT:-3000}"
