#!/usr/bin/env bash
# Backup do Postgres em .sql.gz. Rode no host, de dentro da pasta do projeto, via cron.
# Variaveis opcionais: BACKUP_DIR (padrao ./backups), KEEP_DAYS (padrao 14),
# PGUSER/PGDATABASE (padrao piscinow) e DB_EXEC (como executar um comando no banco).
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
DB_EXEC="${DB_EXEC:-docker compose exec -T db}"
PGUSER="${PGUSER:-piscinow}"
PGDATABASE="${PGDATABASE:-piscinow}"

mkdir -p "$BACKUP_DIR"
file="$BACKUP_DIR/piscinow-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"

# shellcheck disable=SC2086
$DB_EXEC pg_dump -U "$PGUSER" -d "$PGDATABASE" --no-owner | gzip > "$file.tmp"
gzip -t "$file.tmp"
mv "$file.tmp" "$file"

find "$BACKUP_DIR" -name 'piscinow-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
echo "$file"
