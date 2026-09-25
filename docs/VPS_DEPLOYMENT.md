# Moving the database onto the VPS

Audience: whoever deploys the backend on the Hostinger VPS.
Goal: stop using the Hostinger shared-hosting database and run MariaDB next to
the app, in the same `docker compose` stack.

## Why

The shared-hosting database caps the DB user at **500 new connections an hour**.
Celery Beat alone fires ~300 tasks an hour, each opening connections, so the app
locks itself out and every agent's scheduled work fails with:

```
OperationalError(1226, "User '...' has exceeded the 'max_connections_per_hour'
resource (current value: 500)")
```

It recovers only when the hour rolls over. A database you own has no such cap.

The second win is latency. Measured 2026-09-11: the server executes a query in
**0.26 ms**, but the round trip from outside took **232 ms** — 99.9% of every
query was transit, because the database sits in Hostinger's Boston datacenter.
Running it on the same host makes that a local call.

## Before you start

- SSH access to the VPS, with `docker` and `docker compose` working.
- The repo checked out on the VPS with a working `.env`.
- The current (old) database credentials — needed for the dump.
- About 15 minutes. The app is down only for the final restart.

## Step 1 — Take a backup of the live database

Do this **first**, while `.env` still holds the old credentials.

Hostinger only accepts remote MySQL connections from whitelisted IPs, so add the
VPS's public address in **hPanel → Databases → Remote MySQL** before running
this. Get the address with `curl -s ifconfig.me`.

On the VPS:

```bash
cd /path/to/AIEmployee
set -a; . ./.env; set +a          # load the OLD credentials

docker run --rm -e MYSQL_PWD="$DB_PASSWORD" mariadb:11.4 \
  mariadb-dump \
    -h "$DB_HOST" -P "${DB_PORT:-3306}" -u "$DB_USER" \
    --single-transaction --quick --no-tablespaces \
    --default-character-set=utf8mb4 \
    "$DB_NAME" > ~/ppp-backup-$(date +%F-%H%M).sql

ls -lh ~/ppp-backup-*.sql        # sanity: should not be 0 bytes
```

Why those flags:

- `--single-transaction` — consistent snapshot without locking (InnoDB).
- `--no-tablespaces` — the dump otherwise needs the `PROCESS` privilege, which
  shared-hosting users usually do not have. Without this the dump fails.
- `--quick` — streams rows instead of buffering whole tables in memory.
- No `--databases`, so the dump contains no `CREATE DATABASE`. It restores into
  a database that already exists, which is what the container gives us.

Passwords go through `MYSQL_PWD` rather than `-p...` so they do not appear in
the process list.

## Step 2 — Set the new credentials

Edit `.env` on the VPS:

```ini
DB_ENGINE=mysql
DB_NAME=<keep the same name, or pick a new one>
DB_USER=<keep the same, or pick a new one>
DB_PASSWORD=<NEW strong password>
DB_ROOT_PASSWORD=<NEW strong password, different from the above>
```

Generate them with `openssl rand -base64 24`.

Do not put a `$` in either password. `docker-compose.yml` interpolates these
values, so a `$` is read as the start of a variable and the password silently
arrives wrong — you would see the `db` container come up but the app fail to
authenticate. (`$$` escapes it if you must.) Base64 output never contains `$`,
so the command above is safe. Avoid quotes too: `.env` keeps them literally, so
`DB_PASSWORD="abc"` makes the password `"abc"`, quotes included.

Choose a **new** `DB_PASSWORD`. The old one has been pasted into chat and into
`MDS/HOSTINGER_DB_DEPLOYMENT.md`, so treat it as compromised regardless of this
migration — and rotate it in hPanel afterwards.

Leave `DB_HOST` / `DB_PORT` alone **for now** — they still point at the old
host, which is what you want until the data is loaded and verified. Step 6 is
where you switch them over.

Add one more line, which is what turns the local database on at all:

```ini
COMPOSE_PROFILES=localdb
```

The `db` service carries `profiles: ["localdb"]`, so a plain
`docker compose up -d` ignores it entirely. This matters because
`.github/workflows/deploy.yml` runs `docker compose up --build -d` on every push
to `main`: without the profile, merging the database change would start an empty
MariaDB and point the app at it on the next deploy. With it, only a host that
has opted in ever runs a local database, and only after you say so.

The `db` container creates `DB_NAME`, `DB_USER` and `DB_PASSWORD` on its **first
boot only**, from the empty `dbdata` volume. Changing them later in `.env` does
not change the database — see Troubleshooting.

## Step 3 — Start the database on its own

```bash
docker compose --profile localdb up -d db
docker compose ps db                      # wait for "healthy" (~40s first run)
docker compose logs -f db                 # Ctrl-C once you see "ready for connections"
```

The app is still talking to the old remote database at this point. Nothing has
switched over yet.

## Step 4 — Load the backup

```bash
set -a; . ./.env; set +a                  # now the NEW credentials

docker compose exec -T -e MYSQL_PWD="$DB_ROOT_PASSWORD" db \
  mariadb -u root "$DB_NAME" < ~/ppp-backup-<stamp>.sql
```

`-T` disables the pseudo-TTY, without which the redirect silently delivers
nothing.

## Step 5 — Check the data landed

```bash
docker compose exec -e MYSQL_PWD="$DB_ROOT_PASSWORD" db \
  mariadb -u root -e "
    SELECT COUNT(*) AS companies     FROM core_company;
    SELECT COUNT(*) AS company_users FROM core_companyuser;
    SELECT COUNT(*) AS purchases     FROM core_companymodulepurchase;
    SELECT COUNT(*) AS qa_chats      FROM Frontline_agent_frontlineqachat;
  " "$DB_NAME"
```

Compare against the old database before cutting over. As of 2026-09-24 that was
6 companies, 4 active company users, 3 module purchases, 5 Q&A chats.

`Frontline_agent_document` being 0 is expected — tenant data was never migrated
off SQL Server in September, so documents have to be re-uploaded (or recovered
from SQL Server separately).

## Step 6 — Cut the app over

Only now, once the counts above look right, point the app at the new database.
In `.env`:

```ini
DB_HOST=db
DB_PORT=3306
```

Then rebuild:

```bash
docker compose up -d --build
docker compose ps                         # web, worker, beat, redis, db all up
docker compose logs --tail=50 web
```

This is the one irreversible-feeling moment, and it isn't: the old database is
untouched, so putting the two old values back and re-running this command
returns you to exactly where you started.

The `web` container runs `migrate` on start, so any pending migrations apply
automatically. `django_migrations` came across in the dump, so nothing re-runs.

## Step 7 — Confirm the cap is gone

```bash
docker compose logs --since=15m worker | grep -c max_connections_per_hour
```

Should be `0`. Previously this fired continuously. Also confirm tasks succeed:

```bash
docker compose logs --since=15m worker | grep -c "succeeded in"
```

## Rolling back

Nothing is destroyed by this process — the old database is untouched.

Put the old `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` back in `.env`
and rebuild:

```bash
docker compose up -d --build
```

No change to `docker-compose.yml` is needed — the app reads the host from
`.env`, so reverting those lines is the whole rollback. Leave the `db` container
running or stop it with `docker compose --profile localdb stop db`; either way
`down -v` is the one command to avoid, because it deletes the volume.

To stop the VPS running a local database at all, drop `COMPOSE_PROFILES` from
`.env`.

## Ongoing backups

The data now lives in the `dbdata` Docker volume on one machine. That is a
single point of failure — shared hosting was at least backed up by Hostinger.
Add a nightly dump, for example a small script in `/usr/local/bin/ppp-backup.sh`:

```bash
#!/bin/sh
set -eu
cd /path/to/AIEmployee
. ./.env
mkdir -p /var/backups/ppp
docker compose exec -T -e MYSQL_PWD="$DB_ROOT_PASSWORD" db \
  mariadb-dump -u root --single-transaction --quick "$DB_NAME" \
  | gzip > "/var/backups/ppp/ppp-$(date +%F).sql.gz"
find /var/backups/ppp -name 'ppp-*.sql.gz' -mtime +7 -delete
```

Then `chmod +x` it and add `0 3 * * * root /usr/local/bin/ppp-backup.sh` to
`/etc/cron.d/ppp-db-backup`. Copy the dumps off the VPS, and test a restore once
— an untested backup is not a backup.

## Security notes

- Port 3306 is **not** published to the host. The database is reachable only
  from inside the compose network. Do not add a `ports:` entry for it — that
  would expose MariaDB to the whole internet.
- Check the firewall allows only what you need: `ufw status`. Prefer nginx on
  80/443 in front of the app rather than exposing 8000.
- Rotate the old shared-hosting password in hPanel once the cutover is done.

## Troubleshooting

**`db` never becomes healthy.** Check `docker compose logs db`. A pre-existing
`dbdata` volume initialised with different credentials is the usual cause.

**App cannot authenticate after changing `DB_PASSWORD`.** The container only
creates the user on first boot. Either change the password in place:

```bash
docker compose exec -e MYSQL_PWD="$DB_ROOT_PASSWORD" db \
  mariadb -u root -e "ALTER USER '<user>'@'%' IDENTIFIED BY '<new password>'; FLUSH PRIVILEGES;"
```

or start over with `docker compose down -v` — which **deletes the database**, so
only do that before you have loaded real data.

**Dump fails with "Access denied ... PROCESS privilege".** You dropped
`--no-tablespaces`.

**Dump produces an empty file.** The VPS IP is not whitelisted in hPanel →
Remote MySQL, or `DB_HOST` still points somewhere unreachable.
