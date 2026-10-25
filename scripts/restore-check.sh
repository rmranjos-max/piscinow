#!/usr/bin/env bash
# Prova que um backup restaura: carrega o arquivo num banco descartavel, confere que as
# tabelas existem (e, se CHECK_SQL for dado, que ele devolve um numero >= 1) e apaga o banco.
# Nunca toca no banco de producao. Uso: scripts/restore-check.sh backups/piscinow-XXXX.sql.gz
set -euo pipefail

file="${1:?uso: restore-check.sh <arquivo.sql.gz>}"
DB_EXEC="${DB_EXEC:-docker compose exec -T db}"
PGUSER="${PGUSER:-piscinow}"
SCRATCH_DB="${SCRATCH_DB:-piscinow_restore_check}"
MIN_TABLES="${MIN_TABLES:-11}"

gzip -t "$file"

# shellcheck disable=SC2086
psql_scratch() { $DB_EXEC psql -U "$PGUSER" -d "$SCRATCH_DB" -v ON_ERROR_STOP=1 -q "$@"; }
# shellcheck disable=SC2086
psql_admin() { $DB_EXEC psql -U "$PGUSER" -d postgres -v ON_ERROR_STOP=1 -q "$@"; }

cleanup() { psql_admin -c "DROP DATABASE IF EXISTS $SCRATCH_DB" >/dev/null 2>&1 || true; }
trap cleanup EXIT

psql_admin -c "DROP DATABASE IF EXISTS $SCRATCH_DB" -c "CREATE DATABASE $SCRATCH_DB"
gunzip -c "$file" | psql_scratch >/dev/null

tables="$(psql_scratch -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'" | tr -d '[:space:]')"
if [ "$tables" -lt "$MIN_TABLES" ]; then
  echo "FALHA: so $tables tabelas restauradas (esperado >= $MIN_TABLES)" >&2
  exit 1
fi

if [ -n "${CHECK_SQL:-}" ]; then
  value="$(psql_scratch -tAc "$CHECK_SQL" | tr -d '[:space:]')"
  if [ "${value:-0}" -lt 1 ]; then
    echo "FALHA: CHECK_SQL devolveu '$value' (esperado >= 1)" >&2
    exit 1
  fi
fi

echo "OK: backup restaurado com $tables tabelas"
