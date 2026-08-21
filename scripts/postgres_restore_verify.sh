#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DUMP_FILE="${1:-}"
ENV_FILE="${TRACTUSMIND_ENV_FILE:-.env.production}"
RESTORE_DB="${TRACTUSMIND_RESTORE_DB:-tractusmind_restore_verify}"
KEEP_RESTORE_DB="${TRACTUSMIND_KEEP_RESTORE_DB:-0}"

if [[ -z "$DUMP_FILE" || ! -f "$DUMP_FILE" ]]; then
  echo "Usage: $0 <backup.dump>" >&2
  exit 2
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing production env file: $ENV_FILE" >&2
  exit 2
fi
if [[ "$RESTORE_DB" == "tractusmind" ]]; then
  echo "Refusing to restore into the live production database" >&2
  exit 2
fi

COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)

if ! "${COMPOSE[@]}" ps --status running postgres | grep -q postgres; then
  echo "Production postgres service is not running" >&2
  exit 2
fi

if [[ -f "${DUMP_FILE}.sha256" ]]; then
  echo "Verifying backup checksum"
  sha256sum -c "${DUMP_FILE}.sha256"
fi

container_id="$("${COMPOSE[@]}" ps -q postgres)"
cleanup() {
  if [[ "$KEEP_RESTORE_DB" != "1" ]]; then
    docker exec "$container_id" dropdb -U tractusmind --if-exists "$RESTORE_DB" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "Preparing isolated restore database: $RESTORE_DB"
docker exec "$container_id" dropdb -U tractusmind --if-exists "$RESTORE_DB"
docker exec "$container_id" createdb -U tractusmind -O tractusmind "$RESTORE_DB"

echo "Streaming backup into isolated restore database"
docker exec -i "$container_id" \
  pg_restore -U tractusmind -d "$RESTORE_DB" \
  --no-owner --no-privileges \
  < "$DUMP_FILE"

table_count="$(docker exec "$container_id" psql -U tractusmind -d "$RESTORE_DB" -Atc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")"
migration_rows="$(docker exec "$container_id" psql -U tractusmind -d "$RESTORE_DB" -Atc \
  "SELECT count(*) FROM alembic_version;")"
source_table="$(docker exec "$container_id" psql -U tractusmind -d "$RESTORE_DB" -Atc \
  "SELECT to_regclass('public.source_state') IS NOT NULL;")"

if [[ "$table_count" -lt 5 ]]; then
  echo "Restore validation failed: only $table_count public tables" >&2
  exit 1
fi
if [[ "$migration_rows" -lt 1 ]]; then
  echo "Restore validation failed: alembic_version is empty" >&2
  exit 1
fi
if [[ "$source_table" != "t" ]]; then
  echo "Restore validation failed: source_state table is missing" >&2
  exit 1
fi

echo "Restore verification: PASS ($table_count public tables)"
if [[ "$KEEP_RESTORE_DB" == "1" ]]; then
  echo "Keeping isolated restore database: $RESTORE_DB"
else
  echo "Isolated restore database will be removed"
fi
