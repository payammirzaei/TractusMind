#!/usr/bin/env sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT="${BACKUP_DIR}/tractusmind-postgres-${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"
umask 077

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" \
  exec -T postgres pg_dump -U tractusmind -d tractusmind -Fc > "${OUTPUT}"

printf 'PostgreSQL backup written to %s\n' "${OUTPUT}"
