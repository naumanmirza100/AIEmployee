"""
SDR Analytics Agent
--------------------
Calculates performance metrics for the AI SDR system and delivers:
  1. Daily summary email  — new leads, emails sent, meetings booked, reply rate
  2. Weekly alert email   — fires when meetings < threshold (default 5/week)
  3. compute_metrics()    — called by the API endpoint for live dashboard data
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from datetime import timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

MEETINGS_ALERT_THRESHOLD = 5   # alert if fewer than this many meetings this week


class AnalyticsAgent:
    """Computes SDR metrics and sends summary / alert emails."""

    # ------------------------------------------------------------------
    # Core metrics calculation
    # ------------------------------------------------------------------

    def compute_metrics(self, company_user) -> dict:
        """Return full analytics dict for the given company user."""
        from ai_sdr_agent.models import (
            SDRLead, SDRCampaign, SDRCampaignEnrollment,
            SDROutreachLog, SDRMeeting,
        )

        now       = timezone.now()
        today_start     = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start      = today_start - timedelta(days=now.weekday())          # Mon
        last_week_start = week_start - timedelta(days=7)
        last_week_end   = week_start
        month_start     = today_start.replace(day=1)

        # ── Leads ─────────────────────────────────────────────────────
        leads_qs = SDRLead.objects.filter(company_user=company_user)
        leads_today  = leads_qs.filter(created_at__gte=today_start).count()
        leads_week   = leads_qs.filter(created_at__gte=week_start).count()
        leads_lweek  = leads_qs.filter(created_at__gte=last_week_start, created_at__lt=last_week_end).count()
        leads_month  = leads_qs.filter(created_at__gte=month_start).count()
        leads_total  = leads_qs.count()

        # Lead status breakdown
        status_counts = {
            row['status']: row['cnt']
            for row in leads_qs.order_by().values('status').annotate(cnt=Count('id'))
        }

        # Lead temperature breakdown
        temp_counts = {
            row['temperature']: row['cnt']
            for row in leads_qs.order_by().values('temperature').annotate(cnt=Count('id'))
        }

        # Lead source breakdown
        source_counts = {
            row['source']: row['cnt']
            for row in leads_qs.order_by().values('source').annotate(cnt=Count('id'))
        }

        # ── Emails ────────────────────────────────────────────────────
        logs_qs = SDROutreachLog.objects.filter(
            enrollment__campaign__company_user=company_user,
            action_type='email',
        )
        emails_today  = logs_qs.filter(sent_at__gte=today_start, status='sent').count()
        emails_week   = logs_qs.filter(sent_at__gte=week_start, status='sent').count()
        emails_lweek  = logs_qs.filter(sent_at__gte=last_week_start, sent_at__lt=last_week_end, status='sent').count()
        emails_month  = logs_qs.filter(sent_at__gte=month_start, status='sent').count()
        emails_total  = logs_qs.filter(status='sent').count()
        emails_failed = logs_qs.filter(sent_at__gte=week_start, status='failed').count()

        # ── Enrollments / Replies ─────────────────────────────────────
        enroll_qs = SDRCampaignEnrollment.objects.filter(campaign__company_user=company_user)
        total_enrolled  = enroll_qs.count()
        replied_week    = enroll_qs.filter(replied_at__gte=week_start).count()
        replied_lweek   = enroll_qs.filter(replied_at__gte=last_week_start, replied_at__lt=last_week_end).count()
        replied_total   = enroll_qs.filter(status__in=['replied', 'unsubscribed']).count()

        # Reply breakdown by sentiment
        sentiment_counts = {
            row['reply_sentiment']: row['cnt']
            for row in enroll_qs.exclude(reply_sentiment='').exclude(reply_sentiment__isnull=True)
                                 .order_by().values('reply_sentiment').annotate(cnt=Count('id'))
        }

        # ── Meetings ──────────────────────────────────────────────────
        meet_qs = SDRMeeting.objects.filter(company_user=company_user)
        meetings_today  = meet_qs.filter(created_at__gte=today_start).count()
        meetings_week   = meet_qs.filter(created_at__gte=week_start).count()
        meetings_lweek  = meet_qs.filter(created_at__gte=last_week_start, created_at__lt=last_week_end).count()
        meetings_month  = meet_qs.filter(created_at__gte=month_start).count()
        meetings_total  = meet_qs.count()
        meetings_scheduled = meet_qs.filter(status='scheduled').count()
        meetings_completed = meet_qs.filter(status='completed').count()

        # ── Campaigns ─────────────────────────────────────────────────
        camp_qs = SDRCampaign.objects.filter(company_user=company_user)
        campaigns_active = camp_qs.filter(status='active').count()
        campaigns_total  = camp_qs.count()

        # Per-campaign stats (top 5 active)
        campaign_rows = []
        for c in camp_qs.filter(status='active').order_by('-emails_sent')[:5]:
            enrolled  = c.enrollments.count()
            replied   = c.enrollments.filter(status__in=['replied', 'unsubscribed']).count()
            reply_rate = round((replied / enrolled * 100) if enrolled else 0, 1)
            campaign_rows.append({
                'id': c.id,
                'name': c.name,
                'emails_sent': c.emails_sent or 0,
                'replies': replied,
                'meetings': c.meetings_booked or 0,
                'enrolled': enrolled,
                'reply_rate': reply_rate,
            })

        # ── Rates ─────────────────────────────────────────────────────
        reply_rate_week = round((replied_week / emails_week * 100) if emails_week else 0, 1)
        meeting_rate    = round((meetings_total / replied_total * 100) if replied_total else 0, 1)

        # ── Daily trend (last 7 days) ──────────────────────────────────
        daily_trend = []
        for i in range(6, -1, -1):
            day_start = today_start - timedelta(days=i)
            day_end   = day_start + timedelta(days=1)
            daily_trend.append({
                'day': day_start.strftime('%a'),
                'date': day_start.strftime('%b %d'),
                'emails': logs_qs.filter(sent_at__gte=day_start, sent_at__lt=day_end, status='sent').count(),
                'leads':  leads_qs.filter(created_at__gte=day_start, created_at__lt=day_end).count(),
                'meetings': meet_qs.filter(created_at__gte=day_start, created_at__lt=day_end).count(),
            })

        # ── Funnel ────────────────────────────────────────────────────
        funnel = [
            {'stage': 'Total Leads',  'count': leads_total,                                             'color': '#a78bfa'},
            {'stage': 'Contacted',    'count': leads_qs.filter(status__in=['contacted','replied','meeting_scheduled','converted']).count(), 'color': '#60a5fa'},
            {'stage': 'Replied',      'count': replied_total,                                           'color': '#4ade80'},
            {'stage': 'Meetings',     'count': meetings_total,                                          'color': '#34d399'},
            {'stage': 'Converted',    'count': leads_qs.filter(status='converted').count(),             'color': '#fbbf24'},
        ]

        # ── Alert ─────────────────────────────────────────────────────
        low_meetings_alert = meetings_week < MEETINGS_ALERT_THRESHOLD

        return {
            # Summary cards
            'leads_today':     leads_today,
            'leads_week':      leads_week,
            'leads_lweek':     leads_lweek,
            'leads_month':     leads_month,
            'leads_total':     leads_total,
            'emails_today':    emails_today,
            'emails_week':     emails_week,
            'emails_lweek':    emails_lweek,
            'emails_month':    emails_month,
            'emails_total':    emails_total,
            'emails_failed':   emails_failed,
            'meetings_today':  meetings_today,
            'meetings_week':   meetings_week,
            'meetings_lweek':  meetings_lweek,
            'meetings_month':  meetings_month,
            'meetings_total':  meetings_total,
            'meetings_scheduled': meetings_scheduled,
            'meetings_completed': meetings_completed,
            'replied_week':    replied_week,
            'replied_lweek':   replied_lweek,
            'replied_total':   replied_total,
            'reply_rate_week': reply_rate_week,
            'meeting_rate':    meeting_rate,
            'campaigns_active': campaigns_active,
            'campaigns_total':  campaigns_total,
            # Breakdowns
            'status_counts':    status_counts,
            'temp_counts':      temp_counts,
            'source_counts':    source_counts,
            'sentiment_counts': sentiment_counts,
            'campaign_rows':    campaign_rows,
            'daily_trend':      daily_trend,
            'funnel':           funnel,
            # Alert
            'low_meetings_alert':      low_meetings_alert,
            'meetings_alert_threshold': MEETINGS_ALERT_THRESHOLD,
        }

    # ------------------------------------------------------------------
    # Daily summary email
    # ------------------------------------------------------------------

    def send_daily_summary(self, company_user) -> bool:
        """
        Send a daily summary email to the company user.
        Returns True if sent successfully.
        """
        to_email = getattr(company_user, 'email', None)
        if not to_email:
            logger.warning('AnalyticsAgent: no email for company_user=%s', company_user.pk)
            return False

        try:
            m = self.compute_metrics(company_user)
        except Exception as exc:
            logger.error('AnalyticsAgent: metrics failed for company_user=%s: %s', company_user.pk, exc)
            return False

        now_str = timezone.now().strftime('%A, %B %d %Y')

        trend_arrow = lambda curr, prev: '▲' if curr > prev else ('▼' if curr < prev else '→')
        trend_color = lambda curr, prev: '#4ade80' if curr > prev else ('#f87171' if curr < prev else '#9ca3af')

        alert_banner = ''
        if m['low_meetings_alert']:
            alert_banner = f"""
            <tr>
              <td style="padding:0 0 20px 0;">
                <div style="background:#fef3c7;border-left:4px solid #f59e0b;border-radius:6px;padding:14px 18px;">
                  <strong style="color:#92400e;">⚠️ Alert: Low Meeting Bookings</strong><br>
                  <span style="color:#78350f;font-size:13px;">
                    Only <strong>{m['meetings_week']}</strong> meeting(s) booked this week —
                    below the target of {m['meetings_alert_threshold']}.
                    Consider reviewing reply rates and follow-up sequences.
                  </span>
                </div>
              </td>
            </tr>"""

        def stat_block(label, value, sub=''):
            return f"""
            <td style="width:25%;padding:0 8px 0 0;vertical-align:top;">
              <div style="background:#f8f4ff;border:1px solid #e9d5ff;border-radius:10px;padding:16px;text-align:center;">
                <div style="font-size:28px;font-weight:700;color:#7c3aed;">{value}</div>
                <div style="font-size:12px;color:#6b21a8;font-weight:600;margin-top:4px;">{label}</div>
                {f'<div style="font-size:11px;color:#9ca3af;margin-top:2px;">{sub}</div>' if sub else ''}
              </div>
            </td>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>SDR Daily Summary</title></head>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:32px 16px;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;">

  <!-- Header -->
  <tr>
    <td style="background:linear-gradient(135deg,#7c3aed,#4f46e5);border-radius:12px 12px 0 0;padding:28px 32px;">
      <div style="color:#fff;font-size:20px;font-weight:700;">AI Employee — SDR Daily Report</div>
      <div style="color:rgba(255,255,255,0.7);font-size:13px;margin-top:4px;">{now_str}</div>
    </td>
  </tr>

  <!-- Body -->
  <tr>
    <td style="background:#fff;border-radius:0 0 12px 12px;padding:28px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0">

        {alert_banner}

        <!-- Summary stats -->
        <tr>
          <td style="padding-bottom:24px;">
            <div style="font-size:15px;font-weight:700;color:#1f2937;margin-bottom:14px;">Today's Activity</div>
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                {stat_block('New Leads', m['leads_today'], f"+{m['leads_week']} this week")}
                {stat_block('Emails Sent', m['emails_today'], f"+{m['emails_week']} this week")}
                {stat_block('Meetings Booked', m['meetings_today'], f"+{m['meetings_week']} this week")}
                {stat_block('Replies', m['replied_week'], f"{m['reply_rate_week']}% reply rate")}
              </tr>
            </table>
          </td>
        </tr>

        <!-- Week vs last week -->
        <tr>
          <td style="padding-bottom:24px;">
            <div style="font-size:15px;font-weight:700;color:#1f2937;margin-bottom:14px;">Week vs Last Week</div>
            <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
              <tr style="background:#f9fafb;">
                <th style="padding:10px 14px;text-align:left;font-size:12px;color:#6b7280;font-weight:600;">Metric</th>
                <th style="padding:10px 14px;text-align:center;font-size:12px;color:#6b7280;font-weight:600;">This Week</th>
                <th style="padding:10px 14px;text-align:center;font-size:12px;color:#6b7280;font-weight:600;">Last Week</th>
                <th style="padding:10px 14px;text-align:center;font-size:12px;color:#6b7280;font-weight:600;">Trend</th>
              </tr>
              <tr style="border-top:1px solid #e5e7eb;">
                <td style="padding:10px 14px;font-size:13px;color:#374151;">New Leads</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;font-weight:600;">{m['leads_week']}</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;color:#6b7280;">{m['leads_lweek']}</td>
                <td style="padding:10px 14px;text-align:center;font-size:14px;color:{trend_color(m['leads_week'], m['leads_lweek'])};">{trend_arrow(m['leads_week'], m['leads_lweek'])}</td>
              </tr>
              <tr style="border-top:1px solid #e5e7eb;background:#f9fafb;">
                <td style="padding:10px 14px;font-size:13px;color:#374151;">Emails Sent</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;font-weight:600;">{m['emails_week']}</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;color:#6b7280;">{m['emails_lweek']}</td>
                <td style="padding:10px 14px;text-align:center;font-size:14px;color:{trend_color(m['emails_week'], m['emails_lweek'])};">{trend_arrow(m['emails_week'], m['emails_lweek'])}</td>
              </tr>
              <tr style="border-top:1px solid #e5e7eb;">
                <td style="padding:10px 14px;font-size:13px;color:#374151;">Replies</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;font-weight:600;">{m['replied_week']}</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;color:#6b7280;">{m['replied_lweek']}</td>
                <td style="padding:10px 14px;text-align:center;font-size:14px;color:{trend_color(m['replied_week'], m['replied_lweek'])};">{trend_arrow(m['replied_week'], m['replied_lweek'])}</td>
              </tr>
              <tr style="border-top:1px solid #e5e7eb;background:#f9fafb;">
                <td style="padding:10px 14px;font-size:13px;color:#374151;">Meetings Booked</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;font-weight:600;">{m['meetings_week']}</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;color:#6b7280;">{m['meetings_lweek']}</td>
                <td style="padding:10px 14px;text-align:center;font-size:14px;color:{trend_color(m['meetings_week'], m['meetings_lweek'])};">{trend_arrow(m['meetings_week'], m['meetings_lweek'])}</td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Active campaigns -->
        {"" if not m['campaign_rows'] else f'''
        <tr>
          <td style="padding-bottom:24px;">
            <div style="font-size:15px;font-weight:700;color:#1f2937;margin-bottom:14px;">Active Campaigns</div>
            <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
              <tr style="background:#f9fafb;">
                <th style="padding:10px 14px;text-align:left;font-size:12px;color:#6b7280;font-weight:600;">Campaign</th>
                <th style="padding:10px 14px;text-align:center;font-size:12px;color:#6b7280;font-weight:600;">Emails</th>
                <th style="padding:10px 14px;text-align:center;font-size:12px;color:#6b7280;font-weight:600;">Replies</th>
                <th style="padding:10px 14px;text-align:center;font-size:12px;color:#6b7280;font-weight:600;">Meetings</th>
                <th style="padding:10px 14px;text-align:center;font-size:12px;color:#6b7280;font-weight:600;">Reply %</th>
              </tr>
              {"".join(f'''
              <tr style="border-top:1px solid #e5e7eb;">
                <td style="padding:10px 14px;font-size:13px;color:#374151;font-weight:500;">{row["name"][:30]}</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;">{row["emails_sent"]}</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;">{row["replies"]}</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;font-weight:600;color:#7c3aed;">{row["meetings"]}</td>
                <td style="padding:10px 14px;text-align:center;font-size:13px;color:#16a34a;">{row["reply_rate"]}%</td>
              </tr>''' for row in m["campaign_rows"])}
            </table>
          </td>
        </tr>
        '''}

        <!-- Footer -->
        <tr>
          <td style="border-top:1px solid #e5e7eb;padding-top:18px;">
            <p style="font-size:12px;color:#9ca3af;margin:0;">
              This is an automated daily report from your AI Employee SDR system.
              Total lifetime stats: {m['leads_total']} leads · {m['emails_total']} emails · {m['meetings_total']} meetings.
            </p>
          </td>
        </tr>

      </table>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""

        subject = f"SDR Daily Report — {m['emails_today']} emails · {m['meetings_today']} meetings · {m['leads_today']} leads [{now_str}]"

        return self._send_email(to_email, subject, html)

    # ------------------------------------------------------------------
    # Low-meetings alert
    # ------------------------------------------------------------------

    def send_low_meetings_alert(self, company_user, meetings_this_week: int) -> bool:
        """Send an alert email when meetings this week are below threshold."""
        to_email = getattr(company_user, 'email', None)
        if not to_email:
            return False

        subject = f"⚠️ SDR Alert: Only {meetings_this_week} meeting(s) booked this week (target: {MEETINGS_ALERT_THRESHOLD})"

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:'Helvetica Neue',Arial,sans-serif;background:#f4f4f7;margin:0;padding:32px;">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#dc2626,#b91c1c);padding:24px 28px;">
    <div style="color:#fff;font-size:18px;font-weight:700;">⚠️ Low Meeting Alert</div>
    <div style="color:rgba(255,255,255,0.75);font-size:12px;margin-top:4px;">AI Employee SDR System</div>
  </div>
  <div style="padding:28px;">
    <p style="font-size:15px;color:#1f2937;">
      Your SDR system has only booked <strong style="color:#dc2626;">{meetings_this_week}</strong> meeting(s)
      this week, which is below the target of <strong>{MEETINGS_ALERT_THRESHOLD}</strong>.
    </p>
    <p style="font-size:13px;color:#6b7280;">Possible actions to improve:</p>
    <ul style="font-size:13px;color:#374151;line-height:1.8;">
      <li>Review reply rates — are emails being opened?</li>
      <li>Check if IMAP is properly detecting positive replies</li>
      <li>Consider adjusting email templates for better engagement</li>
      <li>Verify campaign is active and enrollments are running</li>
      <li>Check if scheduling email has a working calendar/booking link</li>
    </ul>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">
    <p style="font-size:11px;color:#9ca3af;">
      This alert fires when weekly meetings fall below {MEETINGS_ALERT_THRESHOLD}.
      You can change this threshold in analytics_agent.py (MEETINGS_ALERT_THRESHOLD).
    </p>
  </div>
</div>
</body></html>"""

        return self._send_email(to_email, subject, html)

    # ------------------------------------------------------------------
    # Internal SMTP sender
    # ------------------------------------------------------------------

    def _send_email(self, to_email: str, subject: str, html: str) -> bool:
        smtp_host     = getattr(settings, 'EMAIL_HOST',     os.environ.get('EMAIL_HOST', ''))
        smtp_port     = int(getattr(settings, 'EMAIL_PORT', os.environ.get('EMAIL_PORT', 587)))
        smtp_user     = getattr(settings, 'EMAIL_HOST_USER',     os.environ.get('EMAIL_HOST_USER', ''))
        smtp_password = getattr(settings, 'EMAIL_HOST_PASSWORD', os.environ.get('EMAIL_HOST_PASSWORD', ''))
        from_email    = getattr(settings, 'DEFAULT_FROM_EMAIL', smtp_user) or smtp_user

        if not (smtp_host and smtp_user and smtp_password):
            logger.warning('AnalyticsAgent._send_email: SMTP not configured (EMAIL_HOST/USER/PASSWORD missing)')
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From']    = f'AI Employee SDR <{from_email}>'
            msg['To']      = to_email
            msg.attach(MIMEText(html, 'html', 'utf-8'))

            ctx = ssl.create_default_context()
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.login(smtp_user, smtp_password)
                server.sendmail(from_email, to_email, msg.as_string())

            logger.info('AnalyticsAgent: email sent to %s subject="%s"', to_email, subject)
            return True
        except Exception as exc:
            logger.error('AnalyticsAgent._send_email failed to %s: %s', to_email, exc)
            return False
