#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${TRACTUSMIND_ENV_FILE:-.env.production}"
BACKUP_DIR="${TRACTUSMIND_BACKUP_DIR:-backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT="${1:-${BACKUP_DIR}/tractusmind-${TIMESTAMP}.dump}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing production env file: $ENV_FILE" >&2
  exit 2
fi

mkdir -p "$(dirname "$OUTPUT")"
umask 077

COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)

if ! "${COMPOSE[@]}" ps --status running postgres | grep -q postgres; then
  echo "Production postgres service is not running" >&2
  exit 2
fi

echo "Creating PostgreSQL backup: $OUTPUT"
"${COMPOSE[@]}" exec -T postgres \
  pg_dump -U tractusmind -d tractusmind \
  --format=custom --no-owner --no-privileges \
  > "$OUTPUT"

size="$(stat -c %s "$OUTPUT")"
if [[ "$size" -le 1024 ]]; then
  echo "Backup is unexpectedly small: ${size} bytes" >&2
  rm -f "$OUTPUT"
  exit 1
fi

sha256sum "$OUTPUT" > "${OUTPUT}.sha256"
chmod 600 "$OUTPUT" "${OUTPUT}.sha256"

echo "Backup complete (${size} bytes)"
echo "Checksum: ${OUTPUT}.sha256"
