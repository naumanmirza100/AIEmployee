"""
Email Service for Marketing Campaigns
Handles sending emails, spam prevention, A/B testing, and tracking
"""
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template import Context, Template
from django.conf import settings
from django.utils import timezone
from marketing_agent.models import Campaign, Lead, EmailTemplate, EmailSendHistory
import re
import time
from datetime import timedelta
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending campaign emails with spam prevention and tracking"""
    
    # Rate limiting: max emails per minute
    MAX_EMAILS_PER_MINUTE = 30
    
    def __init__(self):
        self.sent_count = 0
        self.minute_start = timezone.now()
    
    def check_rate_limit(self):
        """Check if we're within rate limits"""
        now = timezone.now()
        if (now - self.minute_start).total_seconds() >= 60:
            # Reset counter for new minute
            self.sent_count = 0
            self.minute_start = now
        
        if self.sent_count >= self.MAX_EMAILS_PER_MINUTE:
            # Wait until next minute
            wait_seconds = 60 - (now - self.minute_start).total_seconds()
            if wait_seconds > 0:
                time.sleep(wait_seconds)
                self.sent_count = 0
                self.minute_start = timezone.now()
    
    def calculate_spam_score(self, subject: str, html_content: str, text_content: str = '') -> float:
        """
        Calculate spam score for email content (0-100, lower is better)
        Checks for common spam triggers
        """
        score = 0.0
        content = (subject + ' ' + html_content + ' ' + text_content).lower()
        
        # All caps in subject
        if subject.isupper():
            score += 15
        
        # Excessive exclamation marks
        exclamation_count = subject.count('!')
        if exclamation_count > 2:
            score += 10
        
        # Spam trigger words
        spam_words = ['free', 'urgent', 'click here', 'limited time', 'act now', 
                     'guaranteed', 'no risk', 'winner', 'congratulations', 'prize']
        for word in spam_words:
            if word in content:
                score += 5
        
        # Excessive use of ALL CAPS in body
        caps_ratio = sum(1 for c in content[:500] if c.isupper()) / min(len(content[:500]), 500)
        if caps_ratio > 0.3:
            score += 15
        
        # Too many links
        link_count = len(re.findall(r'https?://', html_content))
        if link_count > 5:
            score += 10
        
        # Missing unsubscribe link
        if 'unsubscribe' not in content and 'opt-out' not in content:
            score += 20
        
        # Poor text-to-image ratio (if HTML has many images but little text)
        text_length = len(re.sub(r'<[^>]+>', '', html_content))
        if text_length < 100:
            score += 15
        
        # Check for suspicious patterns
        if re.search(r'\d{10,}', subject):  # Long numbers
            score += 10
        
        return min(score, 100.0)
    
    def render_email_content(self, template_content: str, context_vars: Dict) -> str:
        """Render email template with context variables"""
        try:
            from django.template import Engine, Context
            # Create template engine with autoescape disabled for HTML emails
            # But set undefined variables to empty string (Django default behavior)
            engine = Engine()
            template = engine.from_string(template_content)
            context = Context(context_vars, autoescape=False)
            rendered = template.render(context)
            # Remove any undefined variable patterns that might have rendered as empty
            # This shouldn't happen with Django templates, but just in case
            return rendered
        except Exception as e:
            logger.error(f"Error rendering email template: {str(e)}")
            # Fallback: simple string replacement
            content = template_content
            for key, value in context_vars.items():
                content = content.replace(f'{{{{{key}}}}}', str(value))
            # Also remove any remaining undefined variable patterns
            import re
            content = re.sub(r'\{\{[^}]+\}\}', '', content)
            return content
    
    def send_email(
        self, 
        template: EmailTemplate,
        lead: Lead,
        campaign: Campaign,
        test_email: Optional[str] = None,
        email_account: Optional['EmailAccount'] = None
    ) -> Dict:
        """
        Send email to a lead using a template
        
        Returns:
            Dict with success status, send_history_id, and any errors
        """
        recipient_email = test_email or lead.email
        
        # Prepare context variables
        context_vars = {
            'lead_name': lead.first_name or lead.email.split('@')[0],
            'lead_email': lead.email,
            'campaign_name': campaign.name,
            'lead_company': lead.company or '',
        }
        
        # Render email content
        try:
            subject = self.render_email_content(template.subject, context_vars)
            html_content = self.render_email_content(template.html_content, context_vars)
            text_content = template.text_content
            if text_content:
                text_content = self.render_email_content(text_content, context_vars)
            else:
                # Generate plain text from HTML
                text_content = re.sub(r'<[^>]+>', '', html_content)
        except Exception as e:
            logger.error(f"Error rendering email for lead {lead.id}: {str(e)}")
            return {
                'success': False,
                'error': f'Template rendering error: {str(e)}'
            }
        
        # Check rate limit
        self.check_rate_limit()
        
        # Create send history record
        send_history = EmailSendHistory.objects.create(
            campaign=campaign,
            lead=lead,
            email_template=template,
            subject=subject,
            recipient_email=recipient_email,
            status='pending',
            is_ab_test=False,  # A/B testing removed
            ab_test_variant='',
            is_followup=template.email_type == 'followup',
            followup_sequence_number=0,  # Sequences handle this now
        )
        
        # Generate tracking token
        send_history.tracking_token = send_history.generate_tracking_token()
        send_history.save()
        
        # Add tracking to HTML content
        html_content = self._add_email_tracking(html_content, send_history)
        
        # Send email
        try:
            # Use provided email account, or get default
            from marketing_agent.models import EmailAccount
            if not email_account:
                email_account = EmailAccount.objects.filter(
                    owner=campaign.owner,
                    is_active=True
            ).order_by('-is_default', '-created_at').first()
            
            if not email_account:
                raise ValueError('No active email account found. Please add an email account first.')
            
            from_email = email_account.email
            
            # Use custom SMTP backend if account is configured
            from django.core.mail.backends.smtp import EmailBackend
            
            smtp_backend = EmailBackend(
                host=email_account.smtp_host,
                port=email_account.smtp_port,
                username=email_account.smtp_username,
                password=email_account.smtp_password,
                use_tls=email_account.use_tls,
                use_ssl=email_account.use_ssl,
                fail_silently=False,
            )
            
            # Use EmailMultiAlternatives for HTML emails
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content or html_content,
                from_email=from_email,
                to=[recipient_email],
                connection=smtp_backend,
            )
            
            if html_content:
                email.attach_alternative(html_content, "text/html")
            
            email.send()
            
            # Update send history
            send_history.status = 'sent'
            send_history.sent_at = timezone.now()
            send_history.save()
            
            self.sent_count += 1
            
            # Update spam score if not already set
            if template.spam_score is None:
                spam_score = self.calculate_spam_score(subject, html_content, text_content)
                template.spam_score = spam_score
                template.save(update_fields=['spam_score'])
            
            logger.info(f"Email sent successfully to {recipient_email} (Campaign: {campaign.name}, Template: {template.name})")
            
            return {
                'success': True,
                'send_history_id': send_history.id,
                'message': 'Email sent successfully'
            }
            
        except Exception as e:
            # Update send history with error
            send_history.status = 'failed'
            send_history.error_message = str(e)
            send_history.save()
            
            logger.error(f"Error sending email to {recipient_email}: {str(e)}")
            
            return {
                'success': False,
                'error': str(e),
                'send_history_id': send_history.id
            }
    
    def _add_email_tracking(self, html_content: str, send_history: EmailSendHistory) -> str:
        """
        Add tracking pixel and wrap links with tracking URLs
        """
        from django.conf import settings
        from django.urls import reverse
        
        try:
            # Get base URL for tracking endpoints
            # Try multiple methods to get the correct base URL
            base_url = None
            
            # Method 1: Check SITE_URL setting (recommended)
            base_url = getattr(settings, 'SITE_URL', None)
            
            # Method 2: Try to get from ALLOWED_HOSTS
            if not base_url and hasattr(settings, 'ALLOWED_HOSTS') and settings.ALLOWED_HOSTS:
                host = settings.ALLOWED_HOSTS[0]
                if host != '*':
                    protocol = 'https' if getattr(settings, 'USE_HTTPS', False) else 'http'
                    # Add port for development if not specified
                    if ':' not in host and protocol == 'http':
                        base_url = f"{protocol}://{host}:8000"
                    else:
                        base_url = f"{protocol}://{host}"
            
            # Method 3: Final fallback to localhost (for development only)
            if not base_url:
                base_url = 'http://127.0.0.1:8000'  # Default for local development
                logger.warning(
                    f"SITE_URL not configured in settings. Using {base_url}. "
                    "Tracking URLs may not work from external email clients. "
                    "To fix: Add SITE_URL = 'http://your-domain.com' to settings.py or .env file"
                )
            
            # Clean up base_url - remove trailing slashes and any path components
            # SITE_URL should be just the domain (e.g., https://example.com), not https://example.com/marketing/
            base_url = base_url.rstrip('/')
            # If base_url ends with /marketing, remove it (tracking URLs are at root level)
            if base_url.endswith('/marketing'):
                base_url = base_url[:-9]  # Remove '/marketing'
            logger.info(f"[EMAIL TRACKING] Using base URL: {base_url}")
            
            tracking_token = send_history.tracking_token
            
            if not tracking_token:
                logger.error(f"No tracking token for EmailSendHistory {send_history.id}")
                return html_content
            
            # Add tracking pixel using simple token URL format: /token?t=TOKEN
            # This is simpler and works better with email clients
            tracking_pixel_url = f"{base_url}/token?t={tracking_token}"
            # Use multiple pixel methods for better email client compatibility
            # Some email clients block display:none, so we use multiple approaches
            tracking_pixel = (
                f'<img src="{tracking_pixel_url}" width="1" height="1" style="display:none; width:1px; height:1px; border:0;" alt="" />'
                f'<img src="{tracking_pixel_url}" width="1" height="1" border="0" alt="" style="position:absolute; visibility:hidden; width:1px; height:1px;" />'
            )
            
            # Try to inject before </body>
            if '</body>' in html_content.lower():
                html_content = re.sub(r'</body>', tracking_pixel + '</body>', html_content, flags=re.IGNORECASE)
            else:
                # If no body tag, append at the end
                html_content += tracking_pixel
            
            # Wrap all links with tracking URLs
            def wrap_link(match):
                full_tag = match.group(0)
                href = match.group(3)  # The URL part (group 3 in the regex below)
                
                logger.info(f"[EMAIL TRACKING] Processing link: {full_tag[:100]}... href={href}")
                
                # Skip if already a tracking URL or mailto/tel/javascript/data links
                if ('/token?' in href or 'track/email' in href or 
                    href.startswith('mailto:') or 
                    href.startswith('tel:') or 
                    href.startswith('javascript:') or
                    href.startswith('data:')):
                    logger.info(f"[EMAIL TRACKING] Skipping link (already tracked or special): {href}")
                    return full_tag
                
                # Handle anchor links (#) - convert to default campaign page
                original_href = href
                if href == '#' or href.strip() == '' or href.startswith('#'):
                    logger.warning(f"[EMAIL TRACKING] Found anchor link (href='{href}') - converting to campaign page")
                    # Default to campaign page if available
                    if send_history.campaign:
                        href = f'/marketing/campaigns/{send_history.campaign.id}/'
                    else:
                        href = '/marketing/'
                    logger.info(f"[EMAIL TRACKING] Converted anchor link: {original_href} -> {href}")
                
                # Make sure href is absolute if it's relative
                if not href.startswith('http://') and not href.startswith('https://'):
                    if href.startswith('/'):
                        # Already absolute path, keep as is for encoding
                        pass
                    else:
                        # Relative path, make it absolute
                        href = f'/{href}'
                
                # URL encode the href for the tracking URL
                from urllib.parse import quote as url_quote
                encoded_href = url_quote(href, safe=':/?#[]@!$&\'()*+,;=')
                
                # Create tracked URL using simple token format: /token?t=TOKEN&url=ORIGINAL_URL
                tracked_url = f"{base_url}/token?t={tracking_token}&url={encoded_href}"
                logger.info(f"[EMAIL TRACKING] Wrapping link: {original_href} -> {tracked_url}")
                
                # Replace the href in the full tag - use regex for reliable replacement
                # Match: href="original" or href='original' or href=original
                pattern = r'(href=)(["\']?)' + re.escape(original_href) + r'(\2)'
                replacement = r'\1\2' + tracked_url + r'\3'
                result = re.sub(pattern, replacement, full_tag, flags=re.IGNORECASE)
                
                logger.info(f"[EMAIL TRACKING] Link replaced: {full_tag[:80]}... -> {result[:80]}...")
                return result
            
            # Find all <a href="..."> tags and wrap them
            # Pattern handles: href="url", href='url', and href=url (without quotes)
            # Match: <a ... href="value" ...> or <a ... href='value' ...> or <a ... href=value ...>
            # Use non-greedy matching and handle special characters in href values
            html_content = re.sub(
                r'(<a\s+[^>]*?href\s*=\s*)(["\']?)([^"\'\s>]+?)(\2)',
                wrap_link,
                html_content,
                flags=re.IGNORECASE
            )
            
            # Also handle cases where href might have spaces or special formatting
            # Second pass for any links that might have been missed
            html_content = re.sub(
                r'(<a\s+[^>]*?href\s*=\s*)(["\'])([^"\']+?)(\2)',
                wrap_link,
                html_content,
                flags=re.IGNORECASE
            )
            
            # Log tracking info
            logger.info(
                f"[EMAIL TRACKING] Added tracking to email {send_history.id}, "
                f"Token: {tracking_token[:10]}..., "
                f"Pixel: {tracking_pixel_url}"
            )
            
        except Exception as e:
            logger.error(f"Error adding tracking to email: {str(e)}")
            # Continue without tracking if there's an error
        
        return html_content
    
    def select_ab_test_template(self, templates: List[EmailTemplate], lead_id: int) -> Optional[EmailTemplate]:
        """
        Select A/B test variant based on lead ID (deterministic selection)
        This ensures the same lead always gets the same variant
        """
        if not templates:
            return None
        
        # If no A/B testing, return first template
        ab_templates = [t for t in templates if t.is_ab_test]
        if not ab_templates:
            return templates[0] if templates else None
        
        # Deterministic selection based on lead ID
        variant_a = [t for t in ab_templates if t.ab_test_variant == 'A']
        variant_b = [t for t in ab_templates if t.ab_test_variant == 'B']
        
        if not variant_a or not variant_b:
            return templates[0] if templates else None
        
        # Use lead_id % 2 to split 50/50
        if lead_id % 2 == 0:
            return variant_a[0]
        else:
            return variant_b[0]
    
    def send_campaign_emails(
        self,
        campaign: Campaign,
        template: Optional[EmailTemplate] = None,
        limit: Optional[int] = None
    ) -> Dict:
        """
        DEPRECATED: This function is no longer used.
        Emails are now ONLY sent through email sequences via the send_sequence_emails management command.
        Templates are just templates - they are not sent individually.
        
        Send emails to all leads in a campaign
        
        Args:
            campaign: Campaign to send emails for
            template: Specific template to use (if None, uses first active initial template)
            limit: Maximum number of emails to send (None = all)
        
        Returns:
            Dict with results (sent, failed, total)
        """
        if campaign.status != 'active':
            return {
                'success': False,
                'error': 'Campaign must be active to send emails'
            }
        
        # Get template
        if not template:
            template = campaign.email_templates.filter(
                email_type='initial',
                is_active=True
            ).first()
            
            if not template:
                return {
                    'success': False,
                    'error': 'No active initial email template found for this campaign'
                }
        
        # Get leads
        leads = campaign.leads.all()
        if limit:
            leads = leads[:limit]
        
        results = {
            'total': leads.count(),
            'sent': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
        
        for lead in leads:
            # Check if initial email was already sent to this lead (prevent duplicates)
            already_sent = EmailSendHistory.objects.filter(
                campaign=campaign,
                lead=lead,
                email_template__email_type='initial'
            ).exists()
            
            if already_sent:
                results['skipped'] += 1
                continue
            
            result = self.send_email(template, lead, campaign)
            if result['success']:
                results['sent'] += 1
                # Update lead status
                if lead.status == 'new':
                    lead.status = 'contacted'
                    lead.save()
            else:
                results['failed'] += 1
                results['errors'].append({
                    'lead_email': lead.email,
                    'error': result.get('error', 'Unknown error')
                })
        
        results['success'] = results['failed'] == 0
        return results


# Singleton instance
email_service = EmailService()

