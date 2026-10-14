#!/bin/bash
# Deploy the code that is checked out in /opt/AIEmployee, and prove it came up.
#
# Run on the server by .github/workflows/deploy.yml after `git pull`, or by hand:
#     cd /opt/AIEmployee && git pull && bash scripts/deploy.sh
#
# What it used to be was `docker compose up --build -d` and nothing else. Database
# changes were applied as the web container started, so when one failed the web
# server never came up and kept restarting, while the background workers, already
# on the new code, carried on against the old tables; and the deploy still showed
# green, because all it knew was that the containers had been started. No backup
# was taken first.
#
# The order here, and why:
#   1. build the new image            the old containers keep serving meanwhile;
#      and check it                   Django's own checks, and that no model was
#                                     changed without its migration, in the real
#                                     image, before anything is touched
#   2. back the database up           only when there are database changes to apply
#   3. apply the database changes     in a throwaway container; if this fails the
#                                     script stops and the OLD containers are still
#                                     the ones running
#   4. switch over                    docker compose up -d
#   5. ask the site if it is well     /api/health must answer 200 with the database
#                                     connected; if it does not, the logs are shown
#                                     and the script fails, so the deploy shows red
#
# It does not roll back. A failed step 3 can leave the database part-changed
# (MariaDB does not undo table changes), which is what the backup in step 2 is for:
# restore steps are in MDS/HOSTINGER_DB_DEPLOYMENT.md.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/AIEmployee}"
HEALTH_TRIES="${HEALTH_TRIES:-45}"          # x 4 seconds = three minutes
cd "$APP_DIR"

say() { echo "$(date -Is) deploy: $*"; }
env_get() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'"'\r' || true; }

commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)
say "commit ${commit:0:9}"

# The workflow tries three times, because the SSH connection to this server
# sometimes drops. A commit that really failed here must not be put through all of
# this twice more: it is remembered, and the next try stops at once. FORCE=1 (the
# "force" box when the workflow is run by hand) tries it again.
failed_before="/tmp/deploy-failed-$commit"
if [ -f "$failed_before" ] && [ "${FORCE:-}" != "1" ]; then
  say "FAIL: this commit already failed to deploy at $(cat "$failed_before"). Not trying again."
  say "Fix the cause, then run the workflow by hand with 'force' ticked (or FORCE=1 bash scripts/deploy.sh)."
  exit 1
fi
trap 'date -Is > "$failed_before"' ERR

# ---- 1. build, and check what was built --------------------------------------
say "building the image"
docker compose build

# The database and the queue must be up for the next steps; they are left running.
docker compose up -d --wait db redis || docker compose up -d db redis     # --wait: Compose 2.1.1 and later

say "checking the new image"
docker compose run --rm --no-deps web python manage.py check
# A model changed without a migration works here and breaks on the first query
# after the deploy ("Unknown column"). --dry-run: nothing is written.
if ! docker compose run --rm --no-deps web python manage.py makemigrations --check --dry-run >/tmp/deploy-makemigrations.txt 2>&1; then
  say "FAIL: a model was changed without its migration. Run makemigrations, commit the file, deploy again."
  tail -25 /tmp/deploy-makemigrations.txt
  false
fi

# ---- 2 and 3. database changes ---------------------------------------------
# `migrate --check` exits non-zero when something is waiting to be applied.
if docker compose run --rm --no-deps web python manage.py migrate --check >/dev/null 2>&1; then
  say "no database changes to apply"
else
  if [ "${SKIP_BACKUP:-}" = "1" ]; then
    say "WARNING: database changes are waiting and SKIP_BACKUP=1, so no backup is taken"
  else
    say "database changes are waiting: backing the database up first"
    LOCAL_ONLY=1 bash scripts/ppp-db-backup.sh
  fi
  say "applying database changes"
  docker compose run --rm --no-deps web python manage.py migrate --noinput
fi

# ---- 4. switch over ----------------------------------------------------------
say "starting the new containers"
docker compose up -d

# ---- 5. is the site well? ------------------------------------------------------
# Asked on the server itself, with the site's own host name so that Django's
# ALLOWED_HOSTS lets it through, and as https so that a redirect to https does
# not pass for an answer.
host_of() { printf '%s' "$1" | sed -E 's#^[a-z]+://##; s#[/,].*$##; s#[[:space:]]##g'; }
# The names this server may answer to, most likely first. One of them will be in
# ALLOWED_HOSTS; the rest get a 400, which is not an answer to the question.
hosts=$(
  for name in BACKEND_URL SITE_URL DJANGO_ALLOWED_HOSTS ALLOWED_HOSTS; do
    host_of "$(env_get "$name")"; echo
  done | awk 'NF && !seen[$0]++'
  echo localhost; echo 127.0.0.1
)

say "waiting for http://127.0.0.1:8000/api/health"
ok=0
code=none
for try in $(seq 1 "$HEALTH_TRIES"); do
  for host in $hosts; do
    code=$(curl -s -o /tmp/deploy-health.json -w '%{http_code}' --max-time 5 -H "Host: $host" \
             -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/api/health || true)
    if [ "$code" = "200" ] && grep -q '"database": *"connected"' /tmp/deploy-health.json; then
      ok=1
      break 2
    fi
  done
  sleep 4
done

if [ "$ok" != "1" ]; then
  say "FAIL: the site did not answer after the deploy (last answer: ${code:-none})"
  docker compose ps || true
  say "---- last lines from the web container ----"
  docker compose logs --tail=80 web || true
  false
fi
say "the site is up: $(cat /tmp/deploy-health.json)"
level=$(curl -s --max-time 5 -H "Host: $host" -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/api/version || true)
say "server API level: ${level:-unknown}"

# The workers must be on the new code too, and not restarting.
for service in worker beat; do
  state=$(docker compose ps --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$service" '$1 == s {print $2}')
  if [ -n "$state" ] && [ "$state" != "running" ]; then
    say "FAIL: the $service container is '$state', not running"
    docker compose logs --tail=40 "$service" || true
    false
  fi
done

rm -f "$failed_before"
docker image prune -f >/dev/null
say "done"
