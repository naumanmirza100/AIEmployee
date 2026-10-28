"""
API views — AI Executive Meeting Assistant
Both company-user endpoints and admin endpoints.
"""

import json
import logging
from html import escape
from datetime import datetime

from django.core.cache import cache
from django.db import models
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, throttle_classes,
)
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from datetime import timedelta

from core.api_key_service import KeyServiceError
from core.scheduling import (
    ScheduleConflict, booking_guard, ensure_free, find_conflicts, login_user_id_for_company_user,
    people_for, suggest_slots, zone_name,
)
from meeting_agent.ai_agents import ExecAgentRegistry
from meeting_agent.clock import held_on, when_text as clock_when_text
from rest_framework.permissions import IsAuthenticated
from meeting_agent.models import (
    ExecutiveMeeting,
    ExecutiveMeetingParticipant,
    MeetingNote,
    MeetingActionItem,
    ExecutiveTask,
    MeetingDocument,
    ExecNotification,
    ExecNotificationChannel,
    ExecMeetingSchedulingChat, ExecMeetingSchedulingChatMessage,
    ExecNotetakerChat, ExecNotetakerChatMessage,
    ExecTaskChat, ExecTaskChatMessage,
    ExecCalendarChat, ExecCalendarChatMessage,
    ExecDocumentChat, ExecDocumentChatMessage,
    ExecNotificationChat, ExecNotificationChatMessage,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------

class _Escaped:
    """A meeting or task as an email shows it: its text escaped. Titles, descriptions and names went into the
    email's HTML as typed, so angle brackets broke the email or became the sender's own markup and links
    (CO-261). Other attributes (times, the organiser, ids) pass through."""

    def __init__(self, obj):
        self._obj = obj

    def __getattr__(self, name):
        value = getattr(self._obj, name)
        return escape(value) if isinstance(value, str) else value


def _email_base_html(content: str, preview_text: str = '') -> str:
    preview = (
        f'<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">'
        f'{preview_text}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>'
        if preview_text else ''
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Email</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f7;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  {preview}
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f4f4f7;min-width:100%;">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:680px;width:100%;">
          <tr>
            <td style="background:linear-gradient(135deg,#7c3aed,#4f46e5);border-radius:12px 12px 0 0;padding:28px 36px;text-align:center;">
              <span style="color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.3px;">AI Employee</span>
              <span style="display:block;color:rgba(255,255,255,0.65);font-size:12px;margin-top:4px;letter-spacing:0.04em;text-transform:uppercase;">Executive Meeting Assistant</span>
            </td>
          </tr>
          <tr>
            <td style="background:#ffffff;padding:36px 36px 28px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;">
              {content}
            </td>
          </tr>
          <tr>
            <td style="background:#f9fafb;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;padding:18px 36px;text-align:center;">
              <p style="margin:0;color:#9ca3af;font-size:11px;line-height:1.6;">
                This is an automated notification from your AI Executive Meeting Assistant.<br/>
                Please do not reply to this email.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _email_detail_row(label: str, value: str) -> str:
    return (
        f'<tr>'
        f'<td style="padding:6px 0;color:#6b7280;font-size:13px;width:110px;vertical-align:top;">{label}</td>'
        f'<td style="padding:6px 0;color:#111827;font-size:13px;font-weight:600;vertical-align:top;">{value}</td>'
        f'</tr>'
    )


def _email_divider() -> str:
    return '<tr><td colspan="2"><hr style="border:none;border-top:1px solid #f3f4f6;margin:6px 0;"/></td></tr>'


def _email_agenda_block(agenda) -> str:
    """Render a meeting's agenda (a list of strings) as an HTML bullet list for
    emails. Returns '' when there's no agenda so it can be dropped straight into
    an f-string."""
    items = [str(a).strip() for a in (agenda or []) if str(a).strip()]
    if not items:
        return ''
    import html as _html
    lis = ''.join(
        f'<li style="margin:0 0 6px;color:#374151;font-size:13px;line-height:1.5;">{_html.escape(it)}</li>'
        for it in items
    )
    return (
        '<div style="margin:16px 0 0;">'
        '<p style="margin:0 0 6px;color:#7c3aed;font-size:12px;font-weight:700;'
        'text-transform:uppercase;letter-spacing:0.06em;">Agenda</p>'
        f'<ul style="margin:0;padding-left:18px;">{lis}</ul>'
        '</div>'
    )


def _send_email_safe(subject, html_body, recipient_email, plain_body=''):
    if not recipient_email or '@' not in recipient_email:
        logger.warning("Email skipped — invalid recipient: %r", recipient_email)
        return
    try:
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings
        logger.info("Sending email to %s | subject: %s", recipient_email, subject)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body or 'Please view this email in an HTML-capable client.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send(fail_silently=False)
        logger.info("Email sent OK to %s", recipient_email)
    except Exception as exc:
        logger.error("Email send FAILED to %s: %s", recipient_email, exc)


def _email_login(company_user, topic, subject, html_body):
    """An Executive Meeting email to one of the company's logins, if they want it.

    Every email this agent sends goes to a dashboard login, and none of them
    asked that login's notification settings, so 'Pause all emails' did not stop
    one of them. `topic` is 'exec_meetings' or 'tasks_assigned'
    (core.notification_settings)."""
    from core.notification_settings import wants_email
    from meeting_agent.leavers import still_with_the_company
    # Someone who has left stays on the lists of the meetings they were in; they
    # used to go on being sent the full details of every change.
    if not still_with_the_company(company_user):
        logger.info("Email not sent to %s: no longer with the company", getattr(company_user, 'id', None))
        return
    try:
        wanted = wants_email(company_user, topic)
    except Exception:
        logger.warning("Could not read notification settings for login %s; sending",
                       getattr(company_user, 'id', None), exc_info=True)
        wanted = True
    if not wanted:
        logger.info("Email not sent to login %s: turned off in their notification settings (%s)",
                    getattr(company_user, 'id', None), topic)
        return
    _send_email_safe(subject, html_body, company_user.email)


def _send_meeting_update_email(participant_cu, meeting, organizer_name, changed_fields):
    subject_title = meeting.title
    meeting, organizer_name = _Escaped(meeting), escape(organizer_name or '')     # (CO-261)
    changed_fields = [escape(str(f)) for f in changed_fields or []]
    scheduled = clock_when_text(meeting)   # when it really is, its zone named; it said "UTC" (CO-210)
    changed_str = ', '.join(changed_fields) if changed_fields else 'details'
    link_row = _email_detail_row('Link', f'<a href="{meeting.meeting_link}" style="color:#7c3aed;">{meeting.meeting_link}</a>') if meeting.meeting_link else ''
    desc_block = (
        f'<p style="margin:16px 0 0;color:#374151;font-size:14px;line-height:1.65;">{meeting.description}</p>'
        if meeting.description else ''
    )
    agenda_block = _email_agenda_block(meeting.agenda)
    content = f"""
      <p style="margin:0 0 6px;color:#111827;font-size:22px;font-weight:700;">Meeting Updated</p>
      <p style="margin:0 0 24px;color:#6b7280;font-size:14px;">
        The following details have changed: <strong style="color:#7c3aed;">{changed_str}</strong>
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:10px;margin-bottom:20px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 14px;color:#7c3aed;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">Meeting Details</p>
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {_email_detail_row('Title', meeting.title)}
              {_email_divider()}
              {_email_detail_row('Date &amp; Time', scheduled)}
              {_email_divider()}
              {_email_detail_row('Duration', f'{meeting.duration_minutes} minutes')}
              {_email_divider()}
              {_email_detail_row('Status', meeting.status.replace('_', ' ').capitalize())}
              {_email_divider()}
              {_email_detail_row('Organizer', organizer_name)}
              {(_email_divider() + link_row) if link_row else ''}
            </table>
            {desc_block}
            {agenda_block}
          </td>
        </tr>
      </table>
      <p style="margin:0;color:#374151;font-size:14px;line-height:1.6;">
        Please update your calendar accordingly.<br/><br/>
        <strong style="color:#111827;">AI Executive Assistant</strong>
      </p>
    """
    html = _email_base_html(content, preview_text=f"Your meeting '{meeting.title}' has been updated.")
    _email_login(participant_cu, 'exec_meetings', f"Meeting Updated: {subject_title}", html)


def _send_meeting_invite_email(participant_cu, meeting, organizer_name):
    subject_title = meeting.title
    meeting, organizer_name = _Escaped(meeting), escape(organizer_name or '')     # (CO-261)
    scheduled = clock_when_text(meeting)   # when it really is, its zone named; it said "UTC" (CO-210)
    first_name = escape((participant_cu.full_name or '').split()[0]) if participant_cu.full_name else 'there'
    join_block = ''
    if meeting.meeting_link:
        join_block = f"""
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:20px 0 0;">
        <tr>
          <td align="center">
            <table cellpadding="0" cellspacing="0" border="0" style="margin:0 auto;">
              <tr>
                <td style="background:#059669;border-radius:8px;">
                  <a href="{meeting.meeting_link}" target="_blank"
                     style="display:inline-block;padding:13px 32px;color:#ffffff;font-size:15px;
                            font-weight:600;text-decoration:none;white-space:nowrap;">
                    🎥 Join Meeting
                  </a>
                </td>
              </tr>
            </table>
            <p style="margin:8px 0 0;color:#d1d5db;font-size:11px;word-break:break-all;">{meeting.meeting_link}</p>
          </td>
        </tr>
      </table>"""
    # Accept or decline from the email (CO-211): an employee cannot open the agent to answer.
    seat = ExecutiveMeetingParticipant.objects.filter(meeting_id=meeting.id, company_user=participant_cu).first()
    if seat is not None:
        join_block += _answer_buttons(seat)
    desc_block = (
        f'<p style="margin:16px 0 0;color:#374151;font-size:14px;line-height:1.65;">{meeting.description}</p>'
        if meeting.description else ''
    )
    agenda_block = _email_agenda_block(meeting.agenda)
    content = f"""
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td align="center" style="padding-bottom:20px;">
            <div style="width:56px;height:56px;background:#faf5ff;border-radius:50%;
                        font-size:26px;line-height:56px;text-align:center;">📅</div>
          </td>
        </tr>
      </table>
      <p style="margin:0 0 6px;color:#111827;font-size:22px;font-weight:700;text-align:center;">
        You're invited, {first_name}!
      </p>
      <p style="margin:0 0 24px;color:#6b7280;font-size:14px;text-align:center;">
        {organizer_name} has added you to a meeting.
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:10px;margin-bottom:4px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 14px;color:#7c3aed;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">Meeting Details</p>
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {_email_detail_row('Title', meeting.title)}
              {_email_divider()}
              {_email_detail_row('Date &amp; Time', scheduled)}
              {_email_divider()}
              {_email_detail_row('Duration', f'{meeting.duration_minutes} minutes')}
              {_email_divider()}
              {_email_detail_row('Status', meeting.status.replace('_', ' ').capitalize())}
              {_email_divider()}
              {_email_detail_row('Organizer', organizer_name)}
            </table>
            {desc_block}
            {agenda_block}
          </td>
        </tr>
      </table>
      {join_block}
      <hr style="border:none;border-top:1px solid #f3f4f6;margin:24px 0 20px;"/>
      <p style="margin:0;color:#374151;font-size:14px;line-height:1.8;">
        Please mark this in your calendar.<br/><br/>
        <strong style="color:#111827;">AI Executive Assistant</strong>
      </p>
    """
    html = _email_base_html(content, preview_text=f"You've been invited to '{meeting.title}' by {organizer_name}.")
    _email_login(participant_cu, 'exec_meetings', f"Meeting Invitation: {subject_title}", html)


def _send_task_assignment_email(assignee_cu, task, assigned_by_name):
    subject_title = task.title
    task, assigned_by_name = _Escaped(task), escape(assigned_by_name or '')     # (CO-261)
    first_name = escape((assignee_cu.full_name or '').split()[0]) if assignee_cu.full_name else 'there'
    priority_color = {'high': '#ef4444', 'medium': '#f59e0b', 'low': '#10b981'}.get(task.priority, '#6b7280')
    desc_block = (
        f'<p style="margin:16px 0 0;color:#374151;font-size:14px;line-height:1.65;">{task.description}</p>'
        if task.description else ''
    )
    content = f"""
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td align="center" style="padding-bottom:20px;">
            <div style="width:56px;height:56px;background:#f0fdf4;border-radius:50%;
                        font-size:26px;line-height:56px;text-align:center;">✅</div>
          </td>
        </tr>
      </table>
      <p style="margin:0 0 6px;color:#111827;font-size:22px;font-weight:700;text-align:center;">
        New Task Assigned
      </p>
      <p style="margin:0 0 24px;color:#6b7280;font-size:14px;text-align:center;">
        Hi {first_name}, {assigned_by_name} has assigned you a task.
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:10px;margin-bottom:4px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 14px;color:#7c3aed;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">Task Details</p>
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {_email_detail_row('Title', task.title)}
              {_email_divider()}
              {_email_detail_row('Priority', f'<span style="color:{priority_color};font-weight:700;">{task.priority.capitalize()}</span>')}
              {_email_divider()}
              {_email_detail_row('Status', task.status.replace('_', ' ').capitalize())}
              {_email_divider()}
              {_email_detail_row('Due Date', str(task.due_date) if task.due_date else 'Not set')}
              {_email_divider()}
              {_email_detail_row('Assigned by', assigned_by_name)}
            </table>
            {desc_block}
          </td>
        </tr>
      </table>
      <hr style="border:none;border-top:1px solid #f3f4f6;margin:24px 0 20px;"/>
      <p style="margin:0;color:#374151;font-size:14px;line-height:1.8;">
        Please log in to the platform to view and manage this task.<br/><br/>
        <strong style="color:#111827;">AI Executive Assistant</strong>
      </p>
    """
    html = _email_base_html(content, preview_text=f"New task assigned: {task.title}")
    _email_login(assignee_cu, 'tasks_assigned', f"Task Assigned: {subject_title}", html)


def _send_subtask_added_email(recipient_cu, parent_task, subtask, added_by_name):
    """Notify a parent task's assignee that a subtask was added under their task.
    Lists the subtask's own assignees (if any) so the recipient knows who's on it."""
    subject_parent, subject_sub = parent_task.title, subtask.title
    parent_task, subtask, added_by_name = _Escaped(parent_task), _Escaped(subtask), escape(added_by_name or '')
    first_name = escape((recipient_cu.full_name or '').split()[0]) if recipient_cu.full_name else 'there'
    sub_assignees = list(subtask.assignees.all())
    assignees_str = ', '.join(escape(cu.full_name or '') for cu in sub_assignees) if sub_assignees else 'No one assigned yet'
    desc_block = (
        f'<p style="margin:16px 0 0;color:#374151;font-size:14px;line-height:1.65;">{subtask.description}</p>'
        if subtask.description else ''
    )
    content = f"""
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td align="center" style="padding-bottom:20px;">
            <div style="width:56px;height:56px;background:#eff6ff;border-radius:50%;
                        font-size:26px;line-height:56px;text-align:center;">🧩</div>
          </td>
        </tr>
      </table>
      <p style="margin:0 0 6px;color:#111827;font-size:22px;font-weight:700;text-align:center;">
        New Subtask Added
      </p>
      <p style="margin:0 0 24px;color:#6b7280;font-size:14px;text-align:center;">
        Hi {first_name}, {added_by_name} added a subtask under your task "{parent_task.title}".
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;margin-bottom:4px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 14px;color:#2563eb;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">Subtask Details</p>
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {_email_detail_row('Parent task', parent_task.title)}
              {_email_divider()}
              {_email_detail_row('Subtask', subtask.title)}
              {_email_divider()}
              {_email_detail_row('Priority', subtask.priority.capitalize())}
              {_email_divider()}
              {_email_detail_row('Due Date', str(subtask.due_date) if subtask.due_date else 'Not set')}
              {_email_divider()}
              {_email_detail_row('Assigned to', assignees_str)}
              {_email_divider()}
              {_email_detail_row('Added by', added_by_name)}
            </table>
            {desc_block}
          </td>
        </tr>
      </table>
      <hr style="border:none;border-top:1px solid #f3f4f6;margin:24px 0 20px;"/>
      <p style="margin:0;color:#374151;font-size:14px;line-height:1.8;">
        Please log in to the platform to view this subtask.<br/><br/>
        <strong style="color:#111827;">AI Executive Assistant</strong>
      </p>
    """
    html = _email_base_html(content, preview_text=f"New subtask added: {subtask.title}")
    _email_login(recipient_cu, 'tasks_assigned', f'Subtask added to "{subject_parent}": {subject_sub}', html)


def _send_meeting_removal_email(cu, meeting, removed_by_name):
    subject_title = meeting.title
    meeting, removed_by_name = _Escaped(meeting), escape(removed_by_name or '')     # (CO-261)
    scheduled = clock_when_text(meeting)   # when it really is, its zone named; it said "UTC" (CO-210)
    first_name = escape((cu.full_name or '').split()[0]) if cu.full_name else 'there'
    content = f"""
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td align="center" style="padding-bottom:20px;">
            <div style="width:56px;height:56px;background:#fef2f2;border-radius:50%;
                        font-size:26px;line-height:56px;text-align:center;">🚫</div>
          </td>
        </tr>
      </table>
      <p style="margin:0 0 6px;color:#111827;font-size:22px;font-weight:700;text-align:center;">
        Removed from Meeting
      </p>
      <p style="margin:0 0 24px;color:#6b7280;font-size:14px;text-align:center;">
        Hi {first_name}, you have been removed from this meeting.
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#fff7f7;border:1px solid #fecaca;border-radius:10px;margin-bottom:20px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 14px;color:#ef4444;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">Meeting Details</p>
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {_email_detail_row('Title', meeting.title)}
              {_email_divider()}
              {_email_detail_row('Date &amp; Time', scheduled)}
              {_email_divider()}
              {_email_detail_row('Removed by', removed_by_name)}
            </table>
          </td>
        </tr>
      </table>
      <p style="margin:0;color:#374151;font-size:14px;line-height:1.6;">
        If you believe this was a mistake, please contact the organizer.<br/><br/>
        <strong style="color:#111827;">AI Executive Assistant</strong>
      </p>
    """
    html = _email_base_html(content, preview_text=f"You have been removed from '{meeting.title}'.")
    _email_login(cu, 'exec_meetings', f"Removed from Meeting: {subject_title}", html)


def _send_task_removal_email(cu, task, removed_by_name):
    subject_title = task.title
    task, removed_by_name = _Escaped(task), escape(removed_by_name or '')     # (CO-261)
    first_name = escape((cu.full_name or '').split()[0]) if cu.full_name else 'there'
    content = f"""
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td align="center" style="padding-bottom:20px;">
            <div style="width:56px;height:56px;background:#fef2f2;border-radius:50%;
                        font-size:26px;line-height:56px;text-align:center;">🚫</div>
          </td>
        </tr>
      </table>
      <p style="margin:0 0 6px;color:#111827;font-size:22px;font-weight:700;text-align:center;">
        Removed from Task
      </p>
      <p style="margin:0 0 24px;color:#6b7280;font-size:14px;text-align:center;">
        Hi {first_name}, you have been removed from this task.
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#fff7f7;border:1px solid #fecaca;border-radius:10px;margin-bottom:20px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 14px;color:#ef4444;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">Task Details</p>
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {_email_detail_row('Title', task.title)}
              {_email_divider()}
              {_email_detail_row('Priority', task.priority.capitalize())}
              {_email_divider()}
              {_email_detail_row('Removed by', removed_by_name)}
            </table>
          </td>
        </tr>
      </table>
      <p style="margin:0;color:#374151;font-size:14px;line-height:1.6;">
        If you believe this was a mistake, please contact the task owner.<br/><br/>
        <strong style="color:#111827;">AI Executive Assistant</strong>
      </p>
    """
    html = _email_base_html(content, preview_text=f"You have been removed from task '{task.title}'.")
    _email_login(cu, 'tasks_assigned', f"Removed from Task: {subject_title}", html)


def _send_task_deleted_email(cu, task_title, task_priority, deleted_by_name):
    subject_title = task_title
    task_title, deleted_by_name = escape(task_title or ''), escape(deleted_by_name or '')     # (CO-261)
    first_name = escape((cu.full_name or '').split()[0]) if cu.full_name else 'there'
    content = f"""
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td align="center" style="padding-bottom:20px;">
            <div style="width:56px;height:56px;background:#fef2f2;border-radius:50%;
                        font-size:26px;line-height:56px;text-align:center;">🗑️</div>
          </td>
        </tr>
      </table>
      <p style="margin:0 0 6px;color:#111827;font-size:22px;font-weight:700;text-align:center;">
        Task Deleted
      </p>
      <p style="margin:0 0 24px;color:#6b7280;font-size:14px;text-align:center;">
        Hi {first_name}, a task you were assigned to has been deleted.
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#fff7f7;border:1px solid #fecaca;border-radius:10px;margin-bottom:20px;">
        <tr>
          <td style="padding:20px 24px;">
            <p style="margin:0 0 14px;color:#ef4444;font-size:12px;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.06em;">Task Details</p>
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {_email_detail_row('Title', task_title)}
              {_email_divider()}
              {_email_detail_row('Priority', task_priority.capitalize())}
              {_email_divider()}
              {_email_detail_row('Deleted by', deleted_by_name)}
            </table>
          </td>
        </tr>
      </table>
      <p style="margin:0;color:#374151;font-size:14px;line-height:1.6;">
        This task has been permanently removed from the system.<br/><br/>
        <strong style="color:#111827;">AI Executive Assistant</strong>
      </p>
    """
    html = _email_base_html(content, preview_text=f"Task '{task_title}' has been deleted.")
    _email_login(cu, 'tasks_assigned', f"Task Deleted: {subject_title}", html)


# ---------------------------------------------------------------------------
# Throttle classes
# ---------------------------------------------------------------------------

class ExecLLMThrottle(SimpleRateThrottle):
    scope = 'exec_llm'

    def get_cache_key(self, request, view):
        if hasattr(request, 'user') and request.user:
            ident = getattr(request.user, 'id', None) or getattr(request.user, 'pk', None)
            if ident:
                return self.cache_format % {'scope': self.scope, 'ident': ident}
        return self.get_ident(request)


class ExecCRUDThrottle(SimpleRateThrottle):
    scope = 'exec_crud'

    def get_cache_key(self, request, view):
        if hasattr(request, 'user') and request.user:
            ident = getattr(request.user, 'id', None) or getattr(request.user, 'pk', None)
            if ident:
                return self.cache_format % {'scope': self.scope, 'ident': ident}
        return self.get_ident(request)


# One address both reads a meeting's stored notes and asks the AI to write them. Reading
# was counted as AI use: every meeting card opened spent one of the 30 an hour, and after
# a morning's use the AI stopped and notes showed as missing. A key of None is not counted.
_READS = ('GET', 'HEAD', 'OPTIONS')


class ExecLLMWhenWritingThrottle(ExecLLMThrottle):
    def get_cache_key(self, request, view):
        return None if request.method in _READS else super().get_cache_key(request, view)


class ExecCRUDWhenReadingThrottle(ExecCRUDThrottle):
    def get_cache_key(self, request, view):
        return super().get_cache_key(request, view) if request.method in _READS else None


# The daily digest was asked of the AI every time the overview opened. It is now kept for
# the day and made again only when the refresh button asks for it.
DIGEST_KEEP_SECONDS = 26 * 3600


def _digest_key(company_user):
    from meeting_agent.clock import company_zone
    from zoneinfo import ZoneInfo
    day = timezone.now().astimezone(ZoneInfo(company_zone(company_user.company))).date()
    return f'exec_digest:{company_user.id}:{day.isoformat()}'


def _wants_new_digest(request):
    return str(request.data.get('refresh', '')).lower() in ('1', 'true', 'yes')


class ExecDigestThrottle(ExecLLMThrottle):
    """Counted only when the AI is really asked: a digest already made today costs nothing."""

    def get_cache_key(self, request, view):
        if not _wants_new_digest(request) and cache.get(_digest_key(request.user)) is not None:
            return None
        return super().get_cache_key(request, view)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The shared calendar
#
# Executive meetings were checked, at most, against the organiser's other
# executive meetings. They could land on an interview, a project or HR meeting,
# approved leave or a company holiday. They now ask the calendar every agent
# shares (core.scheduling), and their own busy time is on it.
# ---------------------------------------------------------------------------

def _occupies_people(meeting) -> bool:
    """Is this meeting on in a way that takes people's time? The calendar's own rule."""
    from core.scheduling.sources import SOURCES
    return meeting.status in SOURCES['exec'].ACTIVE


def _calendar_people(company_users):
    """The employee logins behind these dashboard logins and seats. Someone
    who is nobody's employee login has no calendar, and is left out."""
    ids = {login_user_id_for_company_user(cu) for cu in company_users}
    return sorted(i for i in ids if i)


LINK_RULE = 'The meeting link must be a web address starting with http:// or https://.'


def _web_link(link) -> bool:
    """A meeting link goes into every email's Join button: only a web address (CO-261). Any text was kept."""
    return str(link).lower().startswith(('http://', 'https://'))


def _meeting_context(meeting, writer):
    """What a document written for a meeting knows of it: when, who, the agenda, and its notes."""
    lines = [f'Meeting: {meeting.title}, {clock_when_text(meeting)}, {meeting.duration_minutes} minutes.',
             f'Prepared by: {writer.full_name or writer.email}. Today: {_today(writer):%d %b %Y}.']
    people = [p.company_user.full_name for p in meeting.participants.select_related('company_user')]
    if people:
        lines.append('Attendees: ' + ', '.join(n for n in people if n) + '.')
    if meeting.agenda:
        lines.append('Agenda: ' + '; '.join(str(a) for a in meeting.agenda) + '.')
    try:
        note = meeting.note
    except Exception:
        note = None
    if note and note.ai_summary:
        lines.append('Notes: ' + note.ai_summary)
    if note and note.key_decisions:
        lines.append('Decisions: ' + '; '.join(str(d) for d in note.key_decisions) + '.')
    for item in meeting.action_items.select_related('assignee')[:20]:
        owner = item.assignee.full_name if item.assignee else item.owner_name
        lines.append(f"Action: {item.title}" + (f' ({owner})' if owner else '')
                     + (f', due {item.due_date:%d %b %Y}' if item.due_date else '') + '.')
    return '\n'.join(lines)


def _bad_choice(model, data, *fields):
    """Why one of these fields in the request is not a value the model allows, or None."""
    for field in fields:
        if field in data and data[field] not in (None, ''):
            allowed = [key for key, _ in model._meta.get_field(field).choices or getattr(model, f'{field.upper()}_CHOICES', [])]
            if allowed and data[field] not in allowed:
                return f'{field.title()} must be one of: {", ".join(allowed)}.'
    return None


def _today(company_user):
    """Today on the company's clock, for the agent's defaults; the server's UTC date was a day off at night (CO-210)."""
    from meeting_agent.clock import today
    return today(company_user.company)


def _company_zone(company_user, fallback='') -> str:
    """A company holiday is a whole day on the company's own clock; with none set, the browser's (CO-210)."""
    from meeting_agent.clock import company_zone
    return company_zone(company_user.company, fallback)


def _real(company_user, typed, fallback=''):
    """The instant a time kept by this agent means. It is kept as typed and
    filed as UTC; the shared calendar needs when it really is (meeting_agent.clock).
    `fallback` is the zone sent with the meeting, for a company with none set."""
    from meeting_agent.clock import real_instant
    return real_instant(typed, company_user.company, fallback)


def _browser_zone(request, meeting=None) -> str:
    """The zone the organiser's browser sends with a meeting, else the one it was made with ('' if none)."""
    return zone_name(request.data.get('timezone_name'), default='') or (
        zone_name(getattr(meeting, 'timezone_name', ''), default='') if meeting else '')


def _participant_for(user_id, user_type, company):
    """The row a picked person takes part through: a dashboard login, or the
    seat that stands in for an employee login. None when there is no such
    active person in this company."""
    from core.models import CompanyUser
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None
    if user_type == 'profile':
        # An employee login: they take part through a seat, which is not a login.
        return _seat_for_employee(user_id, company)
    return CompanyUser.objects.filter(id=user_id, company=company, is_active=True).first()


def _picked_people(company, picks):
    """The employee logins behind people picked in the dialog, given as
    ``[{user_id, user_type}]``. Nobody is seated: this is for asking only."""
    from core.models import CompanyUser, UserProfile
    ids = set()
    for pick in picks if isinstance(picks, list) else []:
        try:
            picked_id = int(pick.get('user_id'))
        except (AttributeError, TypeError, ValueError):
            continue
        if pick.get('user_type') == 'profile':
            found = (UserProfile.objects.filter(id=picked_id, company=company, user__is_active=True)
                     .values_list('user_id', flat=True).first())
        else:
            login = CompanyUser.objects.filter(id=picked_id, company=company, is_active=True).first()
            found = login_user_id_for_company_user(login) if login else None
        if found:
            ids.add(found)
    return ids


def _shared_clashes(people, typed, duration, company_user, exclude_id=None, fallback=''):
    """What these people have then on the calendar every agent shares: other
    meetings, interviews, sales calls, leave, a company holiday. In the shape
    `check_conflicts` answers with, and each marked ``blocking``: the meeting
    will be refused, not booked over it. `typed` is the time as this agent
    keeps it."""
    if not people:
        return []
    zone, starts = _company_zone(company_user, fallback), _real(company_user, typed, fallback)
    found = find_conflicts(people, starts, starts + timedelta(minutes=duration),
                           exclude=[('exec', exclude_id)] if exclude_id else (),
                           viewer_source='exec', tz_name=zone)
    return [{'id': clash.source_id if clash.source == 'exec' else None,
             'title': clash.describe(zone), 'scheduled_at': clash.starts_at.isoformat(),
             'duration_minutes': int((clash.ends_at - clash.starts_at).total_seconds() // 60),
             'status': 'busy', 'source': clash.source, 'blocking': True}
            for clash in found]


def _free_times(people, typed, duration, company_user, exclude_id=None, fallback='', limit=6):
    """When everyone is free instead, that day and then the next weekdays, as times this agent keeps them
    (wall-clock, no zone), so the screen can put one straight into the form. A refused time named no other."""
    from zoneinfo import ZoneInfo
    zone = _company_zone(company_user, fallback)
    starts = suggest_slots(people, _real(company_user, typed, fallback), duration, tz_name=zone,
                           exclude=[('exec', exclude_id)] if exclude_id else (), limit=limit)
    return [s.astimezone(ZoneInfo(zone)).replace(tzinfo=None).isoformat(timespec='minutes') for s in starts]


def _all_clashes(own, shared):
    """The agent's own answer and the shared calendar's, each meeting once.
    A meeting both know of keeps the agent's wording, which the organiser may
    read in full, and is marked as blocking."""
    blocking = {c['id'] for c in shared if c['id']}
    known = {c.get('id') for c in own}
    return ([dict(c, blocking=True) if c.get('id') in blocking else c for c in own]
            + [c for c in shared if not c['id'] or c['id'] not in known])


def _bell_invited(people, meeting, organizer_name):
    """The invitation in each person's bell too (meeting_agent.bell); the email is sent on its own."""
    from meeting_agent.bell import ring
    ring(people, title=f'{organizer_name} invited you: {meeting.title}'[:255],
         message=f'{clock_when_text(meeting)}. Accept or decline it in your meetings.',
         kind='exec_meeting_invite', link='/exec-meeting/dashboard?tab=meetings', email=False,
         data={'meeting_id': meeting.id})


def _bell_changed(people, meeting, what):
    """A change to a meeting someone is in, in their bell (the email is sent on its own)."""
    from meeting_agent.bell import ring
    ring(people, title=f'{meeting.title}: {what}'[:255], message=f'{meeting.title}, {clock_when_text(meeting)}: {what}.',
         kind='exec_meeting_changed', link='/exec-meeting/dashboard?tab=meetings', email=False,
         data={'meeting_id': meeting.id})


def _invite_all(targets, meeting, organizer_name):
    """Email each person their invitation, off the request: a meeting with ten
    people must not make the organiser wait for ten emails."""
    import threading
    _bell_invited(targets, meeting, organizer_name)
    targets = [t for t in targets if t.email]
    if not targets:
        return

    def send():
        for target in targets:
            _send_meeting_invite_email(target, meeting, organizer_name)

    threading.Thread(target=send, daemon=True).start()


def _get_agent(name, company_user):
    agent = ExecAgentRegistry.get_agent(name)
    agent.company_id = company_user.company_id
    return agent


def _parse_datetime(value):
    """Parse ISO datetime string to aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt
    except (ValueError, AttributeError):
        return None


def _is_weekend(due_date):
    """True if a YYYY-MM-DD string (or date) falls on Saturday/Sunday."""
    if not due_date:
        return False
    try:
        d = due_date if hasattr(due_date, 'weekday') else datetime.strptime(str(due_date)[:10], '%Y-%m-%d').date()
        return d.weekday() >= 5  # 5 = Saturday, 6 = Sunday
    except (ValueError, TypeError):
        return False


def _serialize_meeting(meeting, include_participants=False, viewer=None):
    data = {
        'id': meeting.id,
        'title': meeting.title,
        'description': meeting.description,
        'agenda': meeting.agenda,
        'meeting_link': meeting.meeting_link,
        'scheduled_at': meeting.scheduled_at.isoformat(),
        'duration_minutes': meeting.duration_minutes,
        'timezone_name': meeting.timezone_name,
        'status': meeting.status,
        'recurrence': meeting.recurrence,
        'recurrence_end_date': meeting.recurrence_end_date.isoformat() if meeting.recurrence_end_date else None,
        'organizer_id': meeting.organizer_id,
        'organizer_name': meeting.organizer.full_name if hasattr(meeting, 'organizer') else '',
        'created_at': meeting.created_at.isoformat(),
    }
    if viewer is not None:
        # An invited login sees the meeting too (CO-65); `mine` tells the screen it may only reply to it.
        data['mine'] = meeting.organizer_id == viewer.id
        if not data['mine']:
            mine = meeting.participants.filter(company_user=viewer).first()
            data['my_response'] = mine.response if mine else None
    if include_participants:
        data['participants'] = [
            {
                'id': p.id,
                'company_user_id': p.company_user_id,
                'name': p.company_user.full_name,
                'response': p.response,
                'counter_proposed_time': p.counter_proposed_time.isoformat() if p.counter_proposed_time else None,
                'reason': p.reason,
            }
            for p in meeting.participants.select_related('company_user').all()
        ]
    return data


def _seat_for_employee(profile_id, company):
    """The CompanyUser row that stands in for an employee in meetings and tasks,
    or None when no active employee of this company has that profile id.

    Participants and assignees are stored as CompanyUser, and an employee login
    has none, so a row is made for them. It is a seat, NOT a login: it is created
    inactive, which sign-in, password reset and token checks all refuse. It used
    to be created active with a random password, so the employee could claim it
    with "Forgot password" and open the whole company dashboard: every
    candidate, every project, the AI keys.
    """
    import secrets
    from django.contrib.auth.hashers import make_password
    from core.models import CompanyUser, UserProfile
    profile = (UserProfile.objects.select_related('user')
               .filter(id=profile_id, company=company, user__is_active=True).first())
    if profile is None:
        return None
    user = profile.user
    seat, _ = CompanyUser.objects.get_or_create(
        company=company, email=user.email,
        defaults={'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
                  'role': profile.role or 'company_user',
                  'password_hash': make_password(secrets.token_urlsafe(16)),
                  'is_active': False},
    )
    return seat


def _login_named(company, name):
    """The company's active login with this name: the full name, or a first name only one login has."""
    from core.models import CompanyUser as _CU
    name = ' '.join((name or '').split())
    if not name:
        return None
    logins = _CU.objects.filter(company=company, is_active=True)
    found = list(logins.filter(full_name__iexact=name)[:2])
    if len(found) != 1 and ' ' not in name:
        found = list(logins.filter(full_name__istartswith=name + ' ')[:2])
    return found[0] if len(found) == 1 else None


def _member_named(company, name):
    """The login or employee with this name (an employee through their seat), or None. The notes name who does
    each item, and most people are employees, not logins: matched to logins only, Usman's item was given to
    nobody, and so was the task made from it (live run, 28 Oct 2026)."""
    login = _login_named(company, name)
    if login is not None:
        return login
    from core.models import UserProfile
    name = ' '.join((name or '').split()).lower()
    if not name:
        return None
    profiles = list(UserProfile.objects.select_related('user').filter(company=company, user__is_active=True)
                    .only('id', 'user__first_name', 'user__last_name'))
    found = [p for p in profiles if f'{p.user.first_name} {p.user.last_name}'.strip().lower() == name]
    if len(found) != 1 and ' ' not in name:
        found = [p for p in profiles if (p.user.first_name or '').strip().lower() == name]
    return _seat_for_employee(found[0].id, company) if len(found) == 1 else None


def _resolve_assignees(assignee_list, company):
    """
    Accepts a list of {id, user_type} dicts from the frontend.
    Returns a list of CompanyUser instances; an employee gets a seat
    (see _seat_for_employee).
    """
    from core.models import CompanyUser as _CU
    result = []
    for item in (assignee_list or []):
        uid = item.get('id')
        utype = item.get('user_type', 'company_user')
        if not uid:
            continue
        if utype == 'profile':
            seat = _seat_for_employee(uid, company)
            if seat is not None:
                result.append(seat)
        else:
            try:
                result.append(_CU.objects.get(id=uid, company=company))
            except _CU.DoesNotExist:
                pass
    return result


def _serialize_task(task, include_subtasks=True, viewer=None):
    assignees = [
        {'id': cu.id, 'full_name': cu.full_name, 'email': cu.email}
        for cu in task.assignees.all()
    ]
    data = {
        'id': task.id,
        # A task given to the viewer by someone else: they may move its status on, nothing more.
        'yours': viewer is None or task.company_user_id == viewer.id,
        'given_by': task.company_user.full_name if task.company_user_id else '',
        'title': task.title,
        'description': task.description,
        'status': task.status,
        'priority': task.priority,
        'due_date': task.due_date if isinstance(task.due_date, str) else (task.due_date.isoformat() if task.due_date else None),
        'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
        'ai_reasoning': task.ai_reasoning,
        'assignees': assignees,
        'linked_meeting_id': task.linked_meeting_id,
        'parent_task_id': task.parent_task_id,
        'created_at': task.created_at.isoformat(),
        'updated_at': task.updated_at.isoformat(),
    }
    if include_subtasks:
        subtasks = list(task.subtasks.all())
        data['subtasks'] = [_serialize_task(st, include_subtasks=False, viewer=viewer) for st in subtasks]
        data['subtask_count'] = len(subtasks)
        data['subtask_done_count'] = sum(1 for st in subtasks if st.status == 'done')
    return data


def _serialize_notification(notif):
    return {
        'id': notif.id,
        'notification_type': notif.notification_type,
        'severity': notif.severity,
        'title': notif.title,
        'message': notif.message,
        'data': notif.data,
        'is_read': notif.is_read,
        'meeting_id': notif.meeting_id,
        'created_at': notif.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------
# Shared, dependency-free page slicing for the exec-meeting list endpoints.
# Reads ?page= and ?page_size= from the request, clamps them to sane bounds,
# and returns (page_queryset, meta) where meta describes the full result set
# so the frontend can render "Page X of Y" controls. Total count is computed
# once on the (already filtered) queryset before slicing.

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _paginate(qs, request, default_size=DEFAULT_PAGE_SIZE):
    """Slice a queryset for the requested page. Returns (items, meta)."""
    try:
        page = int(request.query_params.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.query_params.get('page_size', default_size))
    except (TypeError, ValueError):
        page_size = default_size
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)

    total = qs.count()
    total_pages = max((total + page_size - 1) // page_size, 1)
    # Snap an out-of-range page back to the last real page.
    if page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    end = start + page_size
    items = list(qs[start:end])
    meta = {
        'page': page,
        'page_size': page_size,
        'total': total,
        'total_pages': total_pages,
        'has_next': page < total_pages,
        'has_prev': page > 1,
    }
    return items, meta


# ===========================================================================
# MEETINGS
# ===========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def schedule_meeting_ai(request):
    """Parse a natural-language meeting request and optionally create the meeting."""
    company_user = request.user
    message = request.data.get('message', '').strip()
    create = request.data.get('create', False)

    if not message:
        return Response({'status': 'error', 'message': 'message is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        agent = _get_agent('meeting_scheduling', company_user)
        parsed = agent.parse_meeting_request(message, company_user.id)

        if not parsed:
            return Response({'status': 'error', 'message': 'Could not parse meeting request.'}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        result = {'status': 'success', 'parsed': parsed}

        if create:
            scheduled_at = _parse_datetime(parsed.get('scheduled_at'))
            if not scheduled_at:
                return Response({'status': 'error', 'message': 'Could not determine meeting time.'}, status=status.HTTP_400_BAD_REQUEST)

            duration = int(parsed.get('duration_minutes') or 60)
            conflicts = agent.check_conflicts(company_user.id, scheduled_at, duration)
            # And anything the organiser has in another agent, their leave, or a company holiday.
            conflicts = _all_clashes(conflicts, _shared_clashes(_calendar_people([company_user]), scheduled_at,
                                                                duration, company_user,
                                                                fallback=_browser_zone(request)))

            if conflicts:
                result['conflicts'] = conflicts
                result['message'] = 'Meeting has conflicts. Review before creating.'
            else:
                # AI may hand back "null"/"none"/non-ISO for the recurrence end
                # date — coerce anything unparseable to None so the DB doesn't reject it.
                rec_end_raw = parsed.get('recurrence_end_date')
                rec_end = None
                if rec_end_raw and str(rec_end_raw).strip().lower() not in ('null', 'none', 'n/a', 'tbd', ''):
                    try:
                        rec_end = datetime.strptime(str(rec_end_raw)[:10], '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        rec_end = None
                meeting = ExecutiveMeeting.objects.create(
                    organizer=company_user,
                    title=parsed.get('title', 'Executive Meeting'),
                    description=parsed.get('description', ''),
                    agenda=parsed.get('agenda', []),
                    meeting_link=parsed.get('meeting_link', ''),
                    scheduled_at=scheduled_at,
                    duration_minutes=duration,
                    timezone_name=_browser_zone(request) or 'UTC',
                    recurrence=parsed.get('recurrence', 'none'),
                    recurrence_end_date=rec_end,
                )
                result['meeting'] = _serialize_meeting(meeting)
                result['message'] = 'Meeting created successfully.'

        return Response(result, status=status.HTTP_200_OK)
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("schedule_meeting_ai error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def generate_meeting_description(request):
    """AI-expand a meeting title + a few rough points into a description + agenda."""
    company_user = request.user
    title = (request.data.get('title') or '').strip()
    points = (request.data.get('points') or '').strip()

    if not points:
        return Response({'status': 'error', 'message': 'points is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        agent = _get_agent('meeting_scheduling', company_user)
        data = agent.generate_description(title, points)
        return Response({'status': 'success', 'data': data}, status=status.HTTP_200_OK)
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("generate_meeting_description error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_list(request):
    """List meetings or create one manually."""
    company_user = request.user

    if request.method == 'GET':
        status_filter = request.query_params.get('status')
        search = (request.query_params.get('search') or '').strip()
        date_filter = (request.query_params.get('date') or '').strip()
        participant_id = (request.query_params.get('participant') or '').strip()
        # Meetings it arranged and meetings it is invited to. An invitee only got an email telling it to log in,
        # and then could not find the meeting (CO-65).
        qs = (ExecutiveMeeting.objects
              .filter(models.Q(organizer=company_user) | models.Q(participants__company_user=company_user))
              .distinct().select_related('organizer'))
        if status_filter:
            qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(models.Q(title__icontains=search) | models.Q(description__icontains=search))
        if date_filter:
            # Filter by the calendar day the meeting is scheduled on (YYYY-MM-DD).
            try:
                day = datetime.strptime(date_filter, '%Y-%m-%d').date()
                qs = qs.filter(scheduled_at__date=day)
            except (ValueError, TypeError):
                pass
        if participant_id:
            # Meetings a given company user takes part in (organizer or invitee).
            try:
                pid = int(participant_id)
                qs = qs.filter(
                    models.Q(organizer_id=pid) | models.Q(participants__company_user_id=pid)
                ).distinct()
            except (ValueError, TypeError):
                pass
        page_items, meta = _paginate(qs, request)
        data = [_serialize_meeting(m, viewer=company_user) for m in page_items]
        return Response({'status': 'success', 'meetings': data, 'count': len(data), 'pagination': meta})

    # POST — manual create
    title = request.data.get('title', '').strip()
    scheduled_at_str = request.data.get('scheduled_at', '')
    if not title or not scheduled_at_str:
        return Response({'status': 'error', 'message': 'title and scheduled_at are required.'}, status=status.HTTP_400_BAD_REQUEST)

    scheduled_at = _parse_datetime(scheduled_at_str)
    if not scheduled_at:
        return Response({'status': 'error', 'message': 'Invalid scheduled_at format. Use ISO 8601.'}, status=status.HTTP_400_BAD_REQUEST)

    meeting_link = str(request.data.get('meeting_link') or '').strip()
    if meeting_link and not _web_link(meeting_link):
        return Response({'status': 'error', 'message': LINK_RULE}, status=status.HTTP_400_BAD_REQUEST)
    if not meeting_link:
        import secrets, string
        slug = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10))
        meeting_link = f'https://meet.jit.si/exec-{slug}'

    duration = int(request.data.get('duration_minutes', 60))
    # The people invited come with the meeting, so it is booked for all of them or for nobody. They
    # used to be added one request each afterwards: one busy person left a meeting made without them.
    picks = request.data.get('participants') or []
    targets = []
    for pick in picks if isinstance(picks, list) else []:
        target = _participant_for((pick or {}).get('user_id'), (pick or {}).get('user_type', 'company_user'),
                                  company_user.company)
        if target is None:
            return Response({'status': 'error', 'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if target.id != company_user.id and target not in targets:
            targets.append(target)
    people = _calendar_people([company_user, *targets])
    try:
        # Refused if the organiser or anyone invited is busy anywhere: another agent's meeting, an
        # interview, a sales call, leave, a company holiday.
        with booking_guard(people):
            zone = _browser_zone(request)
            ensure_free(people, _real(company_user, scheduled_at, zone), duration, tz_name=_company_zone(company_user, zone),
                        viewer_source='exec')
            meeting = ExecutiveMeeting.objects.create(
                organizer=company_user,
                title=title,
                description=request.data.get('description', ''),
                agenda=request.data.get('agenda', []),
                meeting_link=meeting_link,
                scheduled_at=scheduled_at,
                duration_minutes=duration,
                timezone_name=zone or 'UTC',
                recurrence=request.data.get('recurrence', 'none'),
            )
            for target in targets:
                ExecutiveMeetingParticipant.objects.create(meeting=meeting, company_user=target)
    except ScheduleConflict as clash:
        return clash.response()
    _invite_all(targets, meeting, company_user.full_name)
    return Response({'status': 'success', 'meeting': _serialize_meeting(meeting, include_participants=bool(targets))},
                    status=status.HTTP_201_CREATED)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_filter_users(request):
    """Distinct participants (real users) across the current user's meetings —
    powers the 'by user' dropdown on the Meetings filter bar. The company
    account itself (the organizer) is intentionally excluded — the dropdown
    lists the actual people invited to meetings, not the account owner."""
    from core.models import CompanyUser
    company_user = request.user
    from meeting_agent.models import ExecutiveMeetingParticipant
    my_meeting_ids = ExecutiveMeeting.objects.filter(
        organizer=company_user
    ).values_list('id', flat=True)
    # Participant user ids across those meetings, minus the organizer/account.
    part_ids = set(
        ExecutiveMeetingParticipant.objects.filter(
            meeting_id__in=list(my_meeting_ids)
        ).values_list('company_user_id', flat=True)
    )
    part_ids.discard(company_user.id)
    users = CompanyUser.objects.filter(id__in=part_ids).order_by('full_name')
    data = [{'id': u.id, 'full_name': u.full_name, 'email': u.email} for u in users]
    return Response({'status': 'success', 'users': data, 'count': len(data)})


@api_view(['GET', 'PATCH', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_detail(request, meeting_id):
    """Get, update, or delete a meeting."""
    company_user = request.user
    meeting = get_object_or_404(
        ExecutiveMeeting.objects.filter(
            models.Q(organizer=company_user) | models.Q(participants__company_user=company_user)).distinct(),
        id=meeting_id)

    if request.method == 'GET':
        return Response({'status': 'success', 'meeting': _serialize_meeting(meeting, include_participants=True,
                                                                            viewer=company_user)})
    if meeting.organizer_id != company_user.id:
        who = meeting.organizer.full_name or meeting.organizer.email
        return Response({'status': 'error', 'code': 'organizer_only', 'message': (
            f'Only {who}, who arranged this meeting, can change or cancel it. You can accept or decline it.')},
            status=status.HTTP_403_FORBIDDEN)

    if request.method == 'PATCH':
        updatable = ['title', 'description', 'agenda', 'meeting_link',
                     'duration_minutes', 'status', 'recurrence']
        if request.data.get('meeting_link') and not _web_link(str(request.data['meeting_link']).strip()):
            return Response({'status': 'error', 'message': LINK_RULE}, status=status.HTTP_400_BAD_REQUEST)
        # The browser's zone comes with every save (CO-210); it is not a change to tell anyone about.
        if _browser_zone(request):
            meeting.timezone_name = _browser_zone(request)
        changed_fields = []
        was = (_occupies_people(meeting), meeting.scheduled_at, meeting.duration_minutes)
        for field in updatable:
            if field in request.data:
                if getattr(meeting, field) != request.data[field]:
                    changed_fields.append(field.replace('_', ' '))
                setattr(meeting, field, request.data[field])
        if 'scheduled_at' in request.data:
            dt = _parse_datetime(request.data['scheduled_at'])
            if dt and dt != meeting.scheduled_at:
                changed_fields.append('date/time')
                meeting.scheduled_at = dt
        now = (_occupies_people(meeting), meeting.scheduled_at, meeting.duration_minutes)
        if now[0] and now != was:
            # A new time or length, or a cancelled meeting brought back: everyone in it must be free.
            people = people_for('exec', meeting)
            try:
                with booking_guard(people):
                    ensure_free(people, _real(company_user, meeting.scheduled_at, meeting.timezone_name),
                                meeting.duration_minutes,
                                tz_name=_company_zone(company_user, meeting.timezone_name),
                                exclude=[('exec', meeting.id)],
                                viewer_source='exec')
                    meeting.save()
            except ScheduleConflict as clash:
                return clash.response()
        else:
            meeting.save()

        # Notify existing participants only when calendar-relevant fields change.
        # Run in a background thread with a short delay so any concurrent
        # participant-remove requests finish writing to DB first.
        calendar_fields = {'date/time', 'duration minutes', 'meeting link', 'title', 'status'}
        if any(f in calendar_fields for f in changed_fields):
            import threading as _threading
            meeting_id_snap = meeting.id
            organizer_name_snap = company_user.full_name
            changed_snap = list(changed_fields)

            def _notify():
                import time as _time
                _time.sleep(2)  # let any in-flight DELETE requests commit first
                from meeting_agent.models import ExecutiveMeeting as _EM
                try:
                    _meeting = _EM.objects.get(id=meeting_id_snap)
                    # Not to people who declined, and a meeting that is not on tells nobody unless its status
                    # changed: editing a cancelled or finished one emailed everyone "Meeting updated" (CO-257).
                    if not _occupies_people(_meeting) and 'status' not in changed_snap:
                        return
                    told = [_p.company_user for _p in _meeting.participants.select_related('company_user')
                            .exclude(response='rejected') if _p.company_user_id != company_user.id]
                    what = 'cancelled' if _meeting.status == 'cancelled' else 'changed: ' + ', '.join(changed_snap)
                    _bell_changed(told, _meeting, what)
                    for _cu in told:
                        if _cu.email:
                            _send_meeting_update_email(_cu, _meeting, organizer_name_snap, changed_snap)
                except Exception as _e:
                    logger.error("Meeting update notify error: %s", _e)

            _threading.Thread(target=_notify, daemon=True).start()

        return Response({'status': 'success', 'meeting': _serialize_meeting(meeting)})

    if request.method == 'DELETE':
        was_on = _occupies_people(meeting)
        meeting.status = 'cancelled'
        meeting.save()
        # The people invited are told; cancelling here said nothing to anyone.
        if was_on:
            told = [p.company_user for p in meeting.participants.select_related('company_user')
                    .exclude(response='rejected') if p.company_user_id != company_user.id]
            _bell_changed(told, meeting, 'cancelled')
            for cu in told:
                if cu.email:
                    _send_meeting_update_email(cu, meeting, company_user.full_name, ['status'])
        return Response({'status': 'success', 'message': 'Meeting cancelled.'})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def search_company_users(request):
    """Search company users by name/email for participant autocomplete.

    Returns both CompanyUser records and UserProfile-backed users that belong
    to the same company, so users added via the admin 'Add User' panel also
    appear in the results.
    """
    from core.models import CompanyUser, UserProfile
    company_user = request.user
    q = request.query_params.get('q', '').strip()
    # `all=true` powers the "View all members" panel: return every member of
    # the company (no 2-char requirement, a much higher cap) instead of the
    # autocomplete's short filtered slice. When not set, behaviour is the
    # old typeahead: nothing until 2+ chars, capped at 10 per source.
    show_all = request.query_params.get('all', '').strip().lower() in ('1', 'true', 'yes')
    if not show_all and len(q) < 2:
        return Response({'status': 'success', 'users': []})

    limit = 500 if show_all else 10

    # 1. CompanyUser accounts (self-registered via invitation link)
    cu_qs = CompanyUser.objects.filter(
        company=company_user.company,
        is_active=True,
    )
    if not show_all:
        cu_qs = cu_qs.filter(
            models.Q(full_name__icontains=q) | models.Q(email__icontains=q)
        )
    cu_qs = cu_qs.values('id', 'full_name', 'email', 'role').order_by('full_name')[:limit]
    results = list(cu_qs)

    # 2. UserProfile-backed users created via the admin panel
    existing_emails = {u['email'] for u in results}
    up_qs = UserProfile.objects.filter(
        company=company_user.company, user__is_active=True,
    )
    if not show_all:
        up_qs = up_qs.filter(
            models.Q(user__first_name__icontains=q)
            | models.Q(user__last_name__icontains=q)
            | models.Q(user__email__icontains=q)
            | models.Q(user__username__icontains=q)
        )
    up_qs = up_qs.select_related('user').exclude(user__email__in=existing_emails)[:limit]

    for up in up_qs:
        u = up.user
        full_name = f"{u.first_name} {u.last_name}".strip() or u.username
        results.append({
            'id': up.id,
            'full_name': full_name,
            'email': u.email,
            'role': up.role or 'team_member',
            # tag so frontend knows this is a UserProfile, not a CompanyUser
            'user_type': 'profile',
        })

    return Response({'status': 'success', 'users': results[:limit]})


def _all_company_members(company_user):
    """Return every member of the company in the same shape as
    search_company_users, so hint-matching below and the "View all" panel
    speak the same participant format."""
    from core.models import CompanyUser, UserProfile
    out = []
    cu_qs = CompanyUser.objects.filter(
        company=company_user.company, is_active=True,
    ).values('id', 'full_name', 'email', 'role').order_by('full_name')[:500]
    for cu in cu_qs:
        out.append({
            'id': cu['id'],
            'full_name': cu['full_name'],
            'email': cu['email'],
            'role': cu['role'],
            'user_type': 'company_user',
        })
    seen_emails = {m['email'] for m in out}
    up_qs = UserProfile.objects.filter(
        company=company_user.company, user__is_active=True,
    ).select_related('user').exclude(user__email__in=seen_emails)[:500]
    for up in up_qs:
        u = up.user
        full_name = f"{u.first_name} {u.last_name}".strip() or u.username
        out.append({
            'id': up.id,
            'full_name': full_name,
            'email': u.email,
            'role': up.role or 'team_member',
            'user_type': 'profile',
        })
    return out


def _not_a_draft(parsed, thing):
    """Why "Create with AI" drafts nothing for this message, or None. It drafted anything it was given: "What's the
    weather?" became a meeting called Weather Inquiry, and "Show me everyone's salaries" a task (live run, 28 Oct)."""
    kind = str(parsed.get('kind') or thing).strip().lower()
    if kind == 'not_allowed':
        return ("Sorry, I can't help with that. I only draft " + ('meetings' if thing == 'meeting' else 'tasks')
                + " from what you describe, and I don't show other people's private records.")
    if kind != thing:
        if thing == 'meeting':
            return ('That does not ask for a meeting, so nothing was drafted. Say who it is with, when, for how '
                    'long and what about, for example "Board review with Usman next Tuesday at 11 for 45 minutes". '
                    'To change or cancel a meeting, open it in the list.')
        return ('That does not describe a task, so nothing was drafted. Say what has to be done, by whom and by '
                'when, for example "Ayesha to send the renewal notice by Friday, high priority".')
    return None


def _draft_warnings(members, hints):
    """Names the AI heard that are nobody in the company: they were dropped without a word."""
    missing = [str(h).strip() for h in (hints or []) if str(h).strip() and not _match_members_by_hints(members, [h])]
    return [f"No one called {', '.join(missing)} is in your company, so they were not added."] if missing else []


def _match_members_by_hints(members, hints):
    """Resolve free-text name/email hints (from the AI) to real member rows.

    Matching is intentionally strict to avoid false positives (e.g. the hint
    "usertwo" must NOT also pull in a member literally named "user"):
      - exact match on full_name or email, OR
      - the hint appears as a WHOLE WORD inside the member's name (so "noor"
        matches "Noor Fatima"), OR
      - the email's local part (before @) equals the hint.
    Plain substring containment is deliberately not used. A member is returned
    once; order follows the hints so named people appear first.
    """
    import re as _re
    matched = []
    matched_keys = set()
    for hint in (hints or []):
        h = str(hint or '').strip().lower()
        if not h:
            continue
        for m in members:
            key = f"{m.get('user_type', 'company_user')}-{m.get('id')}"
            if key in matched_keys:
                continue
            name = (m.get('full_name') or '').lower()
            email = (m.get('email') or '').lower()
            local = email.split('@', 1)[0] if email else ''
            name_words = set(_re.split(r'[\s._-]+', name)) if name else set()
            hit = (
                h == name
                or h == email
                or h == local
                or h in name_words          # whole-word match within the name
            )
            if hit:
                matched.append(m)
                matched_keys.add(key)
    return matched


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def meeting_ai_parse(request):
    """"Create with AI" for meetings: parse a free-form prompt into fields the
    Schedule-Meeting form can be pre-filled with, plus participants resolved
    from any names/emails mentioned in the prompt."""
    company_user = request.user
    prompt = (request.data.get('prompt') or '').strip()
    if not prompt:
        return Response({'status': 'error', 'message': 'prompt is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        agent = _get_agent('meeting_scheduling', company_user)
        parsed = agent.parse_meeting_request(prompt, company_user.id) or {}
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("meeting_ai_parse error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    refused = _not_a_draft(parsed, 'meeting')
    if refused:
        return Response({'status': 'error', 'message': refused}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    members = _all_company_members(company_user)
    participants = _match_members_by_hints(members, parsed.get('participant_hints'))
    warnings = _draft_warnings(members, parsed.get('participant_hints'))
    if parsed.get('time_problem'):
        warnings.append(f"Check the time: {str(parsed['time_problem'])[:120]}.")
    at = _parse_datetime(parsed.get('scheduled_at'))
    from meeting_agent.clock import typed_now
    if at and at < typed_now(company_user.company, _browser_zone(request)):
        warnings.append('That time has already passed: pick a time to come.')
    return Response({
        'status': 'success',
        'warnings': warnings,
        'data': {
            'title': parsed.get('title') or '',
            'description': parsed.get('description') or '',
            'scheduled_at': parsed.get('scheduled_at') or '',
            'duration_minutes': parsed.get('duration_minutes') or 60,
            'agenda': parsed.get('agenda') or [],
            'meeting_link': parsed.get('meeting_link') or '',
            'participants': participants,
        },
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def task_ai_parse(request):
    """"Create with AI" for tasks: parse a free-form prompt into fields the
    Add-Task form can be pre-filled with, plus assignees resolved from any
    names/emails mentioned in the prompt."""
    company_user = request.user
    prompt = (request.data.get('prompt') or '').strip()
    if not prompt:
        return Response({'status': 'error', 'message': 'prompt is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        agent = _get_agent('task_prioritization', company_user)
        parsed = agent.parse_task_request(prompt) or {}
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("task_ai_parse error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    refused = _not_a_draft(parsed, 'task')
    if refused:
        return Response({'status': 'error', 'message': refused}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    members = _all_company_members(company_user)
    assignees = _match_members_by_hints(members, parsed.get('assignee_hints'))
    return Response({
        'status': 'success',
        'warnings': _draft_warnings(members, parsed.get('assignee_hints')),
        'data': {
            'title': parsed.get('title') or '',
            'description': parsed.get('description') or '',
            'priority': parsed.get('priority') or 'medium',
            'due_date': parsed.get('due_date') or '',
            'assignees': assignees,
        },
    }, status=status.HTTP_200_OK)


@api_view(['GET', 'POST', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_participants(request, meeting_id):
    """List, add, or remove participants from a meeting."""
    from core.models import CompanyUser
    company_user = request.user
    meeting = get_object_or_404(ExecutiveMeeting, id=meeting_id, organizer=company_user)

    if request.method == 'GET':
        parts = list(meeting.participants.select_related('company_user').all())
        # Who each one is in the People window's terms: a login (its id) or an employee (their profile's id),
        # as `user_type` + `member_id`. The window compared bare ids, so picking an employee could remove a
        # login with the same number, and email them that they were removed (CO-163).
        from core.models import UserProfile
        seat_emails = [p.company_user.email.lower() for p in parts if not p.company_user.is_active and p.company_user.email]
        profiles = {pr.user.email.lower(): pr.id for pr in UserProfile.objects.select_related('user').filter(
            company=company_user.company, user__email__in=seat_emails)} if seat_emails else {}

        def member(cu):
            profile_id = None if cu.is_active else profiles.get((cu.email or '').lower())
            return ('profile', profile_id) if profile_id else ('company_user', cu.id)

        return Response({'status': 'success', 'participants': [
            {'id': p.id, 'user_id': p.company_user.id,
             'user_type': member(p.company_user)[0], 'member_id': member(p.company_user)[1],
             'full_name': p.company_user.full_name, 'email': p.company_user.email,
             'role': p.company_user.role, 'response': p.response}
            for p in parts
        ]})

    if request.method == 'POST':
        user_id = request.data.get('user_id')
        user_type = request.data.get('user_type', 'company_user')
        if not user_id:
            return Response({'status': 'error', 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        target = _participant_for(user_id, user_type, company_user.company)
        if target is None:
            return Response({'status': 'error', 'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        # They must be free then, in every agent: an invitation counts as busy time.
        people = _calendar_people([target])
        try:
            with booking_guard(people):
                if _occupies_people(meeting):
                    ensure_free(people, _real(company_user, meeting.scheduled_at, meeting.timezone_name),
                                meeting.duration_minutes,
                                tz_name=_company_zone(company_user, meeting.timezone_name),
                                exclude=[('exec', meeting.id)],
                                viewer_source='exec')
                p, created = ExecutiveMeetingParticipant.objects.get_or_create(meeting=meeting, company_user=target)
        except ScheduleConflict as clash:
            return clash.response()
        # Invited once, and only to a meeting that is on: picking someone already in it sent a second
        # invitation, and a cancelled or finished meeting still said "You're invited" (CO-257).
        if created and _occupies_people(meeting):
            _bell_invited([target], meeting, company_user.full_name)
            if target.email:
                _send_meeting_invite_email(target, meeting, company_user.full_name)
        return Response({'status': 'success', 'invited': bool(created and _occupies_people(meeting)), 'participant': {
            'id': p.id, 'user_id': target.id, 'full_name': target.full_name,
            'email': target.email, 'role': target.role, 'response': p.response,
        }}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    if request.method == 'DELETE':
        user_id = request.data.get('user_id')
        participant_id = request.data.get('participant_id')
        logger.info("Participant remove: meeting=%s user_id=%s participant_id=%s by=%s", meeting.id, user_id, participant_id, company_user.id)
        # Look up the participant record (prefer participant_id for reliability)
        removed_cu = None
        try:
            if participant_id:
                p_obj = ExecutiveMeetingParticipant.objects.select_related('company_user').get(id=participant_id, meeting=meeting)
                removed_cu = p_obj.company_user
            elif user_id:
                p_obj = ExecutiveMeetingParticipant.objects.select_related('company_user').get(meeting=meeting, company_user_id=user_id)
                removed_cu = p_obj.company_user
            if removed_cu:
                logger.info("Participant remove: found cu=%s email=%s", removed_cu.id, removed_cu.email)
        except ExecutiveMeetingParticipant.DoesNotExist:
            logger.warning("Participant remove: participant record not found (user_id=%s participant_id=%s)", user_id, participant_id)
        # Delete the record
        if participant_id:
            ExecutiveMeetingParticipant.objects.filter(id=participant_id, meeting=meeting).delete()
        elif user_id:
            ExecutiveMeetingParticipant.objects.filter(meeting=meeting, company_user_id=user_id).delete()
        # Send removal email
        if removed_cu and removed_cu.id != company_user.id:
            from meeting_agent.bell import ring
            ring([removed_cu], title=f'Taken off: {meeting.title}'[:255],
                 message=f'{company_user.full_name} took you off "{meeting.title}" ({clock_when_text(meeting)}).',
                 kind='exec_meeting_removed', email=False, data={'meeting_id': meeting.id})
            if removed_cu.email:
                _send_meeting_removal_email(removed_cu, meeting, company_user.full_name)
        elif removed_cu and removed_cu.id == company_user.id:
            logger.info("Participant remove: skipping email — user removed themselves")
        return Response({'status': 'success'})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_respond(request, meeting_id):
    """Accept, reject, or counter-propose a meeting invitation.

    Only for a meeting of the caller's own company, and only for someone who
    was invited. The meeting used to be found by its number alone and the
    caller added as a participant on the spot, so a login from another company
    could join anyone's meeting and write into the organiser's alerts.
    """
    company_user = request.user
    meeting = get_object_or_404(ExecutiveMeeting, id=meeting_id, organizer__company=company_user.company)
    response_val = request.data.get('response', '').strip()
    reason = request.data.get('reason', '')
    counter_time_str = request.data.get('counter_proposed_time', '')

    valid_responses = ['accepted', 'rejected', 'tentative', 'counter_proposed']
    if response_val not in valid_responses:
        return Response({'status': 'error', 'message': f'response must be one of {valid_responses}'}, status=status.HTTP_400_BAD_REQUEST)

    participant = ExecutiveMeetingParticipant.objects.filter(meeting=meeting, company_user=company_user).first()
    if participant is None:
        return Response({'status': 'error', 'message': 'You are not invited to this meeting.'},
                        status=status.HTTP_403_FORBIDDEN)
    counter = _parse_datetime(counter_time_str) if response_val == 'counter_proposed' and counter_time_str else None
    _record_answer(meeting, participant, response_val, reason, counter)
    return Response({'status': 'success', 'participant': {
        'response': participant.response,
        'responded_at': participant.responded_at.isoformat(),
    }})


# ---------------------------------------------------------------------------
# Answering an invitation (CO-211). A dashboard login answers in the agent (above); an employee, who takes part
# through a seat and cannot open the agent, answers on their own Meetings page or from the invitation email. An
# unanswered invitation is busy time on the shared calendar, so until now they could not free themselves.
# ---------------------------------------------------------------------------

EXEC_ANSWER_SALT = 'exec.meeting.email-answer.v1'
EXEC_ANSWER_MAX_AGE = 14 * 24 * 3600
_SAID = {'accepted': 'accepted', 'rejected': 'declined', 'tentative': 'tentatively accepted',
         'counter_proposed': 'suggested another time for'}


def _record_answer(meeting, participant, response_val, reason='', counter_time=None):
    """Save an invitee's answer and tell the organiser, on the agent's page and in the bell. Saving the seat
    re-syncs the shared calendar, so a decline frees the person's time."""
    who = participant.company_user.full_name or participant.company_user.email
    participant.response = response_val
    participant.reason = reason
    participant.responded_at = timezone.now()
    if counter_time:
        participant.counter_proposed_time = counter_time
    participant.save()
    said = _SAID[response_val]
    ExecNotification.objects.create(
        company_user=meeting.organizer,
        notification_type='participant_response',
        severity='info',
        title=f"{who} {said} your meeting"[:255],
        message=f"{who} {said} the meeting '{meeting.title}'." + (f" Reason: {reason}" if reason else ''),
        meeting=meeting,
        data={'participant_id': participant.company_user_id, 'response': response_val, 'meeting_id': meeting.id},
    )
    # And in the bell: the alert above shows only on Executive Meeting's own page.
    from core.notification_utils import notify_company_users
    notify_company_users(
        [meeting.organizer], title=f'{who} {said} {meeting.title}'[:255],
        message=f'{who} {said} the meeting "{meeting.title}".' + (f' Reason: {reason}' if reason else ''),
        link='/exec-meeting/dashboard?tab=meetings', kind='exec_meeting_reply',
        data={'meeting_id': meeting.id})
    return participant


def _not_answerable(meeting):
    """Why an invitation to this meeting can no longer be answered, or None."""
    from meeting_agent.clock import real_end
    if meeting.status == 'cancelled':
        return f'The meeting "{meeting.title}" was cancelled. There is nothing to answer.'
    if meeting.status == 'completed' or (real_end(meeting) and real_end(meeting) < timezone.now()):
        return f'The meeting "{meeting.title}" is over.'
    return None


def answer_link(participant, action):
    """The Accept or Decline button of an invitation email: a signed link for this seat, good for 14 days."""
    from django.core.signing import TimestampSigner
    from core.notification_settings import backend_url
    base = backend_url()
    token = TimestampSigner(salt=EXEC_ANSWER_SALT).sign(str(int(participant.id)))
    return f'{base}/api/meetings/exec-email-answer/{action}/{token}/'


def _answer_buttons(seat) -> str:
    """The invitation email's Accept and Decline buttons."""
    def button(label, href, colour):
        return (f'<td style="padding:0 6px;"><a href="{escape(href, quote=True)}" target="_blank" style="display:'
                f'inline-block;padding:11px 26px;background:{colour};border-radius:8px;color:#ffffff;font-size:14px;'
                f'font-weight:600;text-decoration:none;">{label}</a></td>')
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:20px 0 0;"><tr>'
        '<td align="center"><p style="margin:0 0 10px;color:#6b7280;font-size:13px;">Can you come?</p>'
        '<table cellpadding="0" cellspacing="0" border="0" style="margin:0 auto;"><tr>'
        + button('Accept', answer_link(seat, 'accepted'), '#059669')
        + button('Decline', answer_link(seat, 'rejected'), '#6b7280')
        + '</tr></table></td></tr></table>')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def meeting_respond_as_employee(request, meeting_id):
    """An employee accepts or declines an executive meeting from their Meetings page. Their seat is found the way
    the shared calendar finds them (linked by HR, or the same address in the same company). Accept and decline only:
    nothing on the organiser's side acts on a suggested time."""
    from api.views.notification import _dashboard_logins_of
    seat = (ExecutiveMeetingParticipant.objects.select_related('meeting__organizer__company', 'company_user')
            .filter(meeting_id=meeting_id, company_user_id__in=_dashboard_logins_of(request.user)).first())
    if seat is None:
        return Response({'status': 'error', 'message': 'You are not invited to this meeting.'},
                        status=status.HTTP_404_NOT_FOUND)
    action = str(request.data.get('action') or request.data.get('response') or '').strip()
    if action not in ('accepted', 'rejected'):
        return Response({'status': 'error', 'message': 'Answer with accept or decline.'},
                        status=status.HTTP_400_BAD_REQUEST)
    problem = _not_answerable(seat.meeting)
    if problem:
        return Response({'status': 'error', 'message': problem}, status=status.HTTP_400_BAD_REQUEST)
    if seat.response != action:           # the same answer again tells the organiser nothing new
        _record_answer(seat.meeting, seat, action, str(request.data.get('reason') or '').strip()[:1000])
    return Response({'status': 'success', 'response': seat.response})


def meeting_email_answer(request, action, token):
    """The Accept and Decline buttons of an invitation email. No login: the signed link is the proof, as for
    Project Manager's invitations (api/views/notification.meeting_email_action)."""
    from html import escape
    from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
    from api.views.notification import _render_email_action_page

    def page(heading, text, color='#10b981'):
        # The page puts its text into HTML as given; a meeting's title is the organiser's text.
        return _render_email_action_page(escape(heading), escape(text), color=color)
    try:
        seat_id = int(TimestampSigner(salt=EXEC_ANSWER_SALT).unsign(token, max_age=EXEC_ANSWER_MAX_AGE))
    except (BadSignature, SignatureExpired, ValueError):
        return page('Link expired or invalid', 'This invitation link is no longer valid. Ask the organiser to '
                    'invite you again, or answer on your Meetings page.', color='#ef4444')
    seat = (ExecutiveMeetingParticipant.objects.select_related('meeting__organizer__company', 'company_user')
            .filter(id=seat_id).first())
    if seat is None or action not in ('accepted', 'rejected'):
        return page('Invitation not found', 'You are no longer invited to this meeting, or it was deleted.',
                    color='#ef4444')
    problem = _not_answerable(seat.meeting)
    if problem:
        return page('Nothing to answer', problem, color='#9ca3af')
    title = seat.meeting.title
    if seat.response == action:
        return page(f'Already {_SAID[action]}', f'You have already {_SAID[action]} "{title}". Nothing more to do.')
    _record_answer(seat.meeting, seat, action)
    if action == 'accepted':
        return page('Accepted', f'You accepted "{title}". {seat.meeting.organizer.full_name or "The organiser"} '
                    'has been told.')
    return page('Declined', f'You declined "{title}". The organiser has been told, and the time is free in your '
                'calendar again.', color='#6b7280')


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def meeting_suggest_slots(request):
    """Suggest free time slots for a meeting."""
    company_user = request.user
    preferred_date = request.query_params.get('date', _today(company_user).isoformat())
    duration = int(request.query_params.get('duration_minutes', 60))
    num_slots = min(int(request.query_params.get('num_slots', 5)), 10)

    try:
        slots = _shared_free_slots(company_user, preferred_date, duration, num_slots)
        if slots is None:
            agent = _get_agent('meeting_scheduling', company_user)
            slots = agent.suggest_available_slots(company_user.id, preferred_date, duration, num_slots)
        return Response({'status': 'success', 'slots': slots, 'date': preferred_date})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("meeting_suggest_slots error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_check_conflicts(request):
    """What is in the way of a proposed time (no LLM, DB only).
    Body: { scheduled_at, duration_minutes, exclude_meeting_id?, participants? }.

    Asked before a meeting is made or moved. The answer covers the organiser,
    the people picked (``participants``, as ``[{user_id, user_type}]``) and,
    when a meeting is being moved, everyone already in it. A clash on the
    calendar every agent shares is marked ``blocking`` and the answer says
    ``blocking: true``: saving will be refused, so the screen must not offer to
    book over it. A clash only the agent's own check finds is a warning."""
    company_user = request.user
    scheduled_at = _parse_datetime(request.data.get('scheduled_at'))
    if not scheduled_at:
        return Response({'status': 'error', 'message': 'Valid scheduled_at is required.'}, status=status.HTTP_400_BAD_REQUEST)
    duration = int(request.data.get('duration_minutes') or 60)
    exclude_id = request.data.get('exclude_meeting_id') or None
    try:
        exclude_id = int(exclude_id) if exclude_id else None
    except (TypeError, ValueError):
        exclude_id = None
    try:
        agent = _get_agent('meeting_scheduling', company_user)
        conflicts = agent.check_conflicts(company_user.id, scheduled_at, duration, exclude_id)
        people = set(_calendar_people([company_user])) | _picked_people(company_user.company,
                                                                         request.data.get('participants'))
        moving = (ExecutiveMeeting.objects.filter(id=exclude_id, organizer=company_user).first()
                  if exclude_id else None)
        if moving is not None:
            people |= set(people_for('exec', moving))
        fallback = _browser_zone(request, moving)
        shared = _shared_clashes(sorted(people), scheduled_at, duration, company_user, exclude_id, fallback=fallback)
        free = (_free_times(sorted(people), scheduled_at, duration, company_user, exclude_id, fallback=fallback)
                if shared else [])
        return Response({'status': 'success', 'conflicts': _all_clashes(conflicts, shared),
                         'blocking': bool(shared), 'free_times': free})
    except Exception as e:
        logger.error("meeting_check_conflicts error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# MEETING NOTES
# ===========================================================================

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMWhenWritingThrottle, ExecCRUDWhenReadingThrottle])
def meeting_notes(request, meeting_id):
    """Get or submit notes/transcript for a meeting."""
    company_user = request.user
    meeting = get_object_or_404(ExecutiveMeeting, id=meeting_id, organizer=company_user)

    if request.method == 'GET':
        try:
            note = meeting.note
            action_items = list(meeting.action_items.values(
                'id', 'title', 'description', 'status', 'priority',
                'due_date', 'ai_extracted', 'assignee_id', 'owner_name',
            ))
            from core.models import CompanyUser
            names = dict(CompanyUser.objects.filter(
                id__in=[a['assignee_id'] for a in action_items if a['assignee_id']]).values_list('id', 'full_name'))
            for a in action_items:
                a['assignee_name'] = names.get(a['assignee_id'], '')
            # Titles of tasks already created from this meeting — lets the UI
            # keep showing "Task created" on matching action items across page
            # reloads, without storing any link on the action item itself.
            converted_titles = [
                (t or '').strip().lower()
                for t in meeting.linked_tasks.values_list('title', flat=True)
            ]
            return Response({'status': 'success', 'notes': {
                'id': note.id,
                'ai_summary': note.ai_summary,
                'key_decisions': note.key_decisions,
                'raw_transcript': note.raw_transcript,
                'action_items': action_items,
                'converted_titles': converted_titles,
            }})
        except MeetingNote.DoesNotExist:
            return Response({'status': 'success', 'notes': None})

    # POST — process transcript with AI
    transcript = request.data.get('transcript', '').strip()
    if not transcript:
        return Response({'status': 'error', 'message': 'transcript is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        agent = _get_agent('meeting_notetaker', company_user)
        participant_names = list(
            meeting.participants.select_related('company_user').values_list('company_user__full_name', flat=True)
        )
        from meeting_agent.clock import held_on
        meeting_day = held_on(meeting)
        result = agent.process_full_transcript(transcript, meeting.title, participant_names, held_on=meeting_day)

        # The AI's answer is cleaned first, and the note and its items are replaced together: the old items were
        # deleted before the answer was read, so an answer not in the expected shape failed the request with them
        # already gone (CO-258).
        # The LLM sometimes returns the string "null"/"none"/"tbd" (or a
        # non-ISO date) for due_date — none of which the date column accepts.
        # Keep only a clean YYYY-MM-DD value, otherwise store no date.
        def _clean_due(raw):
            if not raw:
                return None
            s = str(raw).strip()
            if s.lower() in ('null', 'none', 'n/a', 'tbd', ''):
                return None
            try:
                due = datetime.strptime(s[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return None
            # Nothing agreed in a meeting is due before it was held. A date like that is the
            # AI guessing a year (it gave 2023), and no date is better than a wrong one.
            return due if due >= meeting_day else None

        valid_priorities = ('low', 'medium', 'high', 'critical')

        # The AI names who does each item. That name was asked for and then dropped, so no item
        # had an owner, and a task made from one was given to nobody.
        def _owner_named(raw):
            name = ' '.join(str(raw or '').split())[:255]
            return '' if name.lower() in ('null', 'none', 'n/a', 'tbd', 'unassigned', 'unknown') else name

        raw_items = result.get('action_items') if isinstance(result, dict) else None
        decisions = result.get('key_decisions') if isinstance(result, dict) else None
        decisions = [' '.join(str(d).split())[:500] for d in (decisions if isinstance(decisions, list) else []) if d]
        new_items, kept_titles = [], set()
        for item_data in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(item_data, dict):
                continue
            title = ' '.join(str(item_data.get('title') or 'Action Item').split())[:255]
            if title.lower() in kept_titles:
                continue  # the same item twice in one answer
            kept_titles.add(title.lower())
            prio = str(item_data.get('priority', 'medium')).strip().lower()
            if prio not in valid_priorities:
                prio = 'medium'
            owner = _owner_named(item_data.get('assignee_hint'))
            new_items.append(MeetingActionItem(
                meeting=meeting,
                title=title,
                description=str(item_data.get('description', '') or ''),
                due_date=_clean_due(item_data.get('due_date')),
                priority=prio,
                ai_extracted=True,
                owner_name=owner,
                assignee=_member_named(company_user.company, owner),
            ))

        from django.db import transaction
        with transaction.atomic():
            note, _ = MeetingNote.objects.update_or_create(
                meeting=meeting,
                defaults={
                    'raw_transcript': transcript,
                    'ai_summary': str(result.get('summary', '') or ''),
                    'key_decisions': decisions,
                },
            )
            # Re-generating gives a fresh set of action items. Any tasks created from the old ones are standalone.
            meeting.action_items.all().delete()
            for item in new_items:
                item.save()
        created_items = [{'id': item.id, 'title': item.title} for item in new_items]

        # Notify the organizer that action items were extracted. Re-generating
        # a transcript replaces the old notification for THIS meeting instead of
        # stacking a new one each time (avoids spam). The meeting name is spelled
        # out as "the '<name>' meeting" so it's easy to tell which meeting.
        if created_items:
            ExecNotification.objects.filter(
                company_user_id=company_user.id,
                notification_type='action_items_added',
                meeting=meeting,
            ).delete()
            ExecNotification.objects.create(
                company_user_id=company_user.id,
                notification_type='action_items_added',
                severity='info',
                title=f"{len(created_items)} action item(s) from the “{meeting.title}” meeting",
                message=(
                    f"AI pulled {len(created_items)} action item(s) out of the notes for "
                    f"the “{meeting.title}” meeting: " + ', '.join(ci['title'] for ci in created_items[:5])
                    + ('…' if len(created_items) > 5 else '')
                ),
                meeting=meeting,
                data={'meeting_id': meeting.id, 'action_item_ids': [ci['id'] for ci in created_items]},
            )

        # Say how much was read: the screen said the meeting was summarised when a few minutes were (CO-164).
        read, total = result.get('chars_read', len(transcript)), result.get('chars_total', len(transcript))
        message = (f'Summary, {len(decisions)} decision(s) and {len(created_items)} action item(s) from the whole '
                   'meeting.' if read >= total else
                   f'The transcript is long: the first {read:,} of its {total:,} characters were read. Summary, '
                   f'{len(decisions)} decision(s) and {len(created_items)} action item(s) from that part.')
        return Response({'status': 'success', 'message': message, 'notes': {
            'ai_summary': note.ai_summary,
            'key_decisions': note.key_decisions,
            'action_items_created': len(created_items),
            'chars_read': read,
            'chars_total': total,
        }})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("meeting_notes POST error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_notes_delete(request, meeting_id):
    """Clear a meeting's AI notes — deletes the MeetingNote (summary + key
    decisions + transcript) and ALL its extracted action items, for a clean
    slate. Any tasks created from those action items are standalone, so deleting
    the action items doesn't affect them."""
    company_user = request.user
    meeting = get_object_or_404(ExecutiveMeeting, id=meeting_id, organizer=company_user)
    MeetingNote.objects.filter(meeting=meeting).delete()
    meeting.action_items.all().delete()
    return Response({'status': 'success', 'message': 'Meeting notes cleared.'})


# ===========================================================================
# ACTION ITEMS
# ===========================================================================

@api_view(['GET', 'PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def action_item_detail(request, item_id):
    """Update or view a meeting action item."""
    company_user = request.user
    item = get_object_or_404(MeetingActionItem, id=item_id, meeting__organizer=company_user)

    if request.method == 'GET':
        return Response({'status': 'success', 'action_item': {
            'id': item.id, 'title': item.title, 'description': item.description,
            'status': item.status, 'priority': item.priority,
            'due_date': item.due_date.isoformat() if item.due_date else None,
            'assignee_id': item.assignee_id, 'ai_extracted': item.ai_extracted,
        }})

    # Only this company's people, and only the states the item has: an assignee id was saved as sent, so an
    # action item could be given to a person in another company (CO-255).
    problem = _bad_choice(MeetingActionItem, request.data, 'status', 'priority')
    if problem:
        return Response({'status': 'error', 'message': problem}, status=status.HTTP_400_BAD_REQUEST)
    for field in ['title', 'description', 'status', 'priority']:
        if field in request.data:
            setattr(item, field, request.data[field])
    if 'due_date' in request.data:
        item.due_date = request.data['due_date'] or None
    if 'assignee_id' in request.data:
        from core.models import CompanyUser
        wanted = request.data['assignee_id'] or None
        if wanted and not CompanyUser.objects.filter(id=wanted, company=company_user.company).exists():
            return Response({'status': 'error', 'message': 'That person is not in your company.'},
                            status=status.HTTP_404_NOT_FOUND)
        item.assignee_id = wanted
    item.save()
    return Response({'status': 'success', 'message': 'Action item updated.'})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def action_item_convert_to_task(request, item_id):
    """Turn a meeting action item into a standalone ExecutiveTask.

    The new task copies the action item's title/description/priority/due date and
    is linked to the meeting only (for reference). It has NO ongoing link to the
    action item — the action item is left completely untouched (not marked done,
    no back-reference), so the two live independently. Body (optional):
    { parent_task_id } to create it as a subtask of an existing task."""
    company_user = request.user
    item = get_object_or_404(MeetingActionItem, id=item_id, meeting__organizer=company_user)

    parent_task_id = request.data.get('parent_task_id') or None
    if parent_task_id:
        parent = get_object_or_404(ExecutiveTask, id=parent_task_id, company_user=company_user)
        if parent.parent_task_id:
            return Response({'status': 'error', 'message': 'Subtasks cannot be nested more than one level deep.'}, status=status.HTTP_400_BAD_REQUEST)

    # Same title-uniqueness rule as manual task creation. If a matching task
    # already exists this action item was effectively already converted.
    if ExecutiveTask.objects.filter(company_user=company_user, title__iexact=(item.title or '').strip()).exists():
        return Response(
            {'status': 'error', 'message': f'A task titled “{item.title}” already exists.'},
            status=status.HTTP_409_CONFLICT,
        )

    task = ExecutiveTask.objects.create(
        company_user=company_user,
        title=item.title,
        description=item.description or '',
        priority=item.priority or 'medium',
        due_date=item.due_date or None,
        linked_meeting=item.meeting,
        parent_task_id=parent_task_id,
    )
    # The person the notes say does it gets the task, and is told, as anyone given a task is.
    # An employee owns it through their seat, which is never an active login: they were skipped, so the task made
    # from Usman's item was given to nobody (clean run, 29 Oct 2026).
    owner = item.assignee if item.assignee_id else None
    if owner and owner.company_id == company_user.company_id:
        task.assignees.set([owner])
        if owner.email and owner.id != company_user.id:
            _send_task_assignment_email(owner, task, company_user.full_name)
        _tell_assigned([owner], task, company_user)
    return Response({'status': 'success', 'task': _serialize_task(task), 'message': 'Action item converted to task.'}, status=status.HTTP_201_CREATED)


# ===========================================================================
# TASKS
# ===========================================================================

# A task assigned from here was listed, and could be opened, only by the person who made
# it. The assignee got an email telling them to log in, and then could not see it.
EXEC_TASKS_LINK = '/exec-meeting/dashboard?tab=tasks'


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def exec_stats(request):
    """The overview's figures, counted here. The screen counted the first page of each list, so Total Tasks,
    Overdue Tasks and Unread never went past twenty (CO-168). Upcoming is by when a meeting really starts."""
    from meeting_agent.clock import real_start
    company_user = request.user
    now, today = timezone.now(), _today(company_user)
    on = (ExecutiveMeeting.objects
          .filter(models.Q(organizer=company_user) | models.Q(participants__company_user=company_user))
          .filter(status='scheduled', scheduled_at__gte=now - timedelta(hours=15))
          .exclude(participants__company_user=company_user, participants__response='rejected')
          .distinct().select_related('organizer__company'))
    listed = _listed_tasks(company_user)
    return Response({'status': 'success', 'stats': {
        'upcoming_meetings': sum(1 for m in on if real_start(m) > now),
        'total_tasks': listed.count(),
        'overdue_tasks': _visible_tasks(company_user).filter(due_date__lt=today)
                         .exclude(status__in=['done']).count(),
        'pending_action_items': listed.exclude(status__in=['done']).count(),
        'unread_notifications': ExecNotification.objects.filter(company_user=company_user, is_read=False).count(),
    }})


def _visible_tasks(company_user):
    """Tasks this login made, and tasks given to it."""
    return ExecutiveTask.objects.filter(
        models.Q(company_user=company_user) | models.Q(assignees=company_user)).distinct()


def _listed_tasks(company_user):
    """The task list: top-level tasks this login made, and every task given to it, except
    a subtask whose parent it already sees (the subtask is listed under that parent)."""
    given = ExecutiveTask.objects.filter(assignees=company_user).exclude(company_user=company_user)
    parent_seen = models.Q(parent_task__company_user=company_user) | models.Q(parent_task__assignees=company_user)
    return ExecutiveTask.objects.filter(
        models.Q(company_user=company_user, parent_task__isnull=True)
        | models.Q(pk__in=given.filter(parent_task__isnull=True).values('pk'))
        | models.Q(pk__in=given.filter(parent_task__isnull=False).exclude(parent_seen).values('pk')))


#: What a person on a task hears about when it changes (CO-171).
TASK_TOLD_FIELDS = ('title', 'description', 'status', 'priority', 'due_date')
_TOLD_LABEL = {'title': 'the title', 'description': 'the description', 'status': 'the status',
               'priority': 'the priority', 'due_date': 'the due date'}


def _tell_task_changed(people, task, by, changed):
    """Tell the people on a task what changed, by email and in the bell."""
    if not changed or not people:
        return
    from meeting_agent.bell import ring
    due = f'{task.due_date:%d %b %Y}' if task.due_date else 'no date'
    now = {'status': task.get_status_display(), 'priority': task.get_priority_display(), 'due_date': due}
    what = '; '.join(f"{_TOLD_LABEL[f]}{' is now ' + now[f] if f in now else ''}" for f in changed)
    ring(people, title=f'{by.full_name} changed a task: {task.title}'[:255],
         message=f'{by.full_name} changed "{task.title}": {what}.', kind='exec_task_changed',
         link='/exec-meeting/dashboard?tab=tasks', employee_link='/me/tasks', email=False,
         data={'task_id': task.id})
    rows = ''.join(_email_detail_row(_TOLD_LABEL[f].capitalize(), escape(now.get(f) or str(getattr(task, f) or '-')))
                   for f in changed)
    for cu in people:
        if not cu.email:
            continue
        first = escape((cu.full_name or 'there').split()[0])
        content = (f'<p style="margin:0 0 12px;color:#111827;font-size:16px;">Hi {first}, {escape(by.full_name or "")} '
                   f'changed a task you are on: <strong>{escape(task.title)}</strong>.</p>'
                   f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{rows}</table>')
        html = _email_base_html(content, preview_text=escape(f'"{task.title}" was changed.'))
        _email_login(cu, 'tasks_assigned', f'Task changed: {task.title}', html)


def _day_text(value):
    """A date as people write it (29 Oct 2026). A task just made still holds the date as sent ('2026-10-29')."""
    try:
        return f'{value:%d %b %Y}'
    except (TypeError, ValueError):
        try:
            return f"{datetime.strptime(str(value)[:10], '%Y-%m-%d'):%d %b %Y}"
        except ValueError:
            return str(value)


def _tell_assigned(people, task, given_by):
    """The bell of each person newly given the task, an employee's in My Space (meeting_agent.bell): the login-only
    bell skipped employees, so they never saw a task given to them. The email is sent separately."""
    from meeting_agent.bell import ring
    due = f' It is due on {_day_text(task.due_date)}.' if task.due_date else ''
    ring([cu for cu in people if cu.id != task.company_user_id],
         title=f'New task: {task.title}'[:255],
         message=f'{given_by.full_name or given_by.email} gave you a task in Executive Meeting.{due}',
         kind='exec_task_assigned', link=EXEC_TASKS_LINK, employee_link='/me/tasks', email=False,
         data={'exec_task_id': task.id})


def _tell_owner_of_progress(task, by):
    """The person who gave the task hears when its assignee moves it on."""
    from core.notification_utils import notify_company_users
    notify_company_users(
        [task.company_user],
        title=f'{by.full_name or by.email}: {task.title} is now {task.get_status_display()}'[:255],
        message=f'{by.full_name or by.email} changed the status of a task you gave them.',
        link=EXEC_TASKS_LINK, kind='exec_task_progress', email=False,
        data={'exec_task_id': task.id})


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def task_list(request):
    """List tasks or create one."""
    company_user = request.user

    if request.method == 'GET':
        status_filter = request.query_params.get('status')
        priority_filter = request.query_params.get('priority')
        search = (request.query_params.get('search') or '').strip()
        date_filter = (request.query_params.get('date') or '').strip()
        # Top-level list only — subtasks ride along nested under their parent
        # (via _serialize_task's 'subtasks' key) instead of appearing twice.
        qs = _listed_tasks(company_user)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        if search:
            qs = qs.filter(models.Q(title__icontains=search) | models.Q(description__icontains=search))
        if date_filter:
            # due_date is stored as a DateField (or ISO string) — match the day.
            qs = qs.filter(due_date=date_filter)
        page_items, meta = _paginate(qs, request)
        data = [_serialize_task(t, viewer=company_user) for t in page_items]
        return Response({'status': 'success', 'tasks': data, 'count': len(data), 'pagination': meta})

    title = request.data.get('title', '').strip()
    if not title:
        return Response({'status': 'error', 'message': 'title is required.'}, status=status.HTTP_400_BAD_REQUEST)

    # No two tasks for the same user may share a title (top-level and subtasks
    # both counted) — keeps the list unambiguous and makes meeting action-item
    # "Task created" matching reliable.
    if ExecutiveTask.objects.filter(company_user=company_user, title__iexact=title).exists():
        return Response(
            {'status': 'error', 'message': f'A task titled “{title}” already exists.'},
            status=status.HTTP_409_CONFLICT,
        )

    # Weekend deadlines are allowed — any date may be picked for a task.
    due_date = request.data.get('due_date') or None
    parent_task_id = request.data.get('parent_task_id') or None
    parent = None
    if parent_task_id:
        # Subtasks nest one level only — a subtask can't itself have a parent
        # that is already a subtask.
        parent = get_object_or_404(ExecutiveTask, id=parent_task_id, company_user=company_user)
        if parent.parent_task_id:
            return Response({'status': 'error', 'message': 'Subtasks cannot be nested more than one level deep.'}, status=status.HTTP_400_BAD_REQUEST)
        # A subtask normally must finish on or before its parent. The client can
        # opt out (checkbox) by sending allow_after_parent=true.
        allow_after_parent = bool(request.data.get('allow_after_parent', False))
        if not allow_after_parent and due_date and parent.due_date:
            try:
                sub_dt = datetime.strptime(str(due_date), '%Y-%m-%d').date()
                if sub_dt > parent.due_date:
                    return Response({
                        'status': 'error',
                        'message': f"Subtask due date can't be after the parent task's due date ({parent.due_date}).",
                    }, status=status.HTTP_400_BAD_REQUEST)
            except (ValueError, TypeError):
                pass

    # A linked meeting of this company only, and states the task has (CO-255).
    problem = _bad_choice(ExecutiveTask, request.data, 'status', 'priority')
    linked = request.data.get('linked_meeting_id') or None
    if linked and not ExecutiveMeeting.objects.filter(id=linked, organizer__company=company_user.company).exists():
        problem = "That meeting is not one of your company's."
    if problem:
        return Response({'status': 'error', 'message': problem}, status=status.HTTP_400_BAD_REQUEST)
    task = ExecutiveTask.objects.create(
        company_user=company_user,
        title=title,
        description=request.data.get('description', ''),
        status=request.data.get('status', 'todo'),
        priority=request.data.get('priority', 'medium'),
        due_date=due_date,
        linked_meeting_id=linked,
        parent_task_id=parent_task_id,
    )
    # assignees — list of {id, user_type} dicts
    assignee_list = request.data.get('assignees', [])
    resolved = _resolve_assignees(assignee_list, company_user.company)
    if resolved:
        task.assignees.set(resolved)
        for cu in resolved:
            if cu.email:
                _send_task_assignment_email(cu, task, company_user.full_name)
        _tell_assigned(resolved, task, company_user)

    # For a subtask, also notify the PARENT task's assignees that a subtask was
    # added under their task (so they see it appear on their work item). Skip
    # anyone who's already on the subtask itself — they just got the assignment
    # email above — and skip the creator.
    if parent is not None:
        sub_assignee_ids = {cu.id for cu in resolved}
        for pcu in parent.assignees.all():
            if pcu.email and pcu.id not in sub_assignee_ids and pcu.id != company_user.id:
                _send_subtask_added_email(pcu, parent, task, company_user.full_name)

    return Response({'status': 'success', 'task': _serialize_task(task)}, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def task_detail(request, task_id):
    """Get, update, or delete a task."""
    company_user = request.user
    task = get_object_or_404(_visible_tasks(company_user), id=task_id)

    if request.method == 'GET':
        return Response({'status': 'success', 'task': _serialize_task(task, viewer=company_user)})

    if task.company_user_id != company_user.id:
        # Given by someone else: its assignee may move the status on, and that is all.
        changes = set(request.data.keys()) if request.method == 'PATCH' else {'delete'}
        if not changes or not changes <= {'status'}:
            return Response({'status': 'error',
                             'message': 'Only the person who made this task can change or delete it. '
                                        'You can change its status.'}, status=status.HTTP_403_FORBIDDEN)
        new_status = request.data.get('status')
        if new_status not in dict(ExecutiveTask.STATUS_CHOICES):
            return Response({'status': 'error', 'message': 'Unknown status.'}, status=status.HTTP_400_BAD_REQUEST)
        if new_status != task.status:
            task.status = new_status
            task.save(update_fields=['status', 'updated_at'])
            _tell_owner_of_progress(task, company_user)
        return Response({'status': 'success', 'task': _serialize_task(task, viewer=company_user)})

    if request.method == 'PATCH':
        # Renaming to an existing title is a duplicate too — block it.
        if 'title' in request.data:
            new_title = (request.data.get('title') or '').strip()
            if not new_title:
                return Response({'status': 'error', 'message': 'title is required.'}, status=status.HTTP_400_BAD_REQUEST)
            if ExecutiveTask.objects.filter(
                company_user=company_user, title__iexact=new_title,
            ).exclude(id=task.id).exists():
                return Response(
                    {'status': 'error', 'message': f'A task titled “{new_title}” already exists.'},
                    status=status.HTTP_409_CONFLICT,
                )
        problem = _bad_choice(ExecutiveTask, request.data, 'status', 'priority')
        if problem:
            return Response({'status': 'error', 'message': problem}, status=status.HTTP_400_BAD_REQUEST)
        before = {f: str(getattr(task, f) or '') for f in TASK_TOLD_FIELDS}
        already_on = [cu for cu in task.assignees.all() if cu.id != company_user.id]
        # Weekend deadlines are allowed — any date may be set for a task.
        for field in ['title', 'description', 'status', 'priority', 'due_date', 'ai_reasoning']:
            if field in request.data:
                setattr(task, field, request.data[field] or None if field == 'due_date' else request.data[field])
        if 'estimated_hours' in request.data:
            task.estimated_hours = request.data['estimated_hours'] or None
        task.save()
        if 'assignees' in request.data:
            resolved = _resolve_assignees(request.data['assignees'], company_user.company)
            existing_qs = list(task.assignees.all())
            existing_ids = {cu.id for cu in existing_qs}
            new_ids = {cu.id for cu in resolved}
            task.assignees.set(resolved)
            # Email newly added assignees
            for cu in resolved:
                if cu.id not in existing_ids and cu.email:
                    _send_task_assignment_email(cu, task, company_user.full_name)
            _tell_assigned([cu for cu in resolved if cu.id not in existing_ids], task, company_user)
            # Email removed assignees
            for cu in existing_qs:
                if cu.id not in new_ids and cu.email:
                    _send_task_removal_email(cu, task, company_user.full_name)
        # The people already on it hear what changed: they were told only when added or removed, though the
        # product says they are emailed whenever it changes (CO-171).
        task.refresh_from_db()
        changed = [f for f in TASK_TOLD_FIELDS if str(getattr(task, f) or '') != before[f]]
        still_on = {cu.id for cu in task.assignees.all()}
        _tell_task_changed([cu for cu in already_on if cu.id in still_on], task, company_user, changed)
        return Response({'status': 'success', 'task': _serialize_task(task, viewer=company_user)})

    # Snapshot before delete so we can reference after
    task_title = task.title
    task_priority = task.priority
    # The people on its subtasks too: they go with it (CO-171).
    people = {cu.id: cu for t in [task, *task.subtasks.all()] for cu in t.assignees.all()}
    assignees_to_notify = [cu for cu in people.values() if cu.email and cu.id != company_user.id]
    task.delete()
    for cu in assignees_to_notify:
        _send_task_deleted_email(cu, task_title, task_priority, company_user.full_name)
    return Response({'status': 'success', 'message': 'Task deleted.'})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def generate_task_description(request):
    """AI-expand a task title (and optional rough points) into a full description.

    Only the title is required — the agent can draft a description from the
    task name alone. Any ``points`` the user typed are passed through as extra
    context but are optional, so "Generate with AI" works on a fresh task with
    an empty description box.
    """
    company_user = request.user
    title = (request.data.get('title') or '').strip()
    points = (request.data.get('points') or '').strip()

    if not title:
        return Response({'status': 'error', 'message': 'title is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        agent = _get_agent('task_prioritization', company_user)
        data = agent.generate_description(title, points)
        return Response({'status': 'success', 'data': data}, status=status.HTTP_200_OK)
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("generate_task_description error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def task_prioritize_ai(request):
    """AI-prioritize a set of tasks."""
    company_user = request.user
    task_ids = request.data.get('task_ids', [])
    context = request.data.get('context', '')

    tasks_qs = ExecutiveTask.objects.filter(company_user=company_user)
    if task_ids:
        tasks_qs = tasks_qs.filter(id__in=task_ids)

    tasks_data = [_serialize_task(t) for t in tasks_qs[:30]]
    if not tasks_data:
        return Response({'status': 'error', 'message': 'No tasks found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        agent = _get_agent('task_prioritization', company_user)
        result = [_clean_priority_suggestion(item, _today(company_user))
                  for item in agent.prioritize_tasks(tasks_data, context)]
        # `apply: false` only suggests: the Tasks screen shows the suggestions and applies the ones ticked
        # (task_prioritize_apply). Without it the suggestions are applied at once, as before.
        updated = _apply_priority_suggestions(company_user, result) if request.data.get('apply', True) else 0
        return Response({'status': 'success', 'prioritized': result, 'updated_count': updated})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("task_prioritize_ai error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def task_prioritize_apply(request):
    """Apply the AI suggestions the user ticked: {'items': [{id, priority, ai_reasoning, suggested_due_date}]}."""
    items = request.data.get('items')
    if not isinstance(items, list) or not items:
        return Response({'status': 'error', 'message': 'items must be a non-empty list.'},
                        status=status.HTTP_400_BAD_REQUEST)
    items = [_clean_priority_suggestion(dict(item), _today(request.user)) for item in items if isinstance(item, dict)]
    return Response({'status': 'success', 'updated_count': _apply_priority_suggestions(request.user, items)})


def _clean_priority_suggestion(item, today=None):
    """One AI suggestion made safe to show and to save. Priority is clamped to low/medium/high (a stray 'critical'
    becomes 'high'), and a suggested date before today is pulled up to today. Weekends are allowed."""
    p = str(item.get('priority', '')).strip().lower()
    if p == 'critical':
        p = 'high'
    item['priority'] = p if p in ('low', 'medium', 'high') else 'medium'
    due = None
    raw = item.get('suggested_due_date')
    if raw:
        try:
            due = max(datetime.strptime(str(raw)[:10], '%Y-%m-%d').date(), today or timezone.now().date())
        except (ValueError, TypeError):
            due = None
    item['suggested_due_date'] = due.isoformat() if due else None
    return item


def _apply_priority_suggestions(company_user, items):
    """Save cleaned suggestions onto the user's own tasks, in one read and one write. A suggested date only fills a
    task that has none. Returns how many tasks changed."""
    by_id = ExecutiveTask.objects.filter(company_user=company_user).in_bulk(
        [item['id'] for item in items if str(item.get('id', '')).isdigit()])
    changed = []
    for item in items:
        task = by_id.get(int(item['id'])) if str(item.get('id', '')).isdigit() else None
        if task is None:
            continue
        task.priority = item['priority']
        if item.get('ai_reasoning'):
            task.ai_reasoning = item['ai_reasoning']
        if item['suggested_due_date'] and not task.due_date:
            task.due_date = item['suggested_due_date']
        changed.append(task)
    ExecutiveTask.objects.bulk_update(changed, ['priority', 'ai_reasoning', 'due_date'])
    return len(changed)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def task_workload_analysis(request):
    """Analyze workload for the current user."""
    company_user = request.user
    tasks_data = [_serialize_task(t) for t in ExecutiveTask.objects.filter(company_user=company_user)[:50]]
    try:
        agent = _get_agent('task_prioritization', company_user)
        analysis = agent.analyze_workload(tasks_data, company_user.full_name)
        return Response({'status': 'success', 'analysis': analysis})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("task_workload_analysis error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# CALENDAR
# ===========================================================================

def _shared_free_slots(company_user, date_str, duration, limit):
    """Free times that day from the calendar every agent shares, as {start, end} in the agent's terms (wall-clock
    on the company's clock), or None for a login with no employee calendar. The agent's own answers looked at
    executive meetings only, and offered hours already past (CO-276)."""
    from meeting_agent.clock import company_zone
    from core.scheduling import free_slots
    people = _calendar_people([company_user])
    if not people:
        return None
    try:
        day = datetime.strptime(str(date_str)[:10], '%Y-%m-%d').date()
    except ValueError:
        day = _today(company_user)
    zone = company_zone(company_user.company)
    starts = free_slots(people, day, duration, tz_name=zone, limit=max(1, int(limit)))
    from zoneinfo import ZoneInfo
    wall = [start.astimezone(ZoneInfo(zone)).replace(tzinfo=None) for start in starts]
    return [{'start': w.isoformat(timespec='seconds'),
             'end': (w + timedelta(minutes=int(duration))).isoformat(timespec='seconds')} for w in wall]


def _busy_elsewhere(company_user, week_start, listed_ids):
    """The person's busy time this week outside the agent's own meetings: other agents' meetings, interviews,
    sales calls, leave, company holidays (the calendar every agent shares). The plan read executive meetings
    only, and put tasks over all of them (CO-276). As blocked stretches the planner works round, in the
    agent's own terms: wall-clock time on the company's clock, cut into days and to working hours."""
    from datetime import time as _time
    from zoneinfo import ZoneInfo
    from core.scheduling import busy_intervals
    from meeting_agent.clock import company_zone
    people = _calendar_people([company_user])
    if not people:
        return []
    zone = company_zone(company_user.company)
    tz = ZoneInfo(zone)
    start = datetime.combine(week_start, _time(0), tzinfo=tz)
    end = start + timedelta(days=7)
    try:
        intervals = busy_intervals(people, start, end, exclude=[('exec', i) for i in listed_ids if i], tz_name=zone)
    except Exception as exc:
        logger.warning('calendar_plan_week: shared calendar unreadable: %s', exc)
        return []
    blocks = []
    for s_at, e_at in intervals:
        s_at, e_at = max(s_at, start).astimezone(tz), min(e_at, end).astimezone(tz)
        day = s_at.date()
        while day <= e_at.date():
            piece_start = max(s_at, datetime.combine(day, _time(0), tzinfo=tz))
            piece_end = min(e_at, datetime.combine(day, _time(0), tzinfo=tz) + timedelta(days=1))
            minutes = int((piece_end - piece_start).total_seconds() // 60)
            if minutes > 0:
                blocks.append({'id': None, 'title': 'Busy elsewhere', 'status': 'busy',
                               'scheduled_at': piece_start.replace(tzinfo=None).isoformat(timespec='seconds'),
                               'duration_minutes': minutes})
            day += timedelta(days=1)
    return blocks


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def calendar_plan_week(request):
    """Generate an AI weekly calendar plan."""
    company_user = request.user
    week_start = request.data.get('week_start', _today(company_user).isoformat())
    include_past_tasks = bool(request.data.get('include_past_tasks', False))
    # Work-hours window the user wants tasks scheduled within (defaults 9–17).
    try:
        work_start_hour = int(request.data.get('work_start_hour', 9))
        work_end_hour = int(request.data.get('work_end_hour', 17))
    except (ValueError, TypeError):
        work_start_hour, work_end_hour = 9, 17
    work_start_hour = max(0, min(23, work_start_hour))
    work_end_hour = max(work_start_hour + 1, min(24, work_end_hour))

    from datetime import date as _date, timedelta as _td
    try:
        _week_start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
    except ValueError:
        _week_start_date = _today(company_user)
    _week_end_date = _week_start_date + _td(days=6)

    meetings = []
    for m in ExecutiveMeeting.objects.filter(
        organizer=company_user,
        status__in=['scheduled', 'in_progress'],
    ):
        # Convert to local date using the meeting's stored datetime
        local_date = timezone.localtime(m.scheduled_at).date() if timezone.is_aware(m.scheduled_at) else m.scheduled_at.date()
        if _week_start_date <= local_date <= _week_end_date:
            meetings.append({
                'id': m.id, 'title': m.title,
                'scheduled_at': local_date.isoformat() + 'T' + timezone.localtime(m.scheduled_at).strftime('%H:%M:%S'),
                'duration_minutes': m.duration_minutes,
                'status': m.status,
            })

    # Top-level tasks only — subtasks are pulled in via the nested-flatten loop
    # below (as "Parent → subtask"). Without this filter a subtask would also
    # match here and show up a second time as a standalone item.
    tasks_qs = ExecutiveTask.objects.filter(
        company_user=company_user, status__in=['todo', 'in_progress'],
        parent_task__isnull=True,
    )
    if include_past_tasks:
        # Past + this week only — never show future (next week+) tasks
        tasks_qs = tasks_qs.filter(
            models.Q(due_date__isnull=True) |
            models.Q(due_date__lte=_week_end_date)
        )
    else:
        # Only tasks due within this week or with no due date
        tasks_qs = tasks_qs.filter(
            models.Q(due_date__isnull=True) |
            models.Q(due_date__gte=_week_start_date, due_date__lte=_week_end_date)
        )
    # Flatten for the planner: each task AND each of its subtasks becomes its own
    # schedulable line item, so subtasks show up in the weekly plan too (not just
    # buried inside their parent). Subtasks are prefixed with the parent title.
    # A subtask belongs in this week based on ITS OWN due date, independent of
    # when the parent is due (parent could be next week while a subtask is due
    # this week, or vice-versa).
    def _subtask_in_window(st):
        if st.get('status') in ('done', 'completed', 'cancelled'):
            return False
        st_due = (st.get('due_date') or '')[:10]
        if not st_due:
            return True  # undated subtask rides along with its parent
        if include_past_tasks:
            return st_due <= _week_end_date.isoformat()
        return _week_start_date.isoformat() <= st_due <= _week_end_date.isoformat()

    tasks = []
    seen_subtask_ids = set()
    for t in tasks_qs[:200]:          # it cut at 30 without saying so (CO-166)
        s = _serialize_task(t)
        subtasks = s.pop('subtasks', []) or []
        tasks.append(s)
        for st in subtasks:
            if not _subtask_in_window(st):
                continue
            seen_subtask_ids.add(st.get('id'))
            st = {**st, 'title': f"{t.title} → {st.get('title')}", 'is_subtask': True}
            tasks.append(st)

    # Catch subtasks whose OWN due date is in this week but whose parent isn't
    # (so the parent wasn't in tasks_qs and the loop above never saw them).
    orphan_subs = ExecutiveTask.objects.filter(
        company_user=company_user, status__in=['todo', 'in_progress'],
        parent_task__isnull=False,
    ).exclude(parent_task__in=tasks_qs).select_related('parent_task')
    if include_past_tasks:
        orphan_subs = orphan_subs.filter(due_date__isnull=False, due_date__lte=_week_end_date)
    else:
        orphan_subs = orphan_subs.filter(due_date__gte=_week_start_date, due_date__lte=_week_end_date)
    for st in orphan_subs[:200]:
        if st.id in seen_subtask_ids:
            continue
        s = _serialize_task(st, include_subtasks=False)
        parent_title = st.parent_task.title if st.parent_task else ''
        s['title'] = (f"{parent_title} → " if parent_title else '') + s['title']
        s['is_subtask'] = True
        tasks.append(s)

    logger.info("calendar_plan_week: user=%s week_start=%s meetings=%d tasks=%d include_past=%s",
                company_user.id, week_start, len(meetings), len(tasks), include_past_tasks)

    # Also include meetings where user is a participant (not just organizer)
    participant_meeting_ids = set(m['id'] for m in meetings)
    from meeting_agent.models import ExecutiveMeetingParticipant as _EMP
    for p in _EMP.objects.select_related('meeting').filter(
        company_user=company_user,
        meeting__status__in=['scheduled', 'in_progress'],
    ).exclude(response='rejected'):      # a declined invitation takes no time (CO-276)
        m = p.meeting
        if m.id not in participant_meeting_ids:
            local_date = timezone.localtime(m.scheduled_at).date() if timezone.is_aware(m.scheduled_at) else m.scheduled_at.date()
            if _week_start_date <= local_date <= _week_end_date:
                meetings.append({
                    'id': m.id, 'title': m.title,
                    'scheduled_at': local_date.isoformat() + 'T' + timezone.localtime(m.scheduled_at).strftime('%H:%M:%S'),
                    'duration_minutes': m.duration_minutes,
                    'status': m.status,
                })
                participant_meeting_ids.add(m.id)

    meetings += _busy_elsewhere(company_user, _week_start_date, [m['id'] for m in meetings])
    logger.info("calendar_plan_week: after participant merge meetings=%d", len(meetings))

    try:
        agent = _get_agent('calendar_planner', company_user)
        plan = agent.plan_week(meetings, tasks, week_start, work_start_hour, work_end_hour)
        logger.info("calendar_plan_week: plan keys=%s daily_plans=%s",
                    list(plan.keys()) if plan else None,
                    len(plan.get('daily_plans', [])) if plan else 0)
        return Response({'status': 'success', 'plan': plan})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("calendar_plan_week error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def calendar_free_slots(request):
    """Get free calendar slots for a given date."""
    company_user = request.user
    date = request.query_params.get('date', _today(company_user).isoformat())
    duration = int(request.query_params.get('duration_minutes', 60))

    try:
        slots = _shared_free_slots(company_user, date, duration, 12)
        if slots is None:
            agent = _get_agent('calendar_planner', company_user)
            slots = agent.get_free_slots(company_user.id, date, duration)
        return Response({'status': 'success', 'slots': slots, 'date': date})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("calendar_free_slots error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# DOCUMENTS
# ===========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def document_draft(request):
    """AI-draft a meeting document (agenda, minutes, briefing, report)."""
    company_user = request.user
    doc_type = request.data.get('doc_type', 'agenda')
    meeting_id = request.data.get('meeting_id')
    save = request.data.get('save', False)

    valid_doc_types = ['agenda', 'minutes', 'briefing']
    if doc_type not in valid_doc_types:
        return Response({'status': 'error', 'message': f'doc_type must be one of {valid_doc_types}'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        agent = _get_agent('document_authoring', company_user)
        meeting = None
        if meeting_id:
            try:
                meeting = ExecutiveMeeting.objects.get(id=meeting_id, organizer=company_user)
            except ExecutiveMeeting.DoesNotExist:
                pass

        if doc_type == 'agenda':
            topics = request.data.get('topics', [])
            attendees = request.data.get('attendees', [])
            if meeting and not topics:
                topics = meeting.agenda or []
            if meeting and not attendees:
                attendees = list(meeting.participants.values_list('company_user__full_name', flat=True))
            scheduled_at_str = request.data.get('scheduled_at', '')
            if not scheduled_at_str and meeting and meeting.scheduled_at:
                local_dt = timezone.localtime(meeting.scheduled_at)
                scheduled_at_str = local_dt.strftime('%Y-%m-%d %H:%M')
            content = agent.draft_agenda(
                meeting.title if meeting else request.data.get('title', 'Meeting'),
                meeting.duration_minutes if meeting else int(request.data.get('duration_minutes', 60)),
                topics, attendees, request.data.get('context', ''),
                scheduled_at=scheduled_at_str,
            )

        elif doc_type == 'minutes':
            summary = request.data.get('summary', '').strip()
            user_provided_summary = bool(summary)
            if meeting and not summary:
                try:
                    summary = meeting.note.ai_summary or ''
                except Exception:
                    summary = ''
            action_items = list(request.data.get('action_items') or [])
            decisions = list(request.data.get('decisions') or [])
            # A linked meeting's own decisions and action items always go in, with who owns each. With a summary
            # typed (the screen fills the box with the notes) they were re-extracted from that text, which the screen
            # cut at 800 characters, and most were lost (CO-167).
            if meeting:
                have = {str(i.get('title', '')).strip().lower() for i in action_items if isinstance(i, dict)}
                action_items += [
                    {'title': a.title, 'assignee_hint': (a.assignee.full_name if a.assignee else a.owner_name) or None,
                     'due_date': str(a.due_date) if a.due_date else None}
                    for a in meeting.action_items.select_related('assignee')[:50] if a.title.strip().lower() not in have]
                try:
                    stored = meeting.note.key_decisions or []
                except Exception:
                    stored = []
                said = {' '.join(str(d).split()).lower() for d in decisions}
                decisions += [d for d in stored if ' '.join(str(d).split()).lower() not in said]
            # If user provided a summary but no decisions/action_items, extract them via AI
            if user_provided_summary and not decisions and not action_items:
                extracted = agent.extract_decisions_and_actions(summary)
                decisions = extracted.get('decisions', [])
                action_items = extracted.get('action_items', [])
            attendees_minutes = request.data.get('attendees', [])
            if meeting and not attendees_minutes:
                attendees_minutes = list(meeting.participants.values_list('company_user__full_name', flat=True))
            content = agent.write_minutes(
                meeting.title if meeting else request.data.get('title', 'Meeting'),
                # The day it was held, not the day the minutes were written (CO-167).
                request.data.get('date') or f"{(held_on(meeting) if meeting else _today(request.user)):%d %b %Y}",
                attendees_minutes,
                summary, action_items, decisions,
            )

        elif doc_type == 'briefing':
            briefing_topic = (
                request.data.get('topic') or
                request.data.get('title') or
                (meeting.title if meeting else 'Executive Briefing')
            )
            # A briefing for a chosen meeting is about that meeting. Given only a topic, it came back as a blank
            # template ("[DD MMM YYYY]", "[Name / Department]") whatever meeting was chosen (live run, 28 Oct).
            context = str(request.data.get('context', '') or '')
            if meeting and not context.strip():
                context = _meeting_context(meeting, company_user)
            content = agent.create_briefing(
                briefing_topic,
                context,
                request.data.get('key_points'),
                request.data.get('audience', 'Executive Team') or 'Executive Team',
            )

        result = {'status': 'success', 'doc_type': doc_type, 'content': content}

        # Always auto-save as standalone document
        from meeting_agent.models import ExecStandaloneDocument
        doc_title = request.data.get('title', '') or (meeting.title if meeting else 'Untitled')
        standalone = ExecStandaloneDocument.objects.create(
            company_user=company_user,
            doc_type=doc_type,
            title=f"{doc_type.capitalize()} — {doc_title}",
            content=content,
            ai_generated=True,
            # No linked meeting → this is a fill-in template, not built from
            # real meeting data.
            is_template=(meeting is None),
        )
        result['document_id'] = standalone.id
        result['is_template'] = standalone.is_template

        if save and meeting:
            MeetingDocument.objects.create(
                meeting=meeting,
                created_by=company_user,
                doc_type=doc_type,
                title=doc_title,
                content=content,
                ai_generated=True,
            )

        return Response(result)
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("document_draft error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_documents(request, meeting_id):
    """List documents for a meeting."""
    company_user = request.user
    meeting = get_object_or_404(ExecutiveMeeting, id=meeting_id, organizer=company_user)
    docs = meeting.documents.filter(created_by=company_user)
    return Response({'status': 'success', 'documents': [
        {'id': d.id, 'doc_type': d.doc_type, 'title': d.title, 'ai_generated': d.ai_generated,
         'content': d.content, 'created_at': d.created_at.isoformat()}
        for d in docs
    ]})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def standalone_document_list(request):
    """List all AI-generated standalone documents for the company user."""
    from meeting_agent.models import ExecStandaloneDocument
    company_user = request.user
    doc_type = request.query_params.get('doc_type')
    search = (request.query_params.get('search') or '').strip()
    date_filter = (request.query_params.get('date') or '').strip()
    qs = ExecStandaloneDocument.objects.filter(company_user=company_user)
    if doc_type:
        qs = qs.filter(doc_type=doc_type)
    if search:
        qs = qs.filter(models.Q(title__icontains=search) | models.Q(content__icontains=search))
    if date_filter:
        # Documents created on a given calendar day (YYYY-MM-DD).
        try:
            day = datetime.strptime(date_filter, '%Y-%m-%d').date()
            qs = qs.filter(created_at__date=day)
        except (ValueError, TypeError):
            pass
    page_items, meta = _paginate(qs, request)
    docs = [
        {
            'id': d.id, 'doc_type': d.doc_type, 'title': d.title,
            'content': d.content, 'ai_generated': d.ai_generated,
            'is_template': d.is_template,
            'created_at': d.created_at.isoformat(),
        }
        for d in page_items
    ]
    return Response({'status': 'success', 'documents': docs, 'count': len(docs), 'pagination': meta})


@api_view(['GET', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def standalone_document_detail(request, doc_id):
    """Get or delete a standalone document."""
    from meeting_agent.models import ExecStandaloneDocument
    company_user = request.user
    doc = get_object_or_404(ExecStandaloneDocument, id=doc_id, company_user=company_user)
    if request.method == 'DELETE':
        doc.delete()
        return Response({'status': 'success', 'message': 'Document deleted.'})
    return Response({
        'status': 'success',
        'document': {
            'id': doc.id, 'doc_type': doc.doc_type, 'title': doc.title,
            'content': doc.content, 'ai_generated': doc.ai_generated,
            'is_template': doc.is_template,
            'created_at': doc.created_at.isoformat(),
        },
    })


# ===========================================================================
# NOTIFICATIONS
# ===========================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def notification_list(request):
    """List notifications for the current user."""
    company_user = request.user
    unread_only = request.query_params.get('unread', 'false').lower() == 'true'
    severity = request.query_params.get('severity')
    category = (request.query_params.get('category') or '').strip().lower()
    search = (request.query_params.get('search') or '').strip()

    # Group notification types into two high-level buckets the UI filters on.
    # Action-item notifications are surfaced from a meeting's notes, so they
    # belong under "meeting" even though they mention tasks.
    MEETING_TYPES = [
        'meeting_reminder', 'meeting_invite', 'meeting_update',
        'meeting_cancelled', 'participant_response', 'calendar_conflict',
        'action_items_added', 'action_item_due', 'action_item_overdue',
    ]
    TASK_TYPES = [
        'task_due', 'task_overdue',
    ]

    qs = ExecNotification.objects.filter(company_user=company_user)
    if unread_only:
        qs = qs.filter(is_read=False)
    if severity:
        qs = qs.filter(severity=severity)
    if category == 'meeting':
        qs = qs.filter(notification_type__in=MEETING_TYPES)
    elif category == 'task':
        qs = qs.filter(notification_type__in=TASK_TYPES)
    if search:
        qs = qs.filter(models.Q(title__icontains=search) | models.Q(message__icontains=search))

    page_items, meta = _paginate(qs, request)
    notifications = [_serialize_notification(n) for n in page_items]
    unread_count = ExecNotification.objects.filter(company_user=company_user, is_read=False).count()
    return Response({'status': 'success', 'notifications': notifications, 'unread_count': unread_count, 'pagination': meta})


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def notification_mark_read(request, notification_id):
    """Mark a notification as read."""
    company_user = request.user
    notif = get_object_or_404(ExecNotification, id=notification_id, company_user=company_user)
    notif.is_read = True
    notif.save(update_fields=['is_read'])
    return Response({'status': 'success', 'message': 'Notification marked as read.'})


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def notification_mark_all_read(request):
    """Mark all notifications as read."""
    company_user = request.user
    ExecNotification.objects.filter(company_user=company_user, is_read=False).update(is_read=True)
    return Response({'status': 'success', 'message': 'All notifications marked as read.'})


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def notification_delete(request, notification_id):
    """Delete a single notification."""
    company_user = request.user
    notif = get_object_or_404(ExecNotification, id=notification_id, company_user=company_user)
    notif.delete()
    return Response({'status': 'success', 'message': 'Notification deleted.'})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def notification_bulk_delete(request):
    """Delete multiple notifications by id. Body: { ids: [1, 2, ...] }."""
    company_user = request.user
    ids = request.data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return Response({'status': 'error', 'message': 'ids (non-empty list) is required.'}, status=status.HTTP_400_BAD_REQUEST)
    deleted, _ = ExecNotification.objects.filter(company_user=company_user, id__in=ids).delete()
    return Response({'status': 'success', 'message': f'{deleted} notification(s) deleted.', 'deleted': deleted})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecDigestThrottle])
def notification_daily_digest(request):
    """Today's AI digest: the one already made today, or a new one when {"refresh": true}."""
    company_user = request.user
    key = _digest_key(company_user)
    if not _wants_new_digest(request):
        kept = cache.get(key)
        if kept is not None:
            return Response({'status': 'success', 'digest': kept})
    try:
        agent = _get_agent('proactive_notification', company_user)
        digest = agent.generate_daily_digest(company_user.id, company_user.full_name)
        digest['made_at'] = timezone.now().isoformat()
        cache.set(key, digest, DIGEST_KEEP_SECONDS)
        return Response({'status': 'success', 'digest': digest})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("notification_daily_digest error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# CHAT — generic endpoint for any sub-agent
# ===========================================================================

_CHAT_MODEL_MAP = {
    'meeting_scheduling': (ExecMeetingSchedulingChat, ExecMeetingSchedulingChatMessage),
    'meeting_notetaker': (ExecNotetakerChat, ExecNotetakerChatMessage),
    'task_prioritization': (ExecTaskChat, ExecTaskChatMessage),
    'calendar_planner': (ExecCalendarChat, ExecCalendarChatMessage),
    'document_authoring': (ExecDocumentChat, ExecDocumentChatMessage),
    'proactive_notification': (ExecNotificationChat, ExecNotificationChatMessage),
}

_CHAT_SYSTEM_PROMPTS = {
    'meeting_scheduling': "You are the Meeting Scheduling Agent for the AI Executive Meeting Assistant. Help the user schedule, reschedule, and manage executive meetings.",
    'meeting_notetaker': "You are the Meeting Notetaker Agent. Help the user capture, summarize, and follow up on meeting notes and action items.",
    'task_prioritization': "You are the Task & Prioritization Agent. Help the user manage, prioritize, and track executive tasks.",
    'calendar_planner': "You are the Calendar Auto-planner Agent. Help the user optimize their calendar and schedule.",
    'document_authoring': "You are the Document Authoring Agent. Help the user draft agendas, minutes, briefings, and reports.",
    'proactive_notification': "You are the Proactive Notification Agent. Help the user stay on top of their meetings, tasks, and deadlines.",
}


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def chat_list(request, agent_name):
    """List chats or create a new chat for a sub-agent."""
    if agent_name not in _CHAT_MODEL_MAP:
        return Response({'status': 'error', 'message': f'Unknown agent: {agent_name}'}, status=status.HTTP_404_NOT_FOUND)

    company_user = request.user
    ChatModel, _ = _CHAT_MODEL_MAP[agent_name]

    if request.method == 'GET':
        chats = ChatModel.objects.filter(company_user=company_user)[:20]
        return Response({'status': 'success', 'chats': [
            {'id': c.id, 'title': c.title, 'created_at': c.created_at.isoformat(), 'updated_at': c.updated_at.isoformat()}
            for c in chats
        ]})

    chat = ChatModel.objects.create(
        company_user=company_user,
        title=request.data.get('title', 'Chat'),
    )
    return Response({'status': 'success', 'chat': {'id': chat.id, 'title': chat.title}}, status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def chat_messages(request, agent_name, chat_id):
    """Get messages or send a message in a sub-agent chat."""
    if agent_name not in _CHAT_MODEL_MAP:
        return Response({'status': 'error', 'message': f'Unknown agent: {agent_name}'}, status=status.HTTP_404_NOT_FOUND)

    company_user = request.user
    ChatModel, MessageModel = _CHAT_MODEL_MAP[agent_name]

    chat = get_object_or_404(ChatModel, id=chat_id, company_user=company_user)

    if request.method == 'GET':
        messages = chat.messages.all()[:100]
        return Response({'status': 'success', 'messages': [
            {'id': m.id, 'role': m.role, 'content': m.content,
             'response_data': m.response_data, 'created_at': m.created_at.isoformat()}
            for m in messages
        ]})

    user_message = request.data.get('message', '').strip()
    if not user_message:
        return Response({'status': 'error', 'message': 'message is required.'}, status=status.HTTP_400_BAD_REQUEST)

    # Save user message
    MessageModel.objects.create(chat=chat, role='user', content=user_message)

    # Build history context for LLM
    history = chat.messages.order_by('-created_at')[:8]
    history_text = '\n'.join([
        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
        for m in reversed(list(history))
        if m.content != user_message
    ])

    try:
        agent = _get_agent(agent_name, company_user)
        system_prompt = _CHAT_SYSTEM_PROMPTS.get(agent_name, '')
        prompt = f"{history_text}\nUser: {user_message}" if history_text else user_message
        ai_response = agent._call_llm(prompt, system_prompt, temperature=0.5, max_tokens=800)

        msg = MessageModel.objects.create(
            chat=chat, role='assistant', content=ai_response,
            response_data={'agent': agent_name},
        )
        chat.title = user_message[:60] if chat.title == 'Chat' else chat.title
        chat.save(update_fields=['title', 'updated_at'])

        return Response({'status': 'success', 'message': {
            'id': msg.id, 'role': 'assistant', 'content': ai_response,
            'created_at': msg.created_at.isoformat(),
        }})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("chat_messages POST error (agent=%s): %s", agent_name, e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# ADMIN ENDPOINTS
# ===========================================================================

from rest_framework.permissions import IsAuthenticated
from api.permissions import IsAdmin as IsAdminUser

# These four are for the platform's own staff, who sign in with the default
# (employee/staff) token like every other /api/admin/ page. They used to sign the
# caller in as a dashboard login and then look up the staff account with the same
# id number, which is a different person.


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
@throttle_classes([ExecCRUDThrottle])
def admin_meeting_list(request):
    """Admin: list all meetings across all companies."""
    company_id = request.query_params.get('company_id')
    status_filter = request.query_params.get('status')
    qs = ExecutiveMeeting.objects.select_related('organizer', 'organizer__company').all()
    if company_id:
        qs = qs.filter(organizer__company_id=company_id)
    if status_filter:
        qs = qs.filter(status=status_filter)
    data = []
    for m in qs[:100]:
        s = _serialize_meeting(m)
        s['company_id'] = m.organizer.company_id
        s['company_name'] = getattr(m.organizer.company, 'name', '') if hasattr(m.organizer, 'company') else ''
        data.append(s)
    return Response({'status': 'success', 'meetings': data, 'count': len(data)})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
@throttle_classes([ExecCRUDThrottle])
def admin_task_list(request):
    """Admin: list all executive tasks across all companies."""
    company_id = request.query_params.get('company_id')
    priority_filter = request.query_params.get('priority')
    status_filter = request.query_params.get('status')
    qs = ExecutiveTask.objects.select_related('company_user', 'company_user__company').all()
    if company_id:
        qs = qs.filter(company_user__company_id=company_id)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)
    data = []
    for t in qs[:100]:
        s = _serialize_task(t)
        s['company_user_name'] = t.company_user.full_name
        s['company_id'] = t.company_user.company_id
        data.append(s)
    return Response({'status': 'success', 'tasks': data, 'count': len(data)})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
@throttle_classes([ExecCRUDThrottle])
def admin_notification_list(request):
    """Admin: list all notifications across all companies."""
    company_id = request.query_params.get('company_id')
    severity_filter = request.query_params.get('severity')
    qs = ExecNotification.objects.select_related('company_user').all()
    if company_id:
        qs = qs.filter(company_user__company_id=company_id)
    if severity_filter:
        qs = qs.filter(severity=severity_filter)
    data = []
    for n in qs[:100]:
        s = _serialize_notification(n)
        s['company_user_name'] = n.company_user.full_name
        s['company_id'] = n.company_user.company_id
        data.append(s)
    return Response({'status': 'success', 'notifications': data, 'count': len(data)})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
@throttle_classes([ExecCRUDThrottle])
def admin_stats(request):
    """Admin: aggregate stats for the AI Executive Meeting Assistant."""
    from django.db.models import Count
    company_id = request.query_params.get('company_id')

    meeting_qs = ExecutiveMeeting.objects.all()
    task_qs = ExecutiveTask.objects.all()
    notif_qs = ExecNotification.objects.all()

    if company_id:
        meeting_qs = meeting_qs.filter(organizer__company_id=company_id)
        task_qs = task_qs.filter(company_user__company_id=company_id)
        notif_qs = notif_qs.filter(company_user__company_id=company_id)

    return Response({'status': 'success', 'stats': {
        'meetings': {
            'total': meeting_qs.count(),
            'by_status': dict(meeting_qs.values_list('status').annotate(c=Count('id')).values_list('status', 'c')),
        },
        'tasks': {
            'total': task_qs.count(),
            'by_priority': dict(task_qs.values_list('priority').annotate(c=Count('id')).values_list('priority', 'c')),
            'by_status': dict(task_qs.values_list('status').annotate(c=Count('id')).values_list('status', 'c')),
        },
        'notifications': {
            'total': notif_qs.count(),
            'unread': notif_qs.filter(is_read=False).count(),
            'by_severity': dict(notif_qs.values_list('severity').annotate(c=Count('id')).values_list('severity', 'c')),
        },
    }})
