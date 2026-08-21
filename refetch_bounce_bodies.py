"""Re-fetch bodies for already-synced bounce (DSN) emails.

Rows synced before the get_email_body fix stored the *attached original*
message's body instead of the delivery-failure notice - an "Undelivered
Mail Returned to Sender" row would render as "testing".

This re-opens IMAP for each affected account, re-parses those messages
with the corrected parser, and updates body / body_html in place. Normal
mail is untouched: only rows whose message actually carries a
message/delivery-status part are rewritten.

Run it as a plain script (NOT `manage.py shell < ...`, which feeds the
file line-by-line into the REPL and breaks every indented block):

    python refetch_bounce_bodies.py

Add --dry-run to report what would change without writing anything.
"""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

import email
import imaplib

from django.db.models import Q

from reply_draft_agent.models import InboxEmail
from marketing_agent.management.commands.sync_inbox import Command as SyncCmd

cmd = SyncCmd()

DRY_RUN = '--dry-run' in sys.argv
if DRY_RUN:
    print('DRY RUN - no rows will be written.\n')

# Candidate rows: inbound mail that looks like a bounce notice. Subject /
# sender matching is only used to NARROW the IMAP work — the authoritative
# test is whether the fetched message really has a delivery-status part.
candidates = (
    InboxEmail.objects
    .filter(direction='in')
    .filter(
        Q(subject__icontains='undelivered')
        | Q(subject__icontains='returned to sender')
        | Q(subject__icontains='delivery status notification')
        | Q(subject__icontains='delivery failure')
        | Q(subject__icontains='failure notice')
        | Q(from_email__icontains='mailer-daemon')
        | Q(from_email__icontains='postmaster')
    )
    .select_related('email_account')
    .order_by('email_account_id')
)

total = candidates.count()
print(f'Found {total} candidate bounce row(s).')

updated = skipped = failed = 0
by_account = {}
for row in candidates:
    by_account.setdefault(row.email_account_id, []).append(row)

for account_id, rows in by_account.items():
    account = rows[0].email_account
    print(f'\n--- account {account.email} ({len(rows)} row(s)) ---')
    try:
        mail = imaplib.IMAP4_SSL(account.imap_host, account.imap_port or 993)
        mail.login(account.imap_username, account.imap_password)
        mail.select('INBOX')
    except Exception as e:
        print(f'  ! could not open IMAP: {e}')
        failed += len(rows)
        continue

    for row in rows:
        try:
            typ, data = mail.search(None, f'(HEADER Message-ID "{row.message_id}")')
            if typ != 'OK' or not data or not data[0]:
                print(f'  - not on server: {row.subject[:60]}')
                skipped += 1
                continue
            num = data[0].split()[0]
            typ, msg_data = mail.fetch(num, '(RFC822)')
            if typ != 'OK':
                skipped += 1
                continue
            msg = email.message_from_bytes(msg_data[0][1])

            # Authoritative check: is this really a DSN?
            if not cmd._extract_delivery_status(msg):
                print(f'  - not a DSN, left alone: {row.subject[:60]}')
                skipped += 1
                continue

            plain, html = cmd.get_email_body(msg)
            if not plain and not html:
                skipped += 1
                continue

            if DRY_RUN:
                print(f'  ~ would fix: {row.subject[:60]}')
                print(f'      old body: {(row.body or "")[:80]!r}')
                print(f'      new body: {plain[:80]!r}')
            else:
                row.body = plain
                row.body_html = html or ''
                row.save(update_fields=['body', 'body_html'])
                print(f'  + fixed: {row.subject[:60]}')
            updated += 1
        except Exception as e:
            print(f'  ! {row.subject[:40]}: {e}')
            failed += 1

    try:
        mail.logout()
    except Exception:
        pass

print(f'\nDone. updated={updated} skipped={skipped} failed={failed}')
