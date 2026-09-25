#!/bin/bash
# Nightly backup of the application database out of the `db` container.
#
# Installed at /usr/local/bin/ppp-db-backup.sh, run from /etc/cron.d/ppp-db-backup.
# The database now lives in a Docker volume on this one machine, so unlike the
# old shared hosting nobody else is backing it up.
set -euo pipefail

APP_DIR=/opt/AIEmployee
DEST=/var/backups/ppp
KEEP_DAYS=7

cd "$APP_DIR"

# Read just the two values we need rather than sourcing .env, which would
# execute whatever else is in there.
DB_NAME=$(grep -E '^DB_NAME=' .env | cut -d= -f2-)
DB_ROOT_PASSWORD=$(grep -E '^DB_ROOT_PASSWORD=' .env | cut -d= -f2-)
if [ -z "$DB_NAME" ] || [ -z "$DB_ROOT_PASSWORD" ]; then
  echo "$(date -Is) FAIL: DB_NAME or DB_ROOT_PASSWORD missing from .env" >&2
  exit 1
fi

mkdir -p "$DEST"
OUT="$DEST/ppp-$(date +%F-%H%M).sql.gz"
TMP="$OUT.partial"

# MYSQL_PWD keeps the password out of the process list.
docker compose exec -T -e MYSQL_PWD="$DB_ROOT_PASSWORD" db \
  mariadb-dump -u root --single-transaction --quick --no-tablespaces \
  --default-character-set=utf8mb4 "$DB_NAME" | gzip > "$TMP"

# A dump that died halfway still leaves a valid-looking .gz, so trust it only
# if mariadb-dump wrote its end marker. Without this check a silently broken
# backup would rotate away the good ones below.
if ! gzip -dc "$TMP" | tail -5 | grep -q "Dump completed"; then
  echo "$(date -Is) FAIL: dump incomplete, kept at $TMP for inspection" >&2
  exit 1
fi

mv "$TMP" "$OUT"

# Rotate only after tonight's backup is known good.
find "$DEST" -name 'ppp-*.sql.gz' -mtime +"$KEEP_DAYS" -delete

echo "$(date -Is) ok $(du -h "$OUT" | cut -f1) $OUT"
