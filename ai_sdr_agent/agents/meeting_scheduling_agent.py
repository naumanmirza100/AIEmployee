"""
Meeting Scheduling Agent
--------------------------
Handles the full lifecycle after a positive reply:
  1. Sends a professional scheduling email with calendar link
  2. Generates AI prep notes (who the lead is, why they're interested, talking points)
  3. Sends 24-hour reminder with context
  4. Sends confirmation email when meeting is booked
"""

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

_PREP_SYSTEM_PROMPT = (
    "You are an expert B2B sales strategist. "
    "Generate concise, actionable meeting prep notes for a sales rep. "
    "Return ONLY valid JSON — no markdown, no extra text."
)


class MeetingSchedulingAgent:
    """
    Handles scheduling emails, AI prep notes, reminders, and confirmations
    for meetings triggered by positive outreach replies.
    """

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
                logger.error("Groq init failed in MeetingSchedulingAgent: %s", exc)

        self.model = getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant')

    # ------------------------------------------------------------------
    # AI Prep Notes
    # ------------------------------------------------------------------

    def generate_prep_notes(self, lead, enrollment=None, reply_text: str = '') -> dict:
        """
        Generate AI meeting prep notes for the sales rep.
        Returns a dict with summary, talking_points, questions_to_ask, risks, etc.
        """
        if self.groq_client:
            try:
                return self._ai_prep_notes(lead, enrollment, reply_text)
            except Exception as exc:
                logger.warning("AI prep notes failed, using defaults: %s", exc)
        return self._default_prep_notes(lead, reply_text)

    def _ai_prep_notes(self, lead, enrollment, reply_text: str) -> dict:
        buying_signals = ', '.join((lead.buying_signals or [])[:3]) or 'None identified'
        recent_news = ''
        if lead.recent_news:
            recent_news = (lead.recent_news[0] or {}).get('title', '')

        reply_excerpt = (reply_text or '')[:400] or 'No reply text available'
        campaign_name = enrollment.campaign.name if enrollment else 'Outreach Campaign'
        campaign_desc = enrollment.campaign.description if enrollment else ''
        emails_sent = enrollment.current_step if enrollment else 1

        prompt = f"""Generate meeting prep notes for a B2B sales discovery call.

Lead: {lead.display_name}
Title: {lead.job_title or 'Unknown'}
Company: {lead.company_name or 'Unknown'} ({lead.company_industry or 'Unknown industry'})
Company Size: {lead.company_size or 'Unknown'} employees
Location: {lead.company_location or 'Unknown'}
Lead Score: {lead.score or 'Not scored'}/100 ({lead.temperature or 'unscored'})
Buying Signals: {buying_signals}
Recent News: {recent_news or 'None'}
Campaign: {campaign_name} — {campaign_desc}
Emails sent before reply: {emails_sent}
Lead's reply: "{reply_excerpt}"

Return exactly this JSON:
{{
  "summary": "2-3 sentence overview of who this person is and why they replied",
  "talking_points": ["point 1", "point 2", "point 3"],
  "questions_to_ask": ["question 1", "question 2", "question 3"],
  "risks": ["risk or objection to prepare for"],
  "opportunity_score": 7,
  "recommended_duration": "30 min",
  "key_insight": "One sentence — the single most important thing to know going into this call"
}}"""

        resp = self.groq_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _PREP_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=700,
        )
        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            for part in raw.split("```"):
                if "{" in part:
                    raw = part.lstrip("json").strip()
                    break
        return json.loads(raw)

    def _default_prep_notes(self, lead, reply_text: str) -> dict:
        emails_before = 1
        return {
            "summary": (
                f"{lead.display_name} is a {lead.job_title or 'decision maker'} at "
                f"{lead.company_name or 'their company'} who responded positively to outreach. "
                f"They are a {lead.temperature or 'warm'} lead with a score of {lead.score or 'N/A'}/100."
            ),
            "talking_points": [
                f"Ask about their current challenges in {lead.company_industry or 'their industry'}",
                "Understand their decision-making process and timeline",
                "Present case studies from similar companies",
            ],
            "questions_to_ask": [
                "What prompted you to reply? What's driving this priority right now?",
                "What does success look like for you in the next 6 months?",
                "Who else would be involved in evaluating a solution like this?",
            ],
            "risks": [
                "May still be early in their research process",
                "Budget approval may require additional stakeholders",
            ],
            "opportunity_score": (lead.score // 10) if lead.score else 5,
            "recommended_duration": "30 min",
            "key_insight": (
                f"{lead.display_name} replied after {emails_before} email(s) — "
                "treat as a warm lead and focus on discovery before pitching."
            ),
        }

    # ------------------------------------------------------------------
    # Scheduling Email  (sent right after positive reply detected)
    # ------------------------------------------------------------------

    def send_scheduling_email_once(self, campaign, lead, meeting, prep_notes: dict = None) -> bool:
        """
        Send scheduling email exactly once, even under concurrent scheduler + API calls.

        Uses an atomic conditional UPDATE:
          UPDATE sdr_meeting SET scheduling_email_sent_at=NOW()
          WHERE id=X AND scheduling_email_sent_at IS NULL

        Only the first caller gets rows_updated=1 and proceeds to send.
        All other concurrent/subsequent callers get 0 and are silently skipped.
        Returns True if the email was sent, False if it was already sent.
        """
        from ai_sdr_agent.models import SDRMeeting

        sent_at = timezone.now()
        rows_claimed = SDRMeeting.objects.filter(
            id=meeting.id,
            scheduling_email_sent_at__isnull=True,
        ).update(scheduling_email_sent_at=sent_at)

        if rows_claimed == 0:
            logger.info(
                "SDR [scheduling-email] meeting=%d — SKIPPED: already sent (atomic guard)",
                meeting.id,
            )
            return False

        try:
            self.send_scheduling_email(campaign, lead, meeting, prep_notes)
            logger.info(
                "SDR [scheduling-email] meeting=%d lead=%s — SENT ✓",
                meeting.id, lead.email,
            )
            return True
        except Exception:
            # Roll back the timestamp so a retry is possible
            SDRMeeting.objects.filter(id=meeting.id).update(scheduling_email_sent_at=None)
            raise

    def send_scheduling_email(self, campaign, lead, meeting, prep_notes: dict = None) -> None:
        """Send a professional scheduling email with a self-serve booking link."""
        first_name = lead.first_name or (lead.display_name.split()[0] if lead.display_name else 'there')
        sender = campaign.sender_name or campaign.sender_company or 'the team'
        sender_title = campaign.sender_title or ''
        sender_company = campaign.sender_company or ''

        duration = '30 minutes'
        if prep_notes and prep_notes.get('recommended_duration'):
            duration = prep_notes['recommended_duration']

        subject = f"Let's find a time to connect, {first_name}!"

        # Use our internal self-scheduling page so the lead's chosen time
        # automatically updates the meeting record. Fall back to an external
        # calendar link (e.g. Calendly) if one is configured on the campaign.
        if meeting and getattr(meeting, 'booking_token', None):
            frontend_url = (
                getattr(settings, 'FRONTEND_URL', None)
                or os.environ.get('FRONTEND_URL', 'http://localhost:5173')
            ).rstrip('/')
            booking_url = f"{frontend_url}/book/{meeting.booking_token}"
            booking_block = (
                f"You can pick a time that works for you here:\n{booking_url}\n\n"
                "It only takes a few seconds — just choose a slot that's convenient for you "
                "and it'll be added straight to our calendars."
            )
        elif campaign.calendar_link:
            booking_block = f"You can pick a time that works for you here:\n{campaign.calendar_link}"
        else:
            booking_block = (
                "Please reply with a few times that work for you "
                "and I'll send over a calendar invite right away."
            )

        sender_sig = sender
        if sender_title:
            sender_sig += f"\n{sender_title}"
        if sender_company:
            sender_sig += f"\n{sender_company}"

        body = f"""Hi {first_name},

Thank you for getting back to me — really glad to hear from you!

I'd love to set up a {duration} discovery call so we can learn more about {lead.company_name or 'your company'} and share how we might be able to help.

{booking_block}

On the call we can cover:
  • Your current priorities and challenges
  • How companies like yours are using our solution
  • Any questions you have for us

It should be a quick, no-pressure conversation — and you'll walk away with some concrete ideas regardless.

Looking forward to connecting!

Best regards,
{sender_sig}

---
If you'd prefer not to receive further emails, just reply with "unsubscribe"."""

        self._send_email(campaign, lead.email, subject, body)
        logger.info("Scheduling email sent to %s (meeting %s)", lead.email, meeting.id if meeting else '?')

    # ------------------------------------------------------------------
    # Confirmation Email  (sent when a specific time is confirmed)
    # ------------------------------------------------------------------

    def send_confirmation_email(self, campaign, lead, meeting) -> None:
        """Send confirmation email when a meeting time is set."""
        first_name = lead.first_name or (lead.display_name.split()[0] if lead.display_name else 'there')
        sender = campaign.sender_name or campaign.sender_company or 'the team'
        sender_title = campaign.sender_title or ''
        calendar_link = meeting.calendar_link or campaign.calendar_link or ''
        scheduled_str = self._format_meeting_time(meeting)
        duration = meeting.duration_minutes or 30

        subject = f"Confirmed: Our call on {scheduled_str}"

        cal_line = f"\nJoin link / calendar: {calendar_link}" if calendar_link else ''

        body = f"""Hi {first_name},

Your call is confirmed! Here are the details:

  Date & Time : {scheduled_str}
  Duration    : {duration} minutes
  Topic       : {meeting.title}{cal_line}

What to expect:
  • Quick intros
  • I'd love to hear about your goals and current situation
  • We'll show you what's most relevant to your needs
  • Plenty of time for your questions

If anything comes up and you need to reschedule, just reply to this email — no problem at all.

See you then!

Best regards,
{sender}{(', ' + sender_title) if sender_title else ''}"""

        self._send_email(campaign, lead.email, subject, body)
        logger.info("Confirmation email sent to %s for meeting %s", lead.email, meeting.id)

    # ------------------------------------------------------------------
    # Reminder Email  (sent ~24 hours before meeting)
    # ------------------------------------------------------------------

    def send_reminder_email(self, campaign, lead, meeting) -> None:
        """Send a 24-hour reminder email to the lead."""
        first_name = lead.first_name or (lead.display_name.split()[0] if lead.display_name else 'there')
        sender = campaign.sender_name or campaign.sender_company or 'the team'
        scheduled_str = self._format_meeting_time(meeting)
        calendar_link = meeting.calendar_link or campaign.calendar_link or ''
        duration = meeting.duration_minutes or 30

        subject = f"Reminder: Our call is tomorrow — {scheduled_str}"

        join_line = f"\nJoin link: {calendar_link}" if calendar_link else ''

        body = f"""Hi {first_name},

Just a friendly reminder that we have a call coming up tomorrow:

  Date & Time : {scheduled_str}
  Duration    : {duration} minutes{join_line}

To make the most of our time, it might be helpful to think about:
  • What your top priorities are right now
  • What you've tried so far (if anything)
  • What a successful outcome would look like for you

No preparation needed — come as you are! I'm looking forward to our conversation.

See you tomorrow,
{sender}

P.S. Need to reschedule? Just reply to this email and we'll sort it out."""

        self._send_email(campaign, lead.email, subject, body)
        logger.info("Reminder email sent to %s for meeting %s", lead.email, meeting.id)

    # ------------------------------------------------------------------
    # Internal SMTP sender
    # ------------------------------------------------------------------

    def _send_email(self, campaign, to_email: str, subject: str, body: str) -> None:
        if not (campaign.smtp_host and campaign.smtp_username and campaign.smtp_password):
            raise ValueError(
                "Campaign SMTP credentials not configured. "
                "Add SMTP settings in campaign Settings before sending."
            )

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        display_name = campaign.sender_name or campaign.sender_company or ''
        from_addr = campaign.from_email or campaign.smtp_username
        msg['From'] = f"{display_name} <{from_addr}>" if display_name else from_addr
        msg['To'] = to_email
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        context = ssl.create_default_context()
        port = campaign.smtp_port or 587
        try:
            with smtplib.SMTP(campaign.smtp_host, port, timeout=20) as server:
                server.ehlo()
                if campaign.smtp_use_tls:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(campaign.smtp_username, campaign.smtp_password)
                server.sendmail(from_addr, to_email, msg.as_string())
        except smtplib.SMTPException as exc:
            raise ValueError(f"SMTP error: {exc}") from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_meeting_time(meeting) -> str:
        if meeting.scheduled_at:
            return meeting.scheduled_at.strftime('%A, %B %d %Y at %I:%M %p UTC')
        return 'TBD — awaiting confirmation'
