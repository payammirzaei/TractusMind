#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: RESTORE_CONFIRM=YES scripts/restore-postgres.sh <backup.dump>" >&2
  exit 2
fi
if [ "${RESTORE_CONFIRM:-}" != "YES" ]; then
  echo "refusing destructive restore: set RESTORE_CONFIRM=YES" >&2
  exit 2
fi

BACKUP="$1"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"

if [ ! -f "${BACKUP}" ]; then
  echo "backup not found: ${BACKUP}" >&2
  exit 2
fi

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" \
  exec -T postgres pg_restore \
  -U tractusmind \
  -d tractusmind \
  --clean \
  --if-exists \
  --no-owner < "${BACKUP}"

printf 'PostgreSQL restore completed from %s\n' "${BACKUP}"
