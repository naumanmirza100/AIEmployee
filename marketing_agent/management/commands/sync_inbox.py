"""
Django management command to sync inbox and detect email replies via IMAP.

This command should be run periodically (e.g., every 5 minutes via Windows Scheduler/Cron) to:
1. Connect to IMAP server (Hostinger)
2. Fetch unread emails from inbox
3. Detect replies using In-Reply-To and References headers (professional method)
4. Match replies with sent emails (EmailSendHistory)
5. Save replies and trigger sub-sequence logic

Usage:
    python manage.py sync_inbox
    python manage.py sync_inbox --account-id 1
"""

import imaplib
import email
from contextlib import contextmanager
from email.header import decode_header
from email.utils import parsedate_to_datetime
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import IntegrityError
from marketing_agent.models import EmailAccount, EmailSendHistory, CampaignContact, Reply, Campaign
from marketing_agent.views import mark_contact_replied
from reply_draft_agent.models import InboxEmail
import logging
import re
from datetime import timedelta

try:
    import redis as _redis
except ImportError:
    _redis = None

logger = logging.getLogger(__name__)


# Per-account lock: stops two sync_inbox runs from racing on the same
# EmailAccount. Without it, beat ticks every 5 min could overlap with
# a previous run that's still working through 200+ messages, causing
# `(email_account, message_id)` unique-constraint violations and noisy
# IntegrityError fallbacks.
_LOCK_TTL_SECONDS = 30 * 60  # 30 min — longer than any realistic single-account sync
_LOCK_KEY_PREFIX = 'sync_inbox_lock:account:'


def _get_redis_client():
    """Return a redis client built from CELERY_BROKER_URL, or None.

    We piggy-back on the celery broker connection rather than adding a
    new dependency. Returns None when redis isn't available (sqlite
    broker fallback) — callers degrade to no-locking.
    """
    if _redis is None:
        return None
    url = getattr(settings, 'CELERY_BROKER_URL', '') or ''
    if not url.startswith('redis://') and not url.startswith('rediss://'):
        return None
    try:
        return _redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
    except Exception:
        return None


@contextmanager
def _account_sync_lock(account_id):
    """Acquire an exclusive lock for syncing a single account.

    Yields True if acquired (proceed), False if another worker holds it
    (caller should skip). Auto-releases on exit; TTL prevents a crashed
    worker from locking the account forever.
    """
    client = _get_redis_client()
    if client is None:
        # No Redis → fall back to no-lock behavior. Single-worker setups
        # still work; multi-worker setups lose the protection but won't
        # be worse than before this change.
        yield True
        return

    key = f'{_LOCK_KEY_PREFIX}{account_id}'
    acquired = False
    try:
        acquired = bool(client.set(key, '1', nx=True, ex=_LOCK_TTL_SECONDS))
        yield acquired
    finally:
        if acquired:
            try:
                client.delete(key)
            except Exception:
                pass


class Command(BaseCommand):
    help = 'Sync inbox via IMAP and detect email replies automatically'

    # Fixed 120-day rolling window. The Reply Draft Agent's dropdown is a
    # pure view filter over already-cached rows, so we always pull the max
    # range here and let the UI slice it client-side.
    DEFAULT_SINCE_DAYS = 120

    def add_arguments(self, parser):
        parser.add_argument(
            '--account-id',
            type=int,
            help='Specific email account ID to sync (if not provided, syncs all accounts with IMAP enabled)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without actually processing replies',
        )
        parser.add_argument(
            '--since-days',
            type=int,
            default=None,
            help='Override every account\'s imap_sync_days for this run only. '
                 'If omitted, each EmailAccount uses its own configured window '
                 '(default 30). Pass a larger number for a one-shot backfill.',
        )

    def handle(self, *args, **options):
        account_id = options.get('account_id')
        dry_run = options.get('dry_run', False)
        # --since-days, when passed explicitly, overrides every account's own
        # imap_sync_days setting for this one run. Useful for one-off deep
        # syncs. When omitted, each account uses its configured window.
        cli_since_days = options.get('since_days')
        if cli_since_days is not None and cli_since_days < 1:
            cli_since_days = None

        self.stdout.write(self.style.SUCCESS('\n=== Starting IMAP Inbox Sync ===\n'))
        self.stdout.write(f'Current time: {timezone.now()}')
        if cli_since_days:
            self.stdout.write(f'IMAP window (CLI override): last {cli_since_days} day(s) for every account')
        else:
            self.stdout.write(f'IMAP window: last {self.DEFAULT_SINCE_DAYS} day(s) (fixed)')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] DRY RUN MODE - No replies will be processed\n'))
        
        # Get email accounts with IMAP sync enabled
        if account_id:
            accounts = EmailAccount.objects.filter(
                id=account_id,
                enable_imap_sync=True,
                is_active=True
            )
        else:
            accounts = EmailAccount.objects.filter(
                enable_imap_sync=True,
                is_active=True
            )
        
        if not accounts.exists():
            self.stdout.write(self.style.WARNING('[WARNING] No email accounts with IMAP sync enabled found.'))
            self.stdout.write(self.style.WARNING('[WARNING] Please enable IMAP sync in Email Accounts settings.'))
            return
        
        total_replies_found = 0
        total_replies_processed = 0
        total_inbox_stored = 0

        # Process each account
        for account in accounts:
            self.stdout.write(f'\n{"="*60}')
            self.stdout.write(f'Processing Account: {account.name} ({account.email})')
            self.stdout.write(f'{"="*60}')

            if not account.imap_host or not account.imap_username or not account.imap_password:
                self.stdout.write(self.style.WARNING(f'  [WARNING] IMAP settings incomplete for {account.email}. Skipping.'))
                continue

            # `imap_sync_days` on EmailAccount is retained for rollback safety
            # but no longer consulted — the rolling window is fixed at
            # DEFAULT_SINCE_DAYS. `--since-days` still works as a one-shot override.
            account_since_days = cli_since_days or self.DEFAULT_SINCE_DAYS
            self.stdout.write(f'  IMAP window for this account: last {account_since_days} day(s)')
            with _account_sync_lock(account.id) as got_lock:
                if not got_lock:
                    self.stdout.write(self.style.WARNING(
                        f'  [SKIP] Another sync is already running for account {account.id} ({account.email}); '
                        'skipping this tick to avoid duplicate-key races.'
                    ))
                    logger.info(
                        'sync_inbox: skipping account %s (%s) — lock held by another worker',
                        account.id, account.email,
                    )
                    continue
                try:
                    replies_found, replies_processed, inbox_stored = self.sync_account_inbox(
                        account, dry_run, since_days=account_since_days,
                    )
                    total_replies_found += replies_found
                    total_replies_processed += replies_processed
                    total_inbox_stored += inbox_stored
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  [ERROR] Error syncing {account.email}: {str(e)}'))
                    logger.error(f'Error syncing account {account.id} ({account.email}): {str(e)}', exc_info=True)

        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(self.style.SUCCESS(f'\n[OK] Sync Complete'))
        self.stdout.write(f'Total campaign replies found: {total_replies_found}')
        self.stdout.write(f'Total campaign replies processed: {total_replies_processed}')
        self.stdout.write(f'Total generic inbox emails stored: {total_inbox_stored}')
        self.stdout.write(f'{"="*60}\n')

    def sync_account_inbox(self, account, dry_run=False, since_days=None):
        """
        Sync mail for a single email account — INBOX (incoming) and Sent
        (outgoing) folders both land in the InboxEmail table, distinguished
        by the `direction` field ('in' / 'out').

        Campaign reply detection runs only for INBOX. Sent mail is stored
        as InboxEmail with direction='out' and is independent of campaign
        replies / EmailSendHistory by design.
        """
        if since_days is None or since_days < 1:
            since_days = self.DEFAULT_SINCE_DAYS

        # Re-verify the account still exists in DB. The instance we were
        # handed may be stale if a concurrent sync task / user-deletion
        # removed it between handle()'s queryset and this call. Without
        # this check every InboxEmail INSERT in the loop fails with a
        # FK violation and we waste minutes retrying.
        fresh_account = EmailAccount.objects.filter(pk=account.pk).first()
        if fresh_account is None:
            self.stdout.write(self.style.WARNING(
                f'  [SKIP] Account {account.id} ({account.email}) no longer exists in DB — skipping sync.'
            ))
            return 0, 0, 0
        account = fresh_account

        # Strict separation: only the dedicated reply-agent account writes
        # to the InboxEmail table. Marketing-campaign accounts still need
        # IMAP for campaign reply detection (writes to Reply, not InboxEmail)
        # but their generic mail must not pollute the reply-draft inbox.
        is_reply_agent = bool(getattr(account, 'is_reply_agent_account', False))

        total_replies_found = 0
        total_replies_processed = 0
        total_inbox_stored = 0

        try:
            # Connect to IMAP server
            if account.imap_use_ssl:
                mail = imaplib.IMAP4_SSL(account.imap_host, account.imap_port or 993)
            else:
                mail = imaplib.IMAP4(account.imap_host, account.imap_port or 143)
                if account.imap_port == 143:
                    mail.starttls()  # Use STARTTLS for port 143

            mail.login(account.imap_username, account.imap_password)
            self.stdout.write(f'  Connected to IMAP server: {account.imap_host}:{account.imap_port}')

            # Preload existing Message-IDs ONCE for the whole account, shared
            # across INBOX + Sent. The unique (email_account, message_id)
            # constraint means a self-CC (same Message-ID in both folders)
            # is stored exactly once — first folder processed wins the
            # direction, and we process INBOX first.
            known_message_ids = set(
                InboxEmail.objects
                .filter(email_account=account)
                .values_list('message_id', flat=True)
            )
            self.stdout.write(f'  [INFO] {len(known_message_ids)} message(s) already cached for this account')
            if not is_reply_agent:
                self.stdout.write(
                    '  [INFO] Marketing-only account: campaign reply detection runs '
                    'on INBOX, but no InboxEmail rows are written and Sent is skipped.'
                )

            # 1) INBOX — incoming mail + campaign reply detection
            in_replies_found, in_replies_processed, in_inbox_stored = self._process_folder(
                mail, account, 'INBOX', 'in', dry_run, since_days, known_message_ids,
                store_inbox_rows=is_reply_agent,
            )
            total_replies_found += in_replies_found
            total_replies_processed += in_replies_processed
            total_inbox_stored += in_inbox_stored

            # 2) Sent folder — only synced for the reply-agent account.
            # Marketing accounts have no use for Sent storage (campaigns
            # already track outgoing mail via EmailSendHistory) and must
            # stay out of the InboxEmail table per the reply/marketing
            # separation rule.
            if is_reply_agent:
                sent_folder = self._find_sent_folder(mail)
                if sent_folder:
                    self.stdout.write(f'  Sent folder detected: {sent_folder!r}')
                    _, _, out_inbox_stored = self._process_folder(
                        mail, account, sent_folder, 'out', dry_run, since_days, known_message_ids,
                        store_inbox_rows=True,
                    )
                    total_inbox_stored += out_inbox_stored
                else:
                    self.stdout.write('  [INFO] Sent folder not found via common names; skipping sent sync')
            else:
                self.stdout.write('  [INFO] Skipping Sent sync (marketing account)')

            try:
                mail.close()
            except Exception:
                pass
            mail.logout()
            self.stdout.write(f'\n  [OK] Finished processing account: {account.email}')
            self.stdout.write(
                f'     Campaign replies: {total_replies_found} '
                f'(processed {total_replies_processed}) · Inbox stored: {total_inbox_stored}'
            )

        except imaplib.IMAP4.error as e:
            self.stdout.write(self.style.ERROR(f'  [ERROR] IMAP error: {str(e)}'))
            logger.error(f'IMAP error for account {account.id}: {str(e)}', exc_info=True)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  [ERROR] Error: {str(e)}'))
            logger.error(f'Error syncing account {account.id}: {str(e)}', exc_info=True)

        return total_replies_found, total_replies_processed, total_inbox_stored

    def _find_sent_folder(self, mail):
        """Locate the IMAP Sent-mail folder by probing common names.

        IMAP doesn't have a universal name for Sent — Gmail uses
        '[Gmail]/Sent Mail', Outlook/Exchange uses 'Sent Items', generic
        IMAP servers use 'Sent', etc. RFC 6154's \\Sent special-use flag
        has uneven server support, so we just SELECT each candidate
        readonly until one opens. Returns the folder name as it should
        be passed to mail.select() later.
        """
        candidates = [
            '[Gmail]/Sent Mail',     # Gmail (English UI)
            'Sent',                   # Generic IMAP / Hostinger / cPanel
            'Sent Items',             # Outlook / Exchange / Office 365
            'Sent Messages',          # Apple Mail / iCloud
            'INBOX.Sent',             # Some Courier IMAP servers
            'Sent Mail',              # Older format
        ]
        for name in candidates:
            try:
                # Quote names with spaces / brackets — IMAP requires it.
                status, _ = mail.select(f'"{name}"', readonly=True)
                if status == 'OK':
                    return name
            except Exception:
                continue
        return None

    def _process_folder(self, mail, account, folder_label, direction, dry_run, since_days, known_message_ids, store_inbox_rows=True):
        """Pull mail from one IMAP folder and store as InboxEmail rows.

        direction='in'  → INBOX flow. Each message runs through detect_reply;
                          campaign matches go to the Reply table, the rest
                          land as InboxEmail rows with direction='in'.
        direction='out' → Sent flow. No reply detection — sent mail can't
                          be a "reply to a campaign we sent" in the inbound
                          sense. from_email becomes the account's own
                          address; to_email is parsed from the To: header.

        store_inbox_rows=False is used for marketing-only accounts: we still
        run campaign reply detection on INBOX (writes to Reply), but no
        InboxEmail row is built — the reply-draft inbox stays exclusive to
        the dedicated reply-agent account.

        known_message_ids is shared with the caller and updated in-place so
        cross-folder dedupe spans the whole account.
        """
        # IMAP folder names with spaces or brackets must be quoted.
        select_arg = f'"{folder_label}"' if folder_label != 'INBOX' else 'INBOX'
        status, _ = mail.select(select_arg)
        if status != 'OK':
            self.stdout.write(self.style.WARNING(f'   Failed to select folder {folder_label!r}; skipping'))
            return 0, 0, 0

        since_date = (timezone.now() - timedelta(days=since_days)).strftime('%d-%b-%Y')
        status, messages = mail.search(None, f'(SINCE {since_date})')
        if status != 'OK':
            self.stdout.write(self.style.WARNING(f'   Failed to search folder {folder_label!r}'))
            return 0, 0, 0

        # Newest first so the UI's recent-window view fills progressively.
        email_ids = list(reversed(messages[0].split()))
        if not email_ids:
            self.stdout.write(f'  [INFO] No emails in folder {folder_label!r} for the last {since_days} day(s)')
            return 0, 0, 0

        self.stdout.write(
            f'   [{folder_label}] Found {len(email_ids)} email(s) in the last {since_days} day(s) '
            f'(direction={direction!r}, processing newest first)'
        )

        replies_found = 0
        replies_processed = 0
        inbox_stored = 0
        emails_checked = 0
        emails_skipped_known = 0

        # Buffer InboxEmail rows and flush via bulk_create.
        pending_inbox_rows = []
        BULK_FLUSH_SIZE = 50

        # IMAP fetch batching — one round-trip handles many messages.
        HEADER_BATCH_SIZE = 100
        RFC_BATCH_SIZE = 20

        own_address = (account.email or '').lower()
        total_to_process = len(email_ids)

        for chunk_start in range(0, total_to_process, HEADER_BATCH_SIZE):
            chunk = email_ids[chunk_start:chunk_start + HEADER_BATCH_SIZE]

            # Stage 1: batched header peek (just MESSAGE-ID for dedupe).
            headers_by_eid = {}
            try:
                seq = b','.join(chunk)
                status, hdr_data = mail.fetch(seq, '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])')
                if status == 'OK':
                    headers_by_eid = self._parse_imap_fetch(hdr_data)
            except Exception as e:
                logger.error(f'[{folder_label}] Batched header fetch failed at chunk {chunk_start}: {e}', exc_info=True)

            # Stage 2: split chunk into known (skip) and unknown (need RFC822).
            unknown_in_chunk = []
            for eid in chunk:
                hdr_bytes = headers_by_eid.get(eid)
                if hdr_bytes:
                    try:
                        hdr_msg = email.message_from_bytes(hdr_bytes)
                        mid = (hdr_msg.get('Message-ID') or hdr_msg.get('Message-Id') or '').strip().strip('<>')
                        if mid and mid[:500] in known_message_ids:
                            emails_skipped_known += 1
                            continue
                    except Exception:
                        pass
                unknown_in_chunk.append(eid)

            # Stage 3: batched RFC822 for unknowns.
            for sub_start in range(0, len(unknown_in_chunk), RFC_BATCH_SIZE):
                sub_chunk = unknown_in_chunk[sub_start:sub_start + RFC_BATCH_SIZE]
                if not sub_chunk:
                    continue

                msgs_by_eid = {}
                try:
                    seq2 = b','.join(sub_chunk)
                    status, msg_data = mail.fetch(seq2, '(RFC822)')
                    if status == 'OK':
                        msgs_by_eid = self._parse_imap_fetch(msg_data)
                except Exception as e:
                    logger.error(f'[{folder_label}] Batched RFC822 fetch failed: {e}', exc_info=True)
                    continue

                for eid in sub_chunk:
                    try:
                        msg_bytes = msgs_by_eid.get(eid)
                        if not msg_bytes:
                            continue
                        msg = email.message_from_bytes(msg_bytes)

                        # Direction-aware addressing. For incoming mail the
                        # From: header carries the sender; for outgoing mail
                        # the From: is us and the To: header has the recipient.
                        if direction == 'in':
                            from_addr = self.get_email_address(msg.get('From', ''))
                            to_addr = own_address
                        else:
                            from_addr = own_address
                            to_addr = self.get_email_address(msg.get('To', '')) or ''

                        if not from_addr:
                            continue

                        emails_checked += 1

                        # Campaign reply detection only on incoming mail.
                        if direction == 'in':
                            is_reply, sent_email = self.detect_reply(msg, account)
                            if is_reply and sent_email:
                                replies_found += 1
                                self.stdout.write(f'\n  [REPLY] Campaign reply detected!')
                                self.stdout.write(f'     From: {from_addr}')
                                self.stdout.write(f'     Subject: {self.decode_header(msg.get("Subject", ""))}')
                                self.stdout.write(f'     Original Email: {sent_email.subject} (ID: {sent_email.id})')
                                if not dry_run:
                                    if pending_inbox_rows:
                                        inbox_stored += self._flush_inbox_rows(pending_inbox_rows)
                                    if self.process_reply(msg, sent_email, account):
                                        replies_processed += 1
                                        self.stdout.write(f'     [OK] Reply processed successfully')
                                    else:
                                        self.stdout.write(f'     [ERROR] Failed to process reply')
                                else:
                                    self.stdout.write(f'     [SKIP] Skipped (dry run)')
                                continue

                        if dry_run:
                            continue

                        # Marketing-only accounts run reply detection above
                        # but never write to InboxEmail — that table is
                        # exclusive to the reply-draft agent's dedicated
                        # account.
                        if not store_inbox_rows:
                            continue

                        row = self._build_inbox_email(
                            msg, account, from_addr,
                            to_email=to_addr,
                            direction=direction,
                        )
                        if row and row.message_id not in known_message_ids:
                            pending_inbox_rows.append(row)
                            known_message_ids.add(row.message_id)
                            if len(pending_inbox_rows) >= BULK_FLUSH_SIZE:
                                inbox_stored += self._flush_inbox_rows(pending_inbox_rows)
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'  [ERROR] [{folder_label}] Error processing email {eid.decode()}: {str(e)}'))
                        logger.error(f'[{folder_label}] Error processing email {eid.decode()}: {str(e)}', exc_info=True)
                        continue

            # Progress heartbeat per chunk
            processed_so_far = min(chunk_start + HEADER_BATCH_SIZE, total_to_process)
            self.stdout.write(
                f'  [PROGRESS {folder_label}] {processed_so_far}/{total_to_process}  '
                f'checked={emails_checked}  skipped={emails_skipped_known}  '
                f'stored={inbox_stored + len(pending_inbox_rows)}  replies={replies_found}'
            )

        # Final flush for this folder
        if pending_inbox_rows:
            inbox_stored += self._flush_inbox_rows(pending_inbox_rows)

        return replies_found, replies_processed, inbox_stored

    @staticmethod
    def _parse_imap_fetch(fetch_data):
        """Parse imaplib's multi-message FETCH response into {seq_id_bytes: payload_bytes}.

        imaplib returns a list that mixes tuples (where the body literal is)
        with stand-alone bytes (the closing parens). For each message we get:
            (b'42 (RFC822 {12345}', b'<actual message bytes>'),
            b')',
        We pull the leading sequence number out of the descriptor so the
        caller can look up payloads by the same id it sent in the request,
        regardless of the order the server returned them.
        """
        result = {}
        for entry in fetch_data:
            if not isinstance(entry, tuple) or len(entry) < 2:
                continue
            descriptor, payload = entry[0], entry[1]
            if not isinstance(descriptor, (bytes, bytearray)) or not isinstance(payload, (bytes, bytearray)):
                continue
            m = re.match(rb'\s*(\d+)\s', descriptor)
            if m:
                result[m.group(1)] = bytes(payload)
        return result

    def _build_inbox_email(self, msg, account, from_email, *, to_email=None, direction='in'):
        """Construct (but do not save) an InboxEmail instance from a parsed message.

        from_email is the sender (always — for direction='out' the caller
        passes the account's own address). to_email defaults to the
        account's own address (the typical case for direction='in') and
        is parsed from the To: header by the caller for direction='out'.
        direction is stored verbatim and lets the list endpoint split
        Inbox vs Sent views.
        """
        message_id = (msg.get('Message-ID') or msg.get('Message-Id') or '').strip().strip('<>')
        if not message_id:
            # Synthesize a stable-ish id for messages without a Message-ID header
            # so dedupe still works across syncs.
            date_hint = msg.get('Date', '') or ''
            subj_hint = (msg.get('Subject', '') or '')[:60]
            message_id = f'synthetic-{hash((from_email, date_hint, subj_hint)) & 0xffffffff:x}'

        received_at = timezone.now()
        date_str = msg.get('Date')
        if date_str:
            try:
                parsed = parsedate_to_datetime(date_str)
                if parsed:
                    if timezone.is_naive(parsed):
                        parsed = timezone.make_aware(parsed)
                    received_at = parsed
            except Exception:
                pass

        from_header = msg.get('From', '') or ''
        from_name = ''
        m = re.match(r'\s*"?([^"<]+?)"?\s*<', from_header)
        if m:
            from_name = m.group(1).strip()

        subject = self.decode_header(msg.get('Subject', ''))[:500]
        body, body_html = self.get_email_body(msg)
        in_reply_to = (msg.get('In-Reply-To', '') or '').strip()[:500]
        references = (msg.get('References', '') or '').strip()

        # Default to_email = the account address (correct for incoming mail).
        if to_email is None:
            to_email = (account.email or '')

        return InboxEmail(
            owner=account.owner,
            email_account=account,
            message_id=message_id[:500],
            in_reply_to=in_reply_to,
            references=references,
            from_email=from_email,
            from_name=from_name[:255],
            subject=subject,
            body=body,
            body_html=body_html,
            received_at=received_at,
            to_email=(to_email or '')[:254],
            direction=direction,
        )

    def _flush_inbox_rows(self, pending_rows):
        """Bulk-insert buffered InboxEmail rows. Returns the count flushed.

        SQL Server's mssql backend has had a few foot-guns here historically
        (no ignore_conflicts, ARITHABORT/OUTPUT clause oddities, DataError on
        4000-char-plus subjects, etc.) so we catch *any* exception from
        bulk_create — not just IntegrityError — and fall back to per-row
        save() so the rest of the batch still lands. The log lines below
        surface the real failure if anything still slips through.
        pending_rows is always cleared so the buffer can't poison the next
        batch.

        FK-violation special case: if the email_account row was deleted while
        sync was running, every insert in this batch (and every batch after)
        will fail the same way. Detecting that and re-raising lets the outer
        loop abort instead of burning minutes retrying 2000+ doomed rows.
        """
        if not pending_rows:
            return 0
        try:
            InboxEmail.objects.bulk_create(pending_rows, batch_size=50)
            flushed = len(pending_rows)
        except Exception as e:
            err_text = str(e)
            if 'FOREIGN KEY constraint' in err_text and 'emailaccount' in err_text.lower():
                # The account row vanished mid-sync. Per-row retries are pointless —
                # they'll all hit the same FK miss. Clear the buffer and bail.
                logger.error(
                    'sync_inbox: email_account FK violation — account was deleted '
                    'mid-sync, aborting this account. (%s)', err_text[:300]
                )
                pending_rows.clear()
                raise
            logger.warning(
                'sync_inbox bulk_create failed (%s: %s); falling back to per-row save for %d rows',
                type(e).__name__, e, len(pending_rows)
            )
            flushed = 0
            for row in pending_rows:
                try:
                    row.save()
                    flushed += 1
                except Exception as inner_e:
                    logger.warning(
                        'sync_inbox per-row save failed for message_id=%r: %s: %s',
                        (row.message_id or '')[:60], type(inner_e).__name__, inner_e
                    )
        finally:
            pending_rows.clear()
        return flushed

    def store_inbox_email(self, msg, account, sender_email):
        """Persist a single incoming inbox email. Idempotent on (account, Message-ID).

        Retained for callers outside the batched sync loop. Always writes
        as direction='in' — Sent-folder mail goes through the batched
        _process_folder path, not this one.
        """
        row = self._build_inbox_email(msg, account, sender_email, direction='in')
        if row is None:
            return False
        if InboxEmail.objects.filter(email_account=account, message_id=row.message_id).exists():
            return False
        try:
            row.save()
            return True
        except IntegrityError:
            return False

    def detect_reply(self, msg, account):
        """
        Detect if email is a reply using professional method:
        1. Check In-Reply-To header (PRIMARY)
        2. Check References header (SECONDARY)
        3. Fallback: Check Subject for "Re:" (optional safety)
        """
        in_reply_to = msg.get('In-Reply-To', '').strip()
        references = msg.get('References', '').strip()
        subject = self.decode_header(msg.get('Subject', ''))
        
        # PRIMARY: Check In-Reply-To header
        if in_reply_to:
            # Remove < > brackets
            message_id = in_reply_to.strip('<>')
            sent_email = EmailSendHistory.objects.filter(
                message_id=message_id
            ).first()
            
            if sent_email:
                logger.info(f'Reply detected via In-Reply-To header: {message_id}')
                return True, sent_email
        
        # SECONDARY: Check References header
        if references:
            # References can contain multiple Message-IDs (space-separated)
            ref_message_ids = re.findall(r'<([^>]+)>', references)
            for message_id in ref_message_ids:
                sent_email = EmailSendHistory.objects.filter(
                    message_id=message_id
                ).first()
                
                if sent_email:
                    logger.info(f'Reply detected via References header: {message_id}')
                    return True, sent_email
        
        # FALLBACK: Check Subject for "Re:" (optional safety)
        if subject and subject.lower().startswith('re:'):
            # Try to match by subject and sender
            sender_email = self.get_email_address(msg['From'])
            if sender_email:
                # Get recent sent emails (last 14 days) to this sender
                fourteen_days_ago = timezone.now() - timedelta(days=14)
                subject_without_re = re.sub(r'^(re:|fw:|fwd:)\s*', '', subject, flags=re.IGNORECASE).strip()
                
                sent_emails = EmailSendHistory.objects.filter(
                    recipient_email=sender_email,
                    sent_at__gte=fourteen_days_ago,
                    status__in=['sent', 'delivered', 'opened', 'clicked']
                ).order_by('-sent_at')[:10]
                
                for sent_email in sent_emails:
                    sent_subject = re.sub(r'^(re:|fw:|fwd:)\s*', '', sent_email.subject, flags=re.IGNORECASE).strip()
                    if sent_subject.lower() == subject_without_re.lower():
                        logger.info(f'Reply detected via Subject fallback: {subject}')
                        return True, sent_email
        
        return False, None

    def process_reply(self, msg, sent_email, account):
        """
        Process a detected reply:
        1. Extract reply content
        2. Call mark_contact_replied to trigger sub-sequence logic
        """
        try:
            # Get sender email
            sender_email = self.get_email_address(msg['From'])
            if not sender_email:
                logger.error('Could not extract sender email from reply')
                return False
            
            # Get campaign and lead from sent email
            campaign = sent_email.campaign
            lead = sent_email.lead
            
            # Get or create CampaignContact
            contact = CampaignContact.objects.filter(
                campaign=campaign,
                lead=lead
            ).first()
            
            if not contact:
                logger.warning(f'CampaignContact not found for campaign {campaign.id}, lead {lead.id}')
                return False
            
            # Extract reply content. Reply (campaign-side) only stores the
            # plain text — HTML body goes to InboxEmail rows; campaigns
            # don't render replies as HTML in the marketing dashboard.
            reply_subject = self.decode_header(msg.get('Subject', ''))
            reply_content, _reply_html_unused = self.get_email_body(msg)

            # Get reply date
            reply_date = None
            date_str = msg.get('Date')
            if date_str:
                try:
                    reply_date = parsedate_to_datetime(date_str)
                    # Convert to timezone-aware datetime
                    if reply_date and timezone.is_naive(reply_date):
                        reply_date = timezone.make_aware(reply_date)
                except Exception as e:
                    logger.warning(f'Could not parse date: {str(e)}')
                    reply_date = timezone.now()
            else:
                reply_date = timezone.now()

            # Dedupe: skip if we've already stored a Reply for this exact incoming message.
            # Keyed on (campaign, lead, subject, replied_at within 2 min). We intentionally
            # exclude triggering_email from the filter because multiple EmailSendHistory
            # rows can share a Message-ID (re-sends), which made detect_reply return a
            # different sent_email each run and broke dedupe.
            dedupe_window_start = reply_date - timedelta(minutes=2)
            dedupe_window_end = reply_date + timedelta(minutes=2)
            if Reply.objects.filter(
                campaign=campaign,
                lead=lead,
                reply_subject=reply_subject,
                replied_at__gte=dedupe_window_start,
                replied_at__lte=dedupe_window_end,
            ).exists():
                logger.info(f'Skipping duplicate reply for {sender_email} (already stored)')
                return True

            # Call process_reply_directly service function (avoids middleware/HTTP issues)
            from marketing_agent.services.reply_processor import process_reply_directly
            
            result = process_reply_directly(
                campaign=campaign,
                lead=lead,
                reply_subject=reply_subject,
                reply_content=reply_content,
                reply_date=reply_date
            )
            
            if result.get('success'):
                logger.info(f'Reply processed successfully for {sender_email}: {result.get("message", "")}')
                return True
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f'Failed to process reply: {error_msg}')
                return False
            
        except Exception as e:
            logger.error(f'Error processing reply: {str(e)}', exc_info=True)
            return False

    @staticmethod
    def _safe_decode(raw, encoding):
        """Decode bytes while tolerating bogus encoding labels from malformed mail.

        Some clients produce headers like 'unknown-8bit' which Python cannot
        resolve — LookupError here would bubble up and break the whole sync.
        """
        if not isinstance(raw, (bytes, bytearray)):
            return raw
        candidates = [encoding, 'utf-8', 'latin-1']
        for enc in candidates:
            if not enc:
                continue
            try:
                return raw.decode(enc, errors='ignore')
            except (LookupError, UnicodeDecodeError):
                continue
        return raw.decode('latin-1', errors='ignore')

    def get_email_address(self, header_value):
        """Extract email address from header value"""
        if not header_value:
            return None

        decoded_header = decode_header(header_value)
        email_str = ''
        for part, encoding in decoded_header:
            if isinstance(part, bytes):
                email_str += self._safe_decode(part, encoding or 'utf-8')
            else:
                email_str += part

        # Extract email from string like "Name <email@example.com>" or "email@example.com"
        match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', email_str)
        if match:
            return match.group(0).lower()

        return None

    def decode_header(self, header_value):
        """Decode email header value"""
        if not header_value:
            return ''

        decoded_header = decode_header(header_value)
        result = ''
        for part, encoding in decoded_header:
            if isinstance(part, bytes):
                result += self._safe_decode(part, encoding or 'utf-8')
            else:
                result += part

        return result.strip()

    def get_email_body(self, msg):
        """Extract email body — both plain text and HTML when present.

        Returns a tuple ``(plain, html)``.

        - ``plain`` is what we use for AI analysis, search, and reply-quote
          parsing — straight UTF-8 text, no markup. If the source only had
          HTML, ``plain`` is generated by stripping tags so downstream
          consumers always get something to read.
        - ``html`` is the raw HTML body when the source provided one. The
          UI renders this for visual fidelity (formatted layouts, links,
          images, signatures). When the source is plain-text-only, this
          is empty and the UI falls back to ``plain``.
        """
        plain = ''
        html = ''

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain" and not plain:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            plain = self._safe_decode(payload, charset)
                    except Exception as e:
                        logger.warning(f'Error decoding text/plain: {str(e)}')
                elif content_type == "text/html" and not html:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            html = self._safe_decode(payload, charset)
                    except Exception as e:
                        logger.warning(f'Error decoding text/html: {str(e)}')

                # Stop walking once we have both — saves time on multipart
                # messages with many alternative parts.
                if plain and html:
                    break
        else:
            # Single-part message. Branch on content type so we don't lose
            # the HTML when the source is HTML-only (transactional / OTP
            # mail is often shipped this way).
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or 'utf-8'
                    decoded = self._safe_decode(payload, charset)
                    if (msg.get_content_type() or '').lower() == 'text/html':
                        html = decoded
                    else:
                        plain = decoded
            except Exception as e:
                logger.warning(f'Error decoding body: {str(e)}')

        # Make sure plain is always populated. Tag-strip HTML when it's
        # the only thing the message had.
        if html and not plain:
            plain = re.sub(r'<[^>]+>', '', html)

        return plain, html

        return body.strip()

