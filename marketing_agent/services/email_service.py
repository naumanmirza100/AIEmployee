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
            # For now, we'll use a relative URL that will be resolved by the view
            base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
            tracking_token = send_history.tracking_token
            
            # Add tracking pixel before </body> tag or at the end
            tracking_pixel_url = f"{base_url}/marketing/track/email/{tracking_token}/open/"
            tracking_pixel = f'<img src="{tracking_pixel_url}" width="1" height="1" style="display:none;" alt="" />'
            
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
                
                # Skip if already a tracking URL or mailto/tel/javascript/data links
                if ('track/email' in href or 
                    href.startswith('mailto:') or 
                    href.startswith('tel:') or 
                    href.startswith('javascript:') or
                    href.startswith('data:')):
                    return full_tag
                
                # URL encode the original href
                from urllib.parse import quote as url_quote
                encoded_href = url_quote(href, safe=':/?#[]@!$&\'()*+,;=')
                
                # Create tracked URL
                tracked_url = f"{base_url}/marketing/track/email/{tracking_token}/click/?url={encoded_href}"
                return full_tag.replace(href, tracked_url)
            
            # Find all <a href="..."> tags and wrap them (handles both single and double quotes)
            # Pattern: (<a...href=)(" or ')(url)(" or ')
            html_content = re.sub(r'(<a\s+[^>]*href=)(["\'])([^"\']+)\2', wrap_link, html_content, flags=re.IGNORECASE)
            
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

