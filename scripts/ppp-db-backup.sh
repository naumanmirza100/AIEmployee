#!/bin/bash
# Nightly backup of the application database out of the `db` container.
#
# Installed at /usr/local/bin/ppp-db-backup.sh, run from /etc/cron.d/ppp-db-backup.
# The database lives in a Docker volume on this one machine, so unlike the old
# shared hosting nobody else is backing it up.
#
# Two copies are made:
#   * plaintext .sql.gz in /var/backups/ppp  (7 days, fast local restore)
#   * AES256-encrypted .gpg pushed to Backblaze B2 (90 days, survives the VPS)
#
# The off-site copy is encrypted before it leaves the machine because the dump
# contains customer personal data. The passphrase must ALSO be stored in a
# password manager — if it only exists on this box, losing the box leaves you
# with backups you cannot open.
set -euo pipefail

APP_DIR=/opt/AIEmployee
DEST=/var/backups/ppp
KEEP_DAYS=7
KEEP_REMOTE_DAYS=90

cd "$APP_DIR"

# Read the values we need rather than sourcing .env, which would execute
# whatever else happens to be in there.
env_get() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- || true; }

DB_NAME=$(env_get DB_NAME)
DB_ROOT_PASSWORD=$(env_get DB_ROOT_PASSWORD)
B2_KEY_ID=$(env_get B2_KEY_ID)
B2_APP_KEY=$(env_get B2_APP_KEY)
B2_BUCKET=$(env_get B2_BUCKET)
BACKUP_GPG_PASSPHRASE=$(env_get BACKUP_GPG_PASSPHRASE)

if [ -z "$DB_NAME" ] || [ -z "$DB_ROOT_PASSWORD" ]; then
  echo "$(date -Is) FAIL: DB_NAME or DB_ROOT_PASSWORD missing from .env" >&2
  exit 1
fi

mkdir -p "$DEST"
OUT="$DEST/ppp-$(date +%F-%H%M).sql.gz"
TMP="$OUT.partial"

# ---- 1. dump locally -------------------------------------------------------
# MYSQL_PWD keeps the password out of the process list.
docker compose exec -T -e MYSQL_PWD="$DB_ROOT_PASSWORD" db \
  mariadb-dump -u root --single-transaction --quick --no-tablespaces \
  --default-character-set=utf8mb4 "$DB_NAME" | gzip > "$TMP"

# A dump that died halfway still produces a valid-looking .gz, so trust it only
# if mariadb-dump wrote its end marker. Without this check a silently broken
# backup would rotate away the good ones below.
if ! gzip -dc "$TMP" | tail -5 | grep -q "Dump completed"; then
  echo "$(date -Is) FAIL: dump incomplete, kept at $TMP for inspection" >&2
  exit 1
fi
mv "$TMP" "$OUT"

# Rotate local copies only once tonight's is known good.
find "$DEST" -name 'ppp-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) local ok $(du -h "$OUT" | cut -f1) $OUT"

# ---- 2. encrypt and ship off-site -----------------------------------------
if [ -z "$B2_KEY_ID" ] || [ -z "$B2_APP_KEY" ] || [ -z "$B2_BUCKET" ] || [ -z "$BACKUP_GPG_PASSPHRASE" ]; then
  echo "$(date -Is) WARN: off-site upload skipped (B2_KEY_ID/B2_APP_KEY/B2_BUCKET/BACKUP_GPG_PASSPHRASE not all set in .env)" >&2
  exit 0
fi

ENC="$OUT.gpg"
trap 'rm -f "$ENC"' EXIT      # never leave the encrypted copy lying around

printf '%s' "$BACKUP_GPG_PASSPHRASE" | gpg --batch --yes --quiet \
  --symmetric --cipher-algo AES256 \
  --passphrase-fd 0 --pinentry-mode loopback \
  --output "$ENC" "$OUT"

export RCLONE_CONFIG=/dev/null
export RCLONE_CONFIG_B2_TYPE=b2
export RCLONE_CONFIG_B2_ACCOUNT="$B2_KEY_ID"
export RCLONE_CONFIG_B2_KEY="$B2_APP_KEY"

rclone copy "$ENC" "B2:${B2_BUCKET}/db/" --no-traverse --quiet

# Confirm it actually landed, rather than trusting a zero exit code.
REMOTE_NAME=$(basename "$ENC")
if ! rclone lsf "B2:${B2_BUCKET}/db/" --include "$REMOTE_NAME" --quiet | grep -q .; then
  echo "$(date -Is) FAIL: $REMOTE_NAME not found in B2 after upload" >&2
  exit 1
fi

rclone delete "B2:${B2_BUCKET}/db/" --min-age "${KEEP_REMOTE_DAYS}d" --quiet || true
echo "$(date -Is) offsite ok B2:${B2_BUCKET}/db/$REMOTE_NAME"
