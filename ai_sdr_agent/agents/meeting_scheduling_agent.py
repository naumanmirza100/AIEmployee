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

# ---------------------------------------------------------------------------
# HTML Email Builder Helpers
# ---------------------------------------------------------------------------

def _base_html(content: str, preview_text: str = '') -> str:
    """Wrap email content in a responsive base template."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Email</title>
  <!--[if mso]><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->
</head>
<body style="margin:0;padding:0;background-color:#f4f4f7;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  {f'<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{preview_text}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>' if preview_text else ''}
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f4f4f7;min-width:100%;">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;width:100%;">

          <!-- Header Bar -->
          <tr>
            <td style="background:linear-gradient(135deg,#7c3aed,#4f46e5);border-radius:12px 12px 0 0;padding:28px 36px;text-align:center;">
              <span style="color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.3px;">AI Employee</span>
              <span style="display:block;color:rgba(255,255,255,0.65);font-size:12px;margin-top:4px;letter-spacing:0.04em;text-transform:uppercase;">Smart Outreach Platform</span>
            </td>
          </tr>

          <!-- Body Card -->
          <tr>
            <td style="background:#ffffff;padding:36px 36px 28px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;">
              {content}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f9fafb;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;padding:18px 36px;text-align:center;">
              <p style="margin:0;color:#9ca3af;font-size:11px;line-height:1.6;">
                You received this email because you expressed interest in connecting.<br/>
                If you'd prefer not to hear from us, simply reply with <strong>unsubscribe</strong>.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _btn(label: str, url: str, color: str = '#7c3aed') -> str:
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" style="margin:0 auto;">'
        f'<tr><td style="background:{color};border-radius:8px;">'
        f'<a href="{url}" target="_blank" style="display:inline-block;padding:13px 32px;'
        f'color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;'
        f'letter-spacing:-0.1px;white-space:nowrap;">{label}</a>'
        f'</td></tr></table>'
    )


def _detail_row(label: str, value: str) -> str:
    return (
        f'<tr>'
        f'<td style="padding:6px 0;color:#6b7280;font-size:13px;width:100px;vertical-align:top;">{label}</td>'
        f'<td style="padding:6px 0;color:#111827;font-size:13px;font-weight:600;vertical-align:top;">{value}</td>'
        f'</tr>'
    )


def _divider() -> str:
    return '<tr><td colspan="2"><hr style="border:none;border-top:1px solid #f3f4f6;margin:8px 0;"/></td></tr>'


# ---------------------------------------------------------------------------
# Individual Email HTML Builders
# ---------------------------------------------------------------------------

def _build_scheduling_html(first_name, sender, sender_title, sender_company,
                            duration, booking_url, company_name) -> str:
    bullets = ''.join(
        f'<li style="margin-bottom:6px;color:#374151;font-size:14px;">{b}</li>'
        for b in [
            'Your current priorities and challenges',
            'How companies like yours are already using our solution',
            'Any questions you have — we keep it open and no-pressure',
        ]
    )
    sender_block = f'<strong style="color:#111827;">{sender}</strong>'
    if sender_title:
        sender_block += f'<br/><span style="color:#6b7280;font-size:13px;">{sender_title}</span>'
    if sender_company:
        sender_block += f'<br/><span style="color:#6b7280;font-size:13px;">{sender_company}</span>'

    body_html = f"""
      <p style="margin:0 0 20px;color:#111827;font-size:22px;font-weight:700;line-height:1.3;">
        Let's find a time to connect, {first_name}! 👋
      </p>

      <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.65;">
        Thanks for getting back to us — really glad to hear from you!
        I'd love to set up a <strong>{duration} discovery call</strong> so we can learn more about
        <strong>{company_name or 'your company'}</strong> and share how we might be able to help.
      </p>

      <!-- CTA -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:28px 0;">
        <tr>
          <td align="center">
            {_btn('📅 Pick a Time That Works for You', booking_url)}
            <p style="margin:10px 0 0;color:#9ca3af;font-size:12px;">Takes less than 30 seconds</p>
          </td>
        </tr>
      </table>

      <!-- What we'll cover -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;margin-bottom:24px;">
        <tr>
          <td style="padding:18px 20px;">
            <p style="margin:0 0 10px;color:#7c3aed;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">On the call we'll cover</p>
            <ul style="margin:0;padding-left:18px;">{bullets}</ul>
          </td>
        </tr>
      </table>

      <p style="margin:0 0 24px;color:#374151;font-size:14px;line-height:1.6;">
        It's a quick, no-pressure conversation. You'll walk away with concrete ideas regardless of what you decide to do next.
      </p>

      <hr style="border:none;border-top:1px solid #f3f4f6;margin:0 0 20px;"/>

      <p style="margin:0;color:#374151;font-size:14px;line-height:1.8;">
        Looking forward to connecting,<br/>
        {sender_block}
      </p>
    """
    return _base_html(body_html, preview_text=f"Hi {first_name}, let's schedule our call — pick a time that works for you.")


def _build_confirmation_html(first_name, sender, sender_title, sender_company,
                              scheduled_str, duration, title, meet_link,
                              booking_url) -> str:
    join_block = ''
    if meet_link:
        join_block = f"""
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 0;">
        <tr>
          <td align="center">
            <p style="margin:0 0 10px;color:#6b7280;font-size:13px;">Your video call link</p>
            {_btn('🎥 Join Meeting', meet_link, '#059669')}
            <p style="margin:8px 0 0;color:#d1d5db;font-size:11px;word-break:break-all;">{meet_link}</p>
          </td>
        </tr>
      </table>"""

    reschedule_block = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0"'
        ' style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;margin-top:24px;">'
        '<tr><td style="padding:14px 20px;text-align:center;">'
        '<p style="margin:0;color:#6b7280;font-size:13px;">'
        'Need to reschedule? Simply <strong>reply to this email</strong> and we\'ll sort it out.</p>'
        '</td></tr></table>'
    )

    sender_block = f'<strong style="color:#111827;">{sender}</strong>'
    if sender_title:
        sender_block += f'<br/><span style="color:#6b7280;font-size:13px;">{sender_title}</span>'
    if sender_company:
        sender_block += f'<br/><span style="color:#6b7280;font-size:13px;">{sender_company}</span>'

    body_html = f"""
      <!-- Confirmed checkmark -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td align="center" style="padding-bottom:20px;">
            <div style="width:56px;height:56px;background:#ecfdf5;border-radius:50%;
                        display:inline-flex;align-items:center;justify-content:center;
                        font-size:26px;line-height:56px;text-align:center;">✅</div>
          </td>
        </tr>
      </table>

      <p style="margin:0 0 6px;color:#111827;font-size:22px;font-weight:700;text-align:center;">
        You're all confirmed, {first_name}!
      </p>
      <p style="margin:0 0 24px;color:#6b7280;font-size:14px;text-align:center;">
        We're looking forward to speaking with you.
      </p>

      <!-- Meeting Details Box -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:10px;margin-bottom:4px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 14px;color:#7c3aed;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">Meeting Details</p>
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {_detail_row('Topic', title)}
              {_divider()}
              {_detail_row('Date &amp; Time', scheduled_str)}
              {_divider()}
              {_detail_row('Duration', f'{duration} minutes')}
              {_divider()}
              {_detail_row('Format', 'Video Call')}
            </table>
          </td>
        </tr>
      </table>

      {join_block}
      {reschedule_block}

      <!-- What to expect -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;margin-top:24px;margin-bottom:24px;">
        <tr>
          <td style="padding:18px 20px;">
            <p style="margin:0 0 10px;color:#7c3aed;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">What to expect</p>
            <ul style="margin:0;padding-left:18px;">
              {''.join(f'<li style="margin-bottom:6px;color:#374151;font-size:14px;">{b}</li>' for b in [
                'Quick introductions and context-setting',
                "We'd love to hear about your goals and current situation",
                "We'll walk you through what's most relevant to your needs",
                'Plenty of time for your questions',
              ])}
            </ul>
          </td>
        </tr>
      </table>

      <hr style="border:none;border-top:1px solid #f3f4f6;margin:0 0 20px;"/>

      <p style="margin:0;color:#374151;font-size:14px;line-height:1.8;">
        See you then!<br/>
        {sender_block}
      </p>
    """
    return _base_html(body_html, preview_text=f"Your meeting is confirmed, {first_name}! Here are the details.")


def _build_reminder_html(first_name, sender, sender_title, sender_company,
                          scheduled_str, duration, title, meet_link,
                          booking_url) -> str:
    join_block = ''
    if meet_link:
        join_block = f"""
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:20px 0 0;">
        <tr>
          <td align="center">
            {_btn('🎥 Join Meeting', meet_link, '#059669')}
            <p style="margin:8px 0 0;color:#d1d5db;font-size:11px;word-break:break-all;">{meet_link}</p>
          </td>
        </tr>
      </table>"""

    reschedule_block = (
        '<p style="margin:0;color:#6b7280;font-size:13px;text-align:center;">'
        'Need to reschedule? Simply <strong>reply to this email</strong> and we\'ll sort it out.'
        '</p>'
    )

    sender_block = f'<strong style="color:#111827;">{sender}</strong>'
    if sender_title:
        sender_block += f'<br/><span style="color:#6b7280;font-size:13px;">{sender_title}</span>'
    if sender_company:
        sender_block += f'<br/><span style="color:#6b7280;font-size:13px;">{sender_company}</span>'

    body_html = f"""
      <!-- Bell icon -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td align="center" style="padding-bottom:18px;">
            <div style="width:56px;height:56px;background:#fffbeb;border-radius:50%;
                        display:inline-flex;align-items:center;justify-content:center;
                        font-size:26px;line-height:56px;text-align:center;">🔔</div>
          </td>
        </tr>
      </table>

      <p style="margin:0 0 6px;color:#111827;font-size:22px;font-weight:700;text-align:center;">
        See you tomorrow, {first_name}!
      </p>
      <p style="margin:0 0 24px;color:#6b7280;font-size:14px;text-align:center;">
        Just a friendly heads-up — your call is coming up.
      </p>

      <!-- Meeting Details -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:10px;margin-bottom:4px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 14px;color:#7c3aed;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">Tomorrow's Call</p>
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {_detail_row('Topic', title)}
              {_divider()}
              {_detail_row('Date &amp; Time', scheduled_str)}
              {_divider()}
              {_detail_row('Duration', f'{duration} minutes')}
            </table>
          </td>
        </tr>
      </table>

      {join_block}

      <!-- Prep Tips -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;margin-top:24px;margin-bottom:24px;">
        <tr>
          <td style="padding:18px 20px;">
            <p style="margin:0 0 10px;color:#7c3aed;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">Optional prep (no pressure)</p>
            <ul style="margin:0;padding-left:18px;">
              {''.join(f'<li style="margin-bottom:6px;color:#374151;font-size:14px;">{b}</li>' for b in [
                'What your top priorities are right now',
                'What you have tried so far (if anything)',
                'What a successful outcome would look like for you',
              ])}
            </ul>
          </td>
        </tr>
      </table>

      {reschedule_block}

      <hr style="border:none;border-top:1px solid #f3f4f6;margin:20px 0;"/>

      <p style="margin:0;color:#374151;font-size:14px;line-height:1.8;">
        Looking forward to our conversation tomorrow!<br/>
        {sender_block}
      </p>
    """
    return _base_html(body_html, preview_text=f"Reminder: your call is tomorrow at {scheduled_str}.")


# ---------------------------------------------------------------------------
# Main Agent Class
# ---------------------------------------------------------------------------

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
                f"{lead.display_name} replied — treat as a warm lead and focus on discovery before pitching."
            ),
        }

    # ------------------------------------------------------------------
    # Scheduling Email  (sent right after positive reply detected)
    # ------------------------------------------------------------------

    def send_scheduling_email_once(self, campaign, lead, meeting, prep_notes: dict = None) -> bool:
        """
        Send scheduling email exactly once (atomic guard via conditional UPDATE).
        Returns True if email was sent, False if already sent.
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
            SDRMeeting.objects.filter(id=meeting.id).update(scheduling_email_sent_at=None)
            raise

    def send_scheduling_email(self, campaign, lead, meeting, prep_notes: dict = None) -> None:
        """Send a professional HTML scheduling email with a self-serve booking link."""
        first_name = lead.first_name or (lead.display_name.split()[0] if lead.display_name else 'there')
        sender = campaign.sender_name or campaign.sender_company or 'the team'
        sender_title = campaign.sender_title or ''
        sender_company = campaign.sender_company or ''

        duration = '30 minutes'
        if prep_notes and prep_notes.get('recommended_duration'):
            duration = prep_notes['recommended_duration']

        subject = f"Let's find a time to connect, {first_name}!"

        if meeting and getattr(meeting, 'booking_token', None):
            frontend_url = (
                getattr(settings, 'FRONTEND_URL', None)
                or os.environ.get('FRONTEND_URL', 'http://localhost:5173')
            ).rstrip('/')
            booking_url = f"{frontend_url}/book/{meeting.booking_token}"
        elif campaign.calendar_link:
            booking_url = campaign.calendar_link
        else:
            booking_url = None

        plain = (
            f"Hi {first_name},\n\n"
            f"Thanks for getting back to us! I'd love to set up a {duration} discovery call.\n\n"
            + (f"Book a time here: {booking_url}\n\n" if booking_url else
               "Please reply with a few times that work for you.\n\n")
            + f"Looking forward to connecting!\n\nBest,\n{sender}"
            + (f"\n{sender_title}" if sender_title else '')
            + (f"\n{sender_company}" if sender_company else '')
            + "\n\n---\nReply 'unsubscribe' to opt out."
        )

        html = _build_scheduling_html(
            first_name=first_name,
            sender=sender,
            sender_title=sender_title,
            sender_company=sender_company,
            duration=duration,
            booking_url=booking_url or '#',
            company_name=lead.company_name,
        )

        self._send_email(campaign, lead.email, subject, plain, html)
        logger.info("Scheduling email sent to %s (meeting %s)", lead.email, meeting.id if meeting else '?')

    # ------------------------------------------------------------------
    # Confirmation Email  (sent when a specific time is confirmed)
    # ------------------------------------------------------------------

    def send_confirmation_email(self, campaign, lead, meeting) -> None:
        """Send professional HTML confirmation email with meet link and reschedule option."""
        first_name = lead.first_name or (lead.display_name.split()[0] if lead.display_name else 'there')
        sender = campaign.sender_name or campaign.sender_company or 'the team'
        sender_title = campaign.sender_title or ''
        sender_company = campaign.sender_company or ''
        meet_link = meeting.calendar_link or campaign.calendar_link or ''
        scheduled_str = self._format_meeting_time(meeting)
        duration = meeting.duration_minutes or 30
        title = meeting.title or 'Discovery Call'

        booking_url = None
        if getattr(meeting, 'booking_token', None):
            frontend_url = (
                getattr(settings, 'FRONTEND_URL', None)
                or os.environ.get('FRONTEND_URL', 'http://localhost:5173')
            ).rstrip('/')
            booking_url = f"{frontend_url}/book/{meeting.booking_token}"

        subject = f"Confirmed: {title} on {scheduled_str}"

        plain = (
            f"Hi {first_name},\n\n"
            f"Your call is confirmed! Here are the details:\n\n"
            f"  Topic       : {title}\n"
            f"  Date & Time : {scheduled_str}\n"
            f"  Duration    : {duration} minutes\n"
            + (f"  Join Link   : {meet_link}\n" if meet_link else '')
            + "\nIf you need to reschedule, just reply to this email and we'll sort it out.\n\n"
            f"See you then!\n\nBest,\n{sender}"
            + (f"\n{sender_title}" if sender_title else '')
            + (f"\n{sender_company}" if sender_company else '')
        )

        html = _build_confirmation_html(
            first_name=first_name,
            sender=sender,
            sender_title=sender_title,
            sender_company=sender_company,
            scheduled_str=scheduled_str,
            duration=duration,
            title=title,
            meet_link=meet_link,
            booking_url=booking_url,
        )

        self._send_email(campaign, lead.email, subject, plain, html)
        logger.info("Confirmation email sent to %s for meeting %s", lead.email, meeting.id)

    # ------------------------------------------------------------------
    # Reminder Email  (sent ~24 hours before meeting)
    # ------------------------------------------------------------------

    def send_reminder_email(self, campaign, lead, meeting) -> None:
        """Send professional HTML 24-hour reminder email."""
        first_name = lead.first_name or (lead.display_name.split()[0] if lead.display_name else 'there')
        sender = campaign.sender_name or campaign.sender_company or 'the team'
        sender_title = campaign.sender_title or ''
        sender_company = campaign.sender_company or ''
        meet_link = meeting.calendar_link or campaign.calendar_link or ''
        scheduled_str = self._format_meeting_time(meeting)
        duration = meeting.duration_minutes or 30
        title = meeting.title or 'Discovery Call'

        booking_url = None
        if getattr(meeting, 'booking_token', None):
            frontend_url = (
                getattr(settings, 'FRONTEND_URL', None)
                or os.environ.get('FRONTEND_URL', 'http://localhost:5173')
            ).rstrip('/')
            booking_url = f"{frontend_url}/book/{meeting.booking_token}"

        subject = f"Reminder: {title} is tomorrow — {scheduled_str}"

        plain = (
            f"Hi {first_name},\n\n"
            f"Just a friendly reminder that your call is tomorrow!\n\n"
            f"  Topic       : {title}\n"
            f"  Date & Time : {scheduled_str}\n"
            f"  Duration    : {duration} minutes\n"
            + (f"  Join Link   : {meet_link}\n" if meet_link else '')
            + f"\nNo preparation needed — come as you are!\n\n"
            + "Need to reschedule? Just reply to this email and we'll sort it out.\n\n"
            + f"See you tomorrow!\n\n{sender}"
            + (f"\n{sender_title}" if sender_title else '')
            + (f"\n{sender_company}" if sender_company else '')
        )

        html = _build_reminder_html(
            first_name=first_name,
            sender=sender,
            sender_title=sender_title,
            sender_company=sender_company,
            scheduled_str=scheduled_str,
            duration=duration,
            title=title,
            meet_link=meet_link,
            booking_url=booking_url,
        )

        self._send_email(campaign, lead.email, subject, plain, html)
        logger.info("Reminder email sent to %s for meeting %s", lead.email, meeting.id)

    # ------------------------------------------------------------------
    # Internal SMTP sender
    # ------------------------------------------------------------------

    def _send_email(self, campaign, to_email: str, subject: str,
                    plain: str, html: str = None) -> None:
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

        msg.attach(MIMEText(plain, 'plain', 'utf-8'))
        if html:
            msg.attach(MIMEText(html, 'html', 'utf-8'))

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
