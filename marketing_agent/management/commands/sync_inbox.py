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
from django.core.management.base import BaseCommand
from django.utils import timezone
from marketing_agent.models import EmailAccount, EmailSendHistory, CampaignContact, Reply, Campaign, Lead
from marketing_agent.views import mark_contact_replied
import logging
import re
from datetime import timedelta

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync inbox via IMAP and detect email replies automatically'

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

    def handle(self, *args, **options):
        account_id = options.get('account_id')
        dry_run = options.get('dry_run', False)
        
        self.stdout.write(self.style.SUCCESS('\n=== Starting IMAP Inbox Sync ===\n'))
        self.stdout.write(f'Current time: {timezone.now()}')
        
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
        
        # Get all active campaign leads (for filtering)
        active_campaigns = Campaign.objects.filter(status='active')
        campaign_leads = Lead.objects.filter(
            campaigns__in=active_campaigns
        ).distinct()
        known_lead_emails = set(lead.email.lower() for lead in campaign_leads)
        
        self.stdout.write(f'Found {len(known_lead_emails)} known lead email(s) from active campaigns')
        if known_lead_emails:
            self.stdout.write(f'   Will only process replies from these leads')
        
        total_replies_found = 0
        total_replies_processed = 0
        
        # Process each account
        for account in accounts:
            self.stdout.write(f'\n{"="*60}')
            self.stdout.write(f'Processing Account: {account.name} ({account.email})')
            self.stdout.write(f'{"="*60}')
            
            if not account.imap_host or not account.imap_username or not account.imap_password:
                self.stdout.write(self.style.WARNING(f'  [WARNING] IMAP settings incomplete for {account.email}. Skipping.'))
                continue
            
            try:
                replies_found, replies_processed = self.sync_account_inbox(account, dry_run, known_lead_emails)
                total_replies_found += replies_found
                total_replies_processed += replies_processed
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  [ERROR] Error syncing {account.email}: {str(e)}'))
                logger.error(f'Error syncing account {account.id} ({account.email}): {str(e)}', exc_info=True)
        
        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(self.style.SUCCESS(f'\n[OK] Sync Complete'))
        self.stdout.write(f'Total replies found: {total_replies_found}')
        self.stdout.write(f'Total replies processed: {total_replies_processed}')
        self.stdout.write(f'{"="*60}\n')

    def sync_account_inbox(self, account, dry_run=False, known_lead_emails=None):
        """
        Sync inbox for a single email account
        Only processes emails from known campaign leads (optimized for privacy & performance)
        """
        replies_found = 0
        replies_processed = 0
        
        if known_lead_emails is None:
            known_lead_emails = set()
        
        try:
            # Connect to IMAP server
            if account.imap_use_ssl:
                mail = imaplib.IMAP4_SSL(account.imap_host, account.imap_port or 993)
            else:
                mail = imaplib.IMAP4(account.imap_host, account.imap_port or 143)
                if account.imap_port == 143:
                    mail.starttls()  # Use STARTTLS for port 143
            
            # Login
            mail.login(account.imap_username, account.imap_password)
            self.stdout.write(f'  Connected to IMAP server: {account.imap_host}:{account.imap_port}')
            
            # Select inbox
            mail.select('INBOX')
            
            # Search for unread emails (last 7 days)
            since_date = (timezone.now() - timedelta(days=7)).strftime('%d-%b-%Y')
            status, messages = mail.search(None, f'(UNSEEN SINCE {since_date})')
            
            if status != 'OK':
                self.stdout.write(self.style.WARNING(f'   Failed to search inbox'))
                mail.logout()
                return replies_found, replies_processed
            
            email_ids = messages[0].split()
            
            if not email_ids:
                self.stdout.write(f'  [INFO] No unread emails found')
                mail.logout()
                return replies_found, replies_processed
            
            self.stdout.write(f'   Found {len(email_ids)} unread email(s)')
            
            emails_checked = 0
            emails_from_leads = 0
            
            # Process each email
            for email_id in email_ids:
                try:
                    # Fetch email headers first (lightweight check)
                    status, msg_data = mail.fetch(email_id, '(BODY.PEEK[HEADER])')
                    if status != 'OK':
                        continue
                    
                    header_data = msg_data[0][1]
                    msg_headers = email.message_from_bytes(header_data)
                    
                    # OPTIMIZATION: Check sender email first (before fetching full email)
                    sender_email = self.get_email_address(msg_headers['From'])
                    if not sender_email:
                        continue
                    
                    emails_checked += 1
                    
                    # Skip if not from a known lead (privacy & performance optimization)
                    if known_lead_emails and sender_email.lower() not in known_lead_emails:
                        continue  # Skip this email - not from a campaign lead
                    
                    emails_from_leads += 1
                    
                    # Fetch full email only if it's from a known lead
                    status, msg_data = mail.fetch(email_id, '(RFC822)')
                    if status != 'OK':
                        continue
                    
                    email_body = msg_data[0][1]
                    msg = email.message_from_bytes(email_body)
                    
                    # Check if this is a reply
                    is_reply, sent_email = self.detect_reply(msg, account)
                    
                    if is_reply and sent_email:
                        replies_found += 1
                        self.stdout.write(f'\n  [REPLY] Reply detected!')
                        self.stdout.write(f'     From: {sender_email}')
                        self.stdout.write(f'     Subject: {self.decode_header(msg["Subject"])}')
                        self.stdout.write(f'     Original Email: {sent_email.subject} (ID: {sent_email.id})')
                        
                        if not dry_run:
                            # Process reply
                            success = self.process_reply(msg, sent_email, account)
                            if success:
                                replies_processed += 1
                                self.stdout.write(f'     [OK] Reply processed successfully')
                                # Mark email as read (optional - comment out if you want to keep unread)
                                # mail.store(email_id, '+FLAGS', '\\Seen')
                            else:
                                self.stdout.write(f'     [ERROR] Failed to process reply')
                        else:
                            self.stdout.write(f'     [SKIP] Skipped (dry run)')
                    else:
                        # Email from lead but not a reply to campaign email
                        logger.debug(f'Email from lead {sender_email} is not a reply to campaign email')
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  [ERROR] Error processing email {email_id.decode()}: {str(e)}'))
                    logger.error(f'Error processing email {email_id.decode()}: {str(e)}', exc_info=True)
                    continue
            
            # Logout
            mail.logout()
            self.stdout.write(f'\n  [OK] Finished processing account: {account.email}')
            self.stdout.write(f'     Checked: {emails_checked} email(s), From leads: {emails_from_leads} email(s)')
            
        except imaplib.IMAP4.error as e:
            self.stdout.write(self.style.ERROR(f'  [ERROR] IMAP error: {str(e)}'))
            logger.error(f'IMAP error for account {account.id}: {str(e)}', exc_info=True)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  [ERROR] Error: {str(e)}'))
            logger.error(f'Error syncing account {account.id}: {str(e)}', exc_info=True)
        
        return replies_found, replies_processed

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
                    from email.utils import parsedate_to_datetime
                    reply_date = parsedate_to_datetime(date_str)
                    # Convert to timezone-aware datetime
                    if reply_date and timezone.is_naive(reply_date):
                        reply_date = timezone.make_aware(reply_date)
                except Exception as e:
                    logger.warning(f'Could not parse date: {str(e)}')
                    reply_date = timezone.now()
            else:
                reply_date = timezone.now()
            
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

    def get_email_address(self, header_value):
        """Extract email address from header value"""
        if not header_value:
            return None
        
        # Decode header
        decoded_header = decode_header(header_value)
        email_str = ''
        for part, encoding in decoded_header:
            if isinstance(part, bytes):
                email_str += part.decode(encoding or 'utf-8', errors='ignore')
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
                result += part.decode(encoding or 'utf-8', errors='ignore')
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
                            body = payload.decode(charset, errors='ignore')
                            break
                    except Exception as e:
                        logger.warning(f'Error decoding text/plain: {str(e)}')
                elif content_type == "text/html" and not body:
                    # Use HTML as fallback if no plain text
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            html_body = payload.decode(charset, errors='ignore')
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
                    body = payload.decode(charset, errors='ignore')
            except Exception as e:
                logger.warning(f'Error decoding body: {str(e)}')
        
        return body.strip()

