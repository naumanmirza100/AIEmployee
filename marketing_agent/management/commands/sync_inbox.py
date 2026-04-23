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
from email.header import decode_header
from email.utils import parsedate_to_datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import IntegrityError
from marketing_agent.models import EmailAccount, EmailSendHistory, CampaignContact, Reply, Campaign
from marketing_agent.views import mark_contact_replied
from reply_draft_agent.models import InboxEmail
import logging
import re
from datetime import timedelta

logger = logging.getLogger(__name__)


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
        Sync inbox for a single email account.

        Campaign replies (matched by In-Reply-To / References / Subject) go into
        the Reply table via the existing path. Every other incoming message is
        stored as an InboxEmail row so the Reply Draft Agent can surface the
        full mailbox for the last N days.
        """
        if since_days is None or since_days < 1:
            since_days = self.DEFAULT_SINCE_DAYS
        replies_found = 0
        replies_processed = 0
        inbox_stored = 0

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
            mail.select('INBOX')

            # Last N days of mail (both UNSEEN and SEEN). We rely on our own
            # Message-ID dedupe so reading mail in another client doesn't
            # cause the draft agent to miss messages.
            since_date = (timezone.now() - timedelta(days=since_days)).strftime('%d-%b-%Y')
            status, messages = mail.search(None, f'(SINCE {since_date})')

            if status != 'OK':
                self.stdout.write(self.style.WARNING(f'   Failed to search inbox'))
                mail.logout()
                return replies_found, replies_processed, inbox_stored

            email_ids = messages[0].split()

            if not email_ids:
                self.stdout.write(f'  [INFO] No emails in the last {since_days} day(s)')
                mail.logout()
                return replies_found, replies_processed, inbox_stored

            self.stdout.write(f'   Found {len(email_ids)} email(s) in the last {since_days} day(s)')

            emails_checked = 0
            emails_skipped_known = 0

            for email_id in email_ids:
                try:
                    # Stage 1: peek at headers only, bail out if we've already stored this Message-ID.
                    status, hdr_data = mail.fetch(email_id, '(BODY.PEEK[HEADER])')
                    if status != 'OK' or not hdr_data or not hdr_data[0]:
                        continue
                    hdr_msg = email.message_from_bytes(hdr_data[0][1])
                    msg_id_raw = (hdr_msg.get('Message-ID') or hdr_msg.get('Message-Id') or '').strip().strip('<>')
                    if msg_id_raw and InboxEmail.objects.filter(
                        email_account=account, message_id=msg_id_raw[:500]
                    ).exists():
                        emails_skipped_known += 1
                        continue

                    # Stage 2: full fetch for anything new.
                    status, msg_data = mail.fetch(email_id, '(RFC822)')
                    if status != 'OK':
                        continue

                    email_body = msg_data[0][1]
                    msg = email.message_from_bytes(email_body)

                    sender_email = self.get_email_address(msg.get('From', ''))
                    if not sender_email:
                        continue

                    emails_checked += 1

                    # Step 1: try to match as a campaign reply first.
                    is_reply, sent_email = self.detect_reply(msg, account)

                    if is_reply and sent_email:
                        replies_found += 1
                        self.stdout.write(f'\n  [REPLY] Campaign reply detected!')
                        self.stdout.write(f'     From: {sender_email}')
                        self.stdout.write(f'     Subject: {self.decode_header(msg.get("Subject", ""))}')
                        self.stdout.write(f'     Original Email: {sent_email.subject} (ID: {sent_email.id})')

                        if not dry_run:
                            if self.process_reply(msg, sent_email, account):
                                replies_processed += 1
                                self.stdout.write(f'     [OK] Reply processed successfully')
                            else:
                                self.stdout.write(f'     [ERROR] Failed to process reply')
                        else:
                            self.stdout.write(f'     [SKIP] Skipped (dry run)')
                        continue

                    # Step 2: generic inbox mail — store every message so the
                    # Reply Draft UI surfaces the full mailbox (last N days).
                    if dry_run:
                        continue

                    if self.store_inbox_email(msg, account, sender_email):
                        inbox_stored += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  [ERROR] Error processing email {email_id.decode()}: {str(e)}'))
                    logger.error(f'Error processing email {email_id.decode()}: {str(e)}', exc_info=True)
                    continue

            mail.logout()
            self.stdout.write(f'\n  [OK] Finished processing account: {account.email}')
            self.stdout.write(
                f'     Checked: {emails_checked} · Skipped (already known): {emails_skipped_known} · '
                f'Campaign replies: {replies_found} · Inbox stored: {inbox_stored}'
            )

        except imaplib.IMAP4.error as e:
            self.stdout.write(self.style.ERROR(f'  [ERROR] IMAP error: {str(e)}'))
            logger.error(f'IMAP error for account {account.id}: {str(e)}', exc_info=True)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  [ERROR] Error: {str(e)}'))
            logger.error(f'Error syncing account {account.id}: {str(e)}', exc_info=True)

        return replies_found, replies_processed, inbox_stored

    def store_inbox_email(self, msg, account, sender_email):
        """Persist a generic (non-campaign) inbox email. Idempotent on (account, Message-ID)."""
        message_id = (msg.get('Message-ID') or msg.get('Message-Id') or '').strip().strip('<>')
        if not message_id:
            # Synthesize a stable-ish id for messages without a Message-ID header
            # so dedupe still works across syncs.
            date_hint = msg.get('Date', '') or ''
            subj_hint = (msg.get('Subject', '') or '')[:60]
            message_id = f'synthetic-{hash((sender_email, date_hint, subj_hint)) & 0xffffffff:x}'

        if InboxEmail.objects.filter(email_account=account, message_id=message_id).exists():
            return False

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
        body = self.get_email_body(msg)
        in_reply_to = (msg.get('In-Reply-To', '') or '').strip()[:500]
        references = (msg.get('References', '') or '').strip()

        try:
            InboxEmail.objects.create(
                owner=account.owner,
                email_account=account,
                message_id=message_id[:500],
                in_reply_to=in_reply_to,
                references=references,
                from_email=sender_email,
                from_name=from_name[:255],
                subject=subject,
                body=body,
                received_at=received_at,
            )
            return True
        except IntegrityError:
            # Raced with a concurrent sync — treat as already stored.
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
            
            # Extract reply content
            reply_subject = self.decode_header(msg.get('Subject', ''))
            reply_content = self.get_email_body(msg)
            
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
        """Extract email body text"""
        body = ''
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # Skip attachments
                if "attachment" in content_disposition:
                    continue
                
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            body = self._safe_decode(payload, charset)
                            break
                    except Exception as e:
                        logger.warning(f'Error decoding text/plain: {str(e)}')
                elif content_type == "text/html" and not body:
                    # Use HTML as fallback if no plain text
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            html_body = self._safe_decode(payload, charset)
                            # Convert HTML to text (simple)
                            import re
                            body = re.sub(r'<[^>]+>', '', html_body)
                            break
                    except Exception as e:
                        logger.warning(f'Error decoding text/html: {str(e)}')
        else:
            # Not multipart
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or 'utf-8'
                    body = self._safe_decode(payload, charset)
            except Exception as e:
                logger.warning(f'Error decoding body: {str(e)}')
        
        return body.strip()

