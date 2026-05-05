"""
SDR Outreach Agent
-------------------
Generates AI-personalised email content and sends outreach for campaign enrollments.
Polls IMAP inbox for replies, classifies sentiment with AI, and hands off positive
replies to the scheduling agent (creates SDRMeeting + sends calendar invite email).

Email steps: sent via SMTP using campaign credentials or global env settings.
LinkedIn steps: logged as a manual-action note.
"""

import email as email_lib
import email.utils
import imaplib
import json
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert B2B sales email writer. "
    "Write concise, personalised, high-converting outreach. "
    "Return ONLY valid JSON — no markdown, no extra text."
)


class OutreachAgent:
    """Generates personalised outreach, sends campaign steps, detects replies."""

    def __init__(self):
        groq_key = (
            getattr(settings, 'GROQ_API_KEY', None)
            or getattr(settings, 'GROQ_REC_API_KEY', None)
            or os.environ.get('GROQ_API_KEY', '')
            or os.environ.get('GROQ_REC_API_KEY', '')
        ).strip()

        self.groq_client = None
        if groq_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=groq_key)
            except Exception as exc:
                logger.error("Groq init failed in OutreachAgent: %s", exc)

        self.model = getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant')

    # ------------------------------------------------------------------
    # Step generation
    # ------------------------------------------------------------------

    def generate_campaign_steps(self, campaign, icp=None) -> list:
        if self.groq_client:
            try:
                return self._ai_generate_steps(campaign, icp)
            except Exception as exc:
                logger.warning("AI step generation failed, using defaults: %s", exc)
        return self._default_steps(campaign)

    def _ai_generate_steps(self, campaign, icp) -> list:
        industry = ', '.join(icp.industries[:3]) if icp and icp.industries else 'B2B'
        titles = ', '.join(icp.job_titles[:3]) if icp and icp.job_titles else 'decision makers'

        prompt = f"""Generate a 4-step B2B outreach sequence.

Sender: {campaign.sender_name or 'Sales Rep'}, {campaign.sender_title or 'Account Executive'} at {campaign.sender_company or 'our company'}
Target audience: {titles} in {industry}
Campaign goal: {campaign.description or campaign.name}

Return exactly this JSON array (4 objects):
[
  {{"step_order":1,"step_type":"email","delay_days":1,"name":"Introduction","subject_template":"...","body_template":"..."}},
  {{"step_order":2,"step_type":"linkedin","delay_days":3,"name":"LinkedIn Connect","subject_template":"","body_template":"Send a LinkedIn connection request to {{first_name}} at {{company_name}}"}},
  {{"step_order":3,"step_type":"email","delay_days":5,"name":"Follow-up","subject_template":"...","body_template":"..."}},
  {{"step_order":4,"step_type":"email","delay_days":10,"name":"Last Touch","subject_template":"...","body_template":"..."}}
]

Rules:
- Use {{first_name}}, {{company_name}}, {{job_title}}, {{company_industry}} as placeholders
- Keep emails 3-5 sentences, professional, value-focused
- Do NOT use markdown in body_template"""

        resp = self.groq_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1200,
        )

        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            for part in raw.split("```"):
                if "[" in part:
                    raw = part.lstrip("json").strip()
                    break

        return json.loads(raw)

    def _default_steps(self, campaign) -> list:
        name = campaign.sender_name or 'the team'
        company = campaign.sender_company or 'us'
        return [
            {
                "step_order": 1, "step_type": "email", "delay_days": 1,
                "name": "Introduction",
                "subject_template": "Quick question about {company_name}",
                "body_template": (
                    f"Hi {{first_name}},\n\n"
                    f"I came across {{company_name}} and noticed the great work your team is doing in {{company_industry}}.\n\n"
                    f"We help companies like yours [key value proposition]. I'd love to share how we've helped similar teams.\n\n"
                    f"Would you be open to a quick 15-minute call this week?\n\n"
                    f"Best,\n{name}\n{company}"
                ),
            },
            {
                "step_order": 2, "step_type": "linkedin", "delay_days": 3,
                "name": "LinkedIn Connect",
                "subject_template": "",
                "body_template": "Send a LinkedIn connection request to {first_name} at {company_name}. Mention you reached out via email.",
            },
            {
                "step_order": 3, "step_type": "email", "delay_days": 5,
                "name": "Follow-up",
                "subject_template": "Re: Quick question about {company_name}",
                "body_template": (
                    f"Hi {{first_name}},\n\n"
                    f"I know things get busy — just wanted to follow up on my previous message.\n\n"
                    f"I have a few ideas specific to {{company_name}} that I think could be valuable. Even a 10-minute call would be worth your time.\n\n"
                    f"Available this week?\n\n"
                    f"Best,\n{name}"
                ),
            },
            {
                "step_order": 4, "step_type": "email", "delay_days": 10,
                "name": "Last Touch",
                "subject_template": "Closing the loop, {first_name}",
                "body_template": (
                    f"Hi {{first_name}},\n\n"
                    f"I don't want to keep reaching out if the timing isn't right for {{company_name}}.\n\n"
                    f"If you ever want to explore how we can help, feel free to reply or book time directly.\n\n"
                    f"Wishing you all the best,\n{name}\n{company}"
                ),
            },
        ]

    # ------------------------------------------------------------------
    # Email personalisation
    # ------------------------------------------------------------------

    def generate_personalized_email(self, lead, step, campaign) -> dict:
        ctx = {
            'first_name': lead.first_name or (lead.display_name.split()[0] if lead.display_name else 'there'),
            'last_name': lead.last_name or '',
            'full_name': lead.display_name,
            'company_name': lead.company_name or 'your company',
            'job_title': lead.job_title or 'your role',
            'company_industry': lead.company_industry or 'your industry',
            'company_location': lead.company_location or '',
            'sender_name': campaign.sender_name or '',
            'sender_company': campaign.sender_company or '',
            'sender_title': campaign.sender_title or '',
        }

        subject = step.subject_template
        body = step.body_template
        for key, val in ctx.items():
            subject = subject.replace('{' + key + '}', str(val))
            body = body.replace('{' + key + '}', str(val))

        if not step.ai_personalize or not self.groq_client:
            return {'subject': subject, 'body': body}

        signals = (lead.buying_signals or [])[:2]
        news_title = (lead.recent_news or [{}])[0].get('title', '') if lead.recent_news else ''
        if not signals and not news_title:
            return {'subject': subject, 'body': body}

        try:
            ctx_str = ''
            if news_title:
                ctx_str += f'Recent news about their company: "{news_title}". '
            if signals:
                ctx_str += f'Buying signals: {", ".join(signals)}.'

            prompt = f"""Personalise this B2B outreach email using the context. Keep it 3-5 sentences.

Lead: {lead.display_name}, {lead.job_title} at {lead.company_name}
Context: {ctx_str}

Original subject: {subject}
Original body: {body}

Return JSON: {{"subject":"...","body":"..."}}"""

            resp = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=350,
            )
            raw = resp.choices[0].message.content.strip()
            if "```" in raw:
                for part in raw.split("```"):
                    if "{" in part:
                        raw = part.lstrip("json").strip()
                        break
            result = json.loads(raw)
            return {
                'subject': result.get('subject', subject),
                'body': result.get('body', body),
            }
        except Exception as exc:
            logger.warning("AI personalisation failed for lead %s: %s", lead.id, exc)
            return {'subject': subject, 'body': body}

    # ------------------------------------------------------------------
    # Reply sentiment analysis
    # ------------------------------------------------------------------

    def analyze_reply_sentiment(self, reply_text: str) -> dict:
        """
        Classify a reply email as positive/negative/neutral using AI.
        Returns: {'sentiment': str, 'is_interested': bool, 'reason': str}
        """
        if not reply_text or not reply_text.strip():
            return {'sentiment': 'neutral', 'is_interested': False, 'reason': 'Empty reply'}

        # Fast keyword pre-check before calling AI
        lower = reply_text.lower()
        positive_keywords = [
            'interested', 'tell me more', 'sounds good', 'yes', 'sure', 'absolutely',
            'would love', 'great', 'let\'s', 'lets', 'schedule', 'meeting', 'call',
            'demo', 'when can', 'available', 'book', 'connect', 'love to',
        ]
        negative_keywords = [
            'not interested', 'unsubscribe', 'remove', 'stop', 'no thanks',
            'don\'t contact', 'do not contact', 'not relevant', 'not right now',
        ]

        for kw in negative_keywords:
            if kw in lower:
                return {'sentiment': 'negative', 'is_interested': False, 'reason': f'Contains "{kw}"'}

        keyword_positive = any(kw in lower for kw in positive_keywords)

        if not self.groq_client:
            sentiment = 'positive' if keyword_positive else 'neutral'
            return {
                'sentiment': sentiment,
                'is_interested': keyword_positive,
                'reason': 'Keyword match (no AI)',
            }

        try:
            prompt = f"""Classify this sales reply email. Return ONLY JSON.

Reply text:
\"\"\"
{reply_text[:800]}
\"\"\"

Return: {{"sentiment":"positive"|"negative"|"neutral","is_interested":true|false,"reason":"one sentence"}}

positive = wants to learn more / book a call / interested
negative = unsubscribe / not interested / stop emailing
neutral = out of office / asking a question / unclear"""

            resp = self.groq_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You classify email reply sentiment. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=120,
            )
            raw = resp.choices[0].message.content.strip()
            if "```" in raw:
                for part in raw.split("```"):
                    if "{" in part:
                        raw = part.lstrip("json").strip()
                        break
            result = json.loads(raw)
            return {
                'sentiment': result.get('sentiment', 'neutral'),
                'is_interested': bool(result.get('is_interested', False)),
                'reason': result.get('reason', ''),
            }
        except Exception as exc:
            logger.warning("Sentiment analysis failed: %s", exc)
            sentiment = 'positive' if keyword_positive else 'neutral'
            return {
                'sentiment': sentiment,
                'is_interested': keyword_positive,
                'reason': 'Keyword match (AI failed)',
            }

    # ------------------------------------------------------------------
    # IMAP inbox polling — detect incoming replies
    # ------------------------------------------------------------------

    def _get_imap_credentials(self, campaign):
        """Return (imap_host, imap_port, username, password) for campaign."""
        imap_host = (
            campaign.imap_host
            or os.environ.get('IMAP_HOST', '')
            or _derive_imap_host(campaign.smtp_host or getattr(settings, 'EMAIL_HOST', 'smtp.gmail.com'))
        )
        imap_port = campaign.imap_port or int(os.environ.get('IMAP_PORT', '993'))

        if campaign.smtp_username:
            username = campaign.smtp_username
            password = campaign.smtp_password
        else:
            username = getattr(settings, 'EMAIL_HOST_USER', '')
            password = getattr(settings, 'EMAIL_HOST_PASSWORD', '')

        return imap_host, imap_port, username, password

    def check_inbox_for_replies(self, campaign, enrollments: list) -> list:
        """
        Poll IMAP inbox for replies from enrolled leads.
        Returns list of dicts: {enrollment, reply_text, sender_email}
        """
        if not enrollments:
            return []

        imap_host, imap_port, username, password = self._get_imap_credentials(campaign)
        if not username or not password:
            logger.warning("No IMAP credentials available for campaign %s", campaign.id)
            return []

        # Map lead email → enrollment (case-insensitive)
        email_map = {}
        for enr in enrollments:
            if enr.lead.email:
                email_map[enr.lead.email.lower()] = enr

        if not email_map:
            return []

        found = []
        try:
            with imaplib.IMAP4_SSL(imap_host, imap_port) as imap:
                imap.login(username, password)
                imap.select('INBOX')

                # Search unseen messages from the last 30 days
                _, msg_ids = imap.search(None, 'UNSEEN')
                ids = msg_ids[0].split() if msg_ids[0] else []
                logger.info("IMAP: checking %d unseen messages for campaign %s", len(ids), campaign.id)

                for mid in ids[-50:]:  # cap at last 50 to avoid timeout
                    try:
                        _, msg_data = imap.fetch(mid, '(RFC822)')
                        raw = msg_data[0][1]
                        msg = email_lib.message_from_bytes(raw)

                        from_header = msg.get('From', '')
                        sender_email = email.utils.parseaddr(from_header)[1].lower()

                        if sender_email not in email_map:
                            continue

                        body = _extract_email_body(msg)
                        enrollment = email_map[sender_email]
                        found.append({
                            'enrollment': enrollment,
                            'reply_text': body,
                            'sender_email': sender_email,
                            'subject': msg.get('Subject', ''),
                        })
                        # Mark as seen so we don't pick it up again
                        imap.store(mid, '+FLAGS', '\\Seen')
                    except Exception as exc:
                        logger.warning("IMAP: error parsing message %s: %s", mid, exc)

        except imaplib.IMAP4.error as exc:
            raise ValueError(f"IMAP login failed: {exc}") from exc
        except Exception as exc:
            raise ValueError(f"IMAP error: {exc}") from exc

        return found

    # ------------------------------------------------------------------
    # Scheduling agent handoff — send calendar invitation email
    # ------------------------------------------------------------------

    def send_scheduling_email(self, campaign, lead, calendar_link: str = '') -> None:
        """Send a scheduling email to a positively-replied lead."""
        first_name = lead.first_name or (lead.display_name.split()[0] if lead.display_name else 'there')
        sender = campaign.sender_name or campaign.sender_company or 'us'

        if calendar_link:
            body = (
                f"Hi {first_name},\n\n"
                f"Great to hear from you! I'd love to set up a quick call.\n\n"
                f"You can book a time that works for you here: {calendar_link}\n\n"
                f"Looking forward to connecting!\n\n"
                f"Best,\n{sender}"
            )
        else:
            body = (
                f"Hi {first_name},\n\n"
                f"Great to hear from you! I'd love to set up a quick call to learn more about your needs.\n\n"
                f"What times work best for you this week? Happy to work around your schedule.\n\n"
                f"Best,\n{sender}"
            )

        subject = f"Let's schedule a call, {first_name}!"
        try:
            self.send_email(campaign, lead.email, subject, body)
            logger.info("Scheduling email sent to %s", lead.email)
        except Exception as exc:
            logger.warning("Failed to send scheduling email to %s: %s", lead.email, exc)

    # ------------------------------------------------------------------
    # Email sending
    # ------------------------------------------------------------------

    def send_email(self, campaign, to_email: str, subject: str, body: str) -> None:
        if campaign.smtp_host and campaign.smtp_username:
            self._send_via_smtp(
                host=campaign.smtp_host,
                port=campaign.smtp_port or 587,
                username=campaign.smtp_username,
                password=campaign.smtp_password,
                use_tls=campaign.smtp_use_tls,
                from_addr=campaign.from_email or campaign.smtp_username,
                display_name=campaign.sender_name or campaign.sender_company or '',
                to_email=to_email,
                subject=subject,
                body=body,
            )
            return

        from django.core.mail import send_mail
        from django.conf import settings as djsettings

        from_addr = (
            campaign.from_email
            or getattr(djsettings, 'DEFAULT_FROM_EMAIL', '')
            or getattr(djsettings, 'EMAIL_HOST_USER', '')
        )
        display_name = campaign.sender_name or campaign.sender_company or ''
        from_header = f"{display_name} <{from_addr}>" if display_name else from_addr

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=from_header,
                recipient_list=[to_email],
                fail_silently=False,
            )
        except Exception as exc:
            raise ValueError(f"Email send failed: {exc}") from exc

    def _send_via_smtp(self, host, port, username, password, use_tls,
                       from_addr, display_name, to_email, subject, body) -> None:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{display_name} <{from_addr}>" if display_name else from_addr
        msg['To'] = to_email
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        context = ssl.create_default_context()
        try:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                if use_tls:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(username, password)
                server.sendmail(from_addr, to_email, msg.as_string())
        except smtplib.SMTPException as exc:
            raise ValueError(f"SMTP error: {exc}") from exc

    # ------------------------------------------------------------------
    # Process a single enrollment step
    # ------------------------------------------------------------------

    def process_enrollment(self, enrollment) -> dict:
        from ai_sdr_agent.models import SDROutreachLog

        campaign = enrollment.campaign
        lead = enrollment.lead
        steps = list(campaign.steps.filter(is_active=True).order_by('step_order'))

        if not steps:
            return {'status': 'no_steps', 'lead': lead.display_name}

        idx = enrollment.current_step
        if idx >= len(steps):
            if enrollment.status == 'active':
                enrollment.status = 'completed'
                enrollment.completed_at = timezone.now()
                enrollment.save()
            return {'status': 'already_completed', 'lead': lead.display_name}

        step = steps[idx]
        log_base = {
            'enrollment': enrollment,
            'step': step,
            'step_order': step.step_order,
            'action_type': step.step_type,
            'sent_at': timezone.now(),
        }

        error_message = None

        if step.step_type == 'email':
            if not lead.email:
                SDROutreachLog.objects.create(
                    **log_base, status='skipped',
                    error_message='Lead has no email address',
                )
                result_status = 'skipped'
                error_message = 'Lead has no email address'
            else:
                try:
                    content = self.generate_personalized_email(lead, step, campaign)
                    self.send_email(campaign, lead.email, content['subject'], content['body'])
                    SDROutreachLog.objects.create(
                        **log_base, status='sent',
                        subject_sent=content['subject'],
                        body_sent=content['body'],
                    )
                    campaign.emails_sent = (campaign.emails_sent or 0) + 1
                    campaign.save(update_fields=['emails_sent'])
                    if lead.status == 'new':
                        lead.status = 'contacted'
                        lead.save(update_fields=['status'])
                    result_status = 'sent'
                except Exception as exc:
                    error_message = str(exc)
                    logger.error("Email send failed for lead %s: %s", lead.id, exc)
                    SDROutreachLog.objects.create(
                        **log_base, status='failed',
                        error_message=error_message,
                    )
                    result_status = 'failed'
        else:
            note = step.body_template or f"Send LinkedIn connection to {lead.display_name} ({lead.linkedin_url or 'no URL'})"
            SDROutreachLog.objects.create(**log_base, status='sent', body_sent=note)
            result_status = 'sent'

        # Advance enrollment to next step
        enrollment.current_step = idx + 1
        remaining = steps[idx + 1:]
        if remaining:
            next_step = remaining[0]
            enrollment.next_action_at = enrollment.enrolled_at + timezone.timedelta(days=next_step.delay_days)
        else:
            enrollment.status = 'completed'
            enrollment.completed_at = timezone.now()

        enrollment.save()

        result = {
            'status': result_status,
            'step_type': step.step_type,
            'step_order': step.step_order,
            'lead': lead.display_name,
        }
        if error_message:
            result['error'] = error_message
        return result


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _derive_imap_host(smtp_host: str) -> str:
    """Derive likely IMAP host from SMTP host (smtp.gmail.com → imap.gmail.com)."""
    if not smtp_host:
        return 'imap.gmail.com'
    return smtp_host.replace('smtp.', 'imap.', 1)


def _extract_email_body(msg) -> str:
    """Extract plain-text body from an email.message.Message object."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get('Content-Disposition', ''))
            if ct == 'text/plain' and 'attachment' not in cd:
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or 'utf-8', errors='replace'
                    )
                except Exception:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode(
                msg.get_content_charset() or 'utf-8', errors='replace'
            )
        except Exception:
            pass
    return ''
