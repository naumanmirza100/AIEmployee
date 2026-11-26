#!/bin/bash
# Nightly FULL backup off the VPS: the database AND the uploaded files (CVs, HR and
# Frontline documents, attachments), encrypted and sent to Backblaze B2. Then each
# company's own backup (its dashboard's Backups page), encrypted and sent the same way.
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
# Each company's backup (manage.py make_company_backups: that company's data and
# uploads, its passwords and keys left out) goes to B2:<bucket>/companies/<id>/, also
# kept 30 days; the server keeps the last 7 of each. A company that fails does not
# stop the others, and the script ends with FAIL so the log shows it. The whole-system
# backup is still the one to restore a server from; a company's is its copy to keep.
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
trap 'rm -f "$WORK"/*.gpg' EXIT      # never leave an encrypted copy lying around

# encrypt <path under /app/backups> <encrypted file>: succeeds only if the copy
# decrypts to exactly the zip the app made.
encrypt() {
  docker compose exec -T web cat "/app/backups/$1" | \
    gpg --batch --yes --quiet --symmetric --cipher-algo AES256 \
        --passphrase-fd 3 --pinentry-mode loopback --output "$2" \
        3< <(printf '%s' "$BACKUP_GPG_PASSPHRASE")
  local want got
  want=$(docker compose exec -T web sha256sum "/app/backups/$1" | cut -d' ' -f1)
  got=$(gpg --batch --quiet --decrypt --passphrase-fd 3 --pinentry-mode loopback "$2" \
          3< <(printf '%s' "$BACKUP_GPG_PASSPHRASE") | sha256sum | cut -d' ' -f1)
  [ -n "$want" ] && [ "$want" = "$got" ]
}

# ship <encrypted file> <folder in the bucket>: succeeds only once it is in B2 at its
# full size, rather than trusting a zero exit code.
ship() {
  rclone copy "$1" "B2:${B2_BUCKET}/$2/" --no-traverse --quiet || return 1
  local name local_size remote_size
  name=$(basename "$1")
  local_size=$(stat -c %s "$1")
  remote_size=$(rclone lsf "B2:${B2_BUCKET}/$2/" --include "$name" --format s --quiet | head -1)
  [ "$remote_size" = "$local_size" ]
}

ENC="$WORK/$NAME.gpg"
if ! encrypt "$NAME" "$ENC"; then
  echo "$(date -Is) full FAIL: the encrypted copy of $NAME does not decrypt to the backup" >&2
  exit 1
fi

# ---- 3. ship ----------------------------------------------------------------
export RCLONE_CONFIG=/dev/null
export RCLONE_CONFIG_B2_TYPE=b2
export RCLONE_CONFIG_B2_ACCOUNT="$B2_KEY_ID"
export RCLONE_CONFIG_B2_KEY="$B2_APP_KEY"

if ! ship "$ENC" full; then
  echo "$(date -Is) full FAIL: $(basename "$ENC") did not arrive whole in B2:${B2_BUCKET}/full/" >&2
  exit 1
fi

# Older copies are deleted for good (B2 would otherwise keep them as hidden versions).
rclone delete "B2:${B2_BUCKET}/full/" --min-age "${KEEP_REMOTE_DAYS}d" --b2-hard-delete --quiet || true
echo "$(date -Is) full offsite ok B2:${B2_BUCKET}/full/$(basename "$ENC") ($(du -h "$ENC" | cut -f1))"
rm -f "$ENC"

# ---- 4. each company's backup -----------------------------------------------
# make_company_backups prints one line per finished backup, companies/<id>/<name>. A
# company whose backup failed is on stderr and makes it exit non-zero; the ones that
# were made are still encrypted and sent.
COMPANY_FAILED=0
COMPANY_LIST=$(docker compose exec -T web python manage.py make_company_backups --keep "$KEEP_SERVER" | tr -d '\r') \
  || COMPANY_FAILED=1
SENT=0
# The list is read on fd 4: docker compose exec reads stdin, and would eat the rest of it.
while IFS= read -r -u 4 REL; do
  case "$REL" in
    companies/*/backup-*-nightly.zip) ;;
    *) continue ;;
  esac
  DIR=$(dirname "$REL")                         # companies/<id>
  CENC="$WORK/$(basename "$REL").gpg"
  if ! encrypt "$REL" "$CENC"; then
    echo "$(date -Is) company FAIL: the encrypted copy of $REL does not decrypt to the backup" >&2
    COMPANY_FAILED=1
  elif ! ship "$CENC" "$DIR"; then
    echo "$(date -Is) company FAIL: $REL did not arrive whole in B2:${B2_BUCKET}/$DIR/" >&2
    COMPANY_FAILED=1
  else
    SENT=$((SENT + 1))
  fi
  rm -f "$CENC"
done 4<<< "$COMPANY_LIST"

rclone delete "B2:${B2_BUCKET}/companies/" --min-age "${KEEP_REMOTE_DAYS}d" --b2-hard-delete --quiet || true
if [ "$COMPANY_FAILED" -ne 0 ]; then
  echo "$(date -Is) company FAIL: $SENT company backup(s) sent to B2:${B2_BUCKET}/companies/, but some failed (see above)" >&2
  exit 1
fi
echo "$(date -Is) company offsite ok: $SENT company backup(s) in B2:${B2_BUCKET}/companies/"
