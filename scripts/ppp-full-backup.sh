#!/bin/bash
# Nightly FULL backup off the VPS: the database AND the uploaded files (CVs, HR and
# Frontline documents, attachments), encrypted and sent to Backblaze B2.
#
# Installed at /usr/local/bin/ppp-full-backup.sh, run from /etc/cron.d/ppp-full-backup:
#   0 21 * * * root /usr/local/bin/ppp-full-backup.sh >> /var/log/ppp-backup.log 2>&1
# (21:00 UTC is 02:00 in Pakistan.)
#
# ppp-db-backup.sh already sends the database alone every night (kept 90 days), but
# not the uploaded files: a lost VPS took every CV and document with it. This sends
# the app's own backup (manage.py make_backup, the same zip as Admin -> Backups; the
# server keeps the last 7 of them) and keeps 30 days in B2, as it is ten times the size.
#
# Same bucket and passphrase (BACKUP_GPG_PASSPHRASE) as the database copies. The
# passphrase must also be in a password manager. To restore on a new server:
#   rclone copy B2:<bucket>/full/<name>.gpg .
#   gpg --decrypt <name>.gpg > <name>                      (asks for the passphrase)
#   docker compose exec web python manage.py migrate
#   docker compose cp <name> web:/app/backups/ && docker compose exec web python manage.py restore_backup /app/backups/<name>
# Stored API keys and mailbox passwords decrypt only with the old server's
# FIELD_ENCRYPTION_KEY (or SECRET_KEY): keep a copy of those with the passphrase.
set -euo pipefail

APP_DIR=/opt/AIEmployee
WORK=/var/backups/ppp-full
KEEP_SERVER=7
KEEP_REMOTE_DAYS=30

cd "$APP_DIR"

# Read the values we need rather than sourcing .env (see ppp-db-backup.sh).
env_get() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- || true; }

B2_KEY_ID=$(env_get B2_KEY_ID)
B2_APP_KEY=$(env_get B2_APP_KEY)
B2_BUCKET=$(env_get B2_BUCKET)
BACKUP_GPG_PASSPHRASE=$(env_get BACKUP_GPG_PASSPHRASE)

# ---- 1. make it -------------------------------------------------------------
# The app's own backup, on the web container; its file name is the last line.
NAME=$(docker compose exec -T web python manage.py make_backup --keep "$KEEP_SERVER" | tail -1 | tr -d '\r')
case "$NAME" in
  backup-*-nightly.zip) ;;
  *) echo "$(date -Is) full FAIL: make_backup did not finish (said: ${NAME:-nothing})" >&2; exit 1 ;;
esac
echo "$(date -Is) full local ok $NAME"

if [ -z "$B2_KEY_ID" ] || [ -z "$B2_APP_KEY" ] || [ -z "$B2_BUCKET" ] || [ -z "$BACKUP_GPG_PASSPHRASE" ]; then
  echo "$(date -Is) full FAIL: off-site upload skipped (B2_KEY_ID/B2_APP_KEY/B2_BUCKET/BACKUP_GPG_PASSPHRASE not all set in .env)" >&2
  exit 1
fi

# ---- 2. encrypt -------------------------------------------------------------
# Straight from the container into gpg: no unencrypted copy is written on the host.
mkdir -p "$WORK"
chmod 700 "$WORK"
ENC="$WORK/$NAME.gpg"
trap 'rm -f "$ENC"' EXIT      # never leave the encrypted copy lying around

docker compose exec -T web cat "/app/backups/$NAME" | \
  gpg --batch --yes --quiet --symmetric --cipher-algo AES256 \
      --passphrase-fd 3 --pinentry-mode loopback --output "$ENC" \
      3< <(printf '%s' "$BACKUP_GPG_PASSPHRASE")

# Trust it only if it decrypts to exactly the zip the app made.
WANT=$(docker compose exec -T web sha256sum "/app/backups/$NAME" | cut -d' ' -f1)
GOT=$(gpg --batch --quiet --decrypt --passphrase-fd 3 --pinentry-mode loopback "$ENC" \
        3< <(printf '%s' "$BACKUP_GPG_PASSPHRASE") | sha256sum | cut -d' ' -f1)
if [ -z "$WANT" ] || [ "$WANT" != "$GOT" ]; then
  echo "$(date -Is) full FAIL: the encrypted copy of $NAME does not decrypt to the backup" >&2
  exit 1
fi

# ---- 3. ship ----------------------------------------------------------------
export RCLONE_CONFIG=/dev/null
export RCLONE_CONFIG_B2_TYPE=b2
export RCLONE_CONFIG_B2_ACCOUNT="$B2_KEY_ID"
export RCLONE_CONFIG_B2_KEY="$B2_APP_KEY"

rclone copy "$ENC" "B2:${B2_BUCKET}/full/" --no-traverse --quiet

# Confirm it landed, at its full size, rather than trusting a zero exit code.
REMOTE_NAME=$(basename "$ENC")
LOCAL_SIZE=$(stat -c %s "$ENC")
REMOTE_SIZE=$(rclone lsf "B2:${B2_BUCKET}/full/" --include "$REMOTE_NAME" --format s --quiet | head -1)
if [ "$REMOTE_SIZE" != "$LOCAL_SIZE" ]; then
  echo "$(date -Is) full FAIL: $REMOTE_NAME in B2 is ${REMOTE_SIZE:-missing}, expected $LOCAL_SIZE bytes" >&2
  exit 1
fi

# Older copies are deleted for good (B2 would otherwise keep them as hidden versions).
rclone delete "B2:${B2_BUCKET}/full/" --min-age "${KEEP_REMOTE_DAYS}d" --b2-hard-delete --quiet || true
echo "$(date -Is) full offsite ok B2:${B2_BUCKET}/full/$REMOTE_NAME ($(du -h "$ENC" | cut -f1))"
