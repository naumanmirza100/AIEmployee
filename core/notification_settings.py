"""What each dashboard login wants to hear about, in the bell and by email.

Every agent used to decide this on its own: Frontline had per-event email
switches (one of which nothing read), Project Manager had outbound channels,
and the alerts that reach the shared bell (`core.notification_utils`) checked
nothing at all — nor could anyone turn off a meeting-reply email, a recruiter's
booking email or Frontline's weekly summary. Now there is one list of topics,
one settings page (`company/notification-settings`), and every alert and email
to a dashboard login asks here first.

Defaults keep what each topic did before this existed: a topic that already
emailed still does, and a bell-only alert doesn't start emailing until its
owner turns that on. A topic whose bell row is also its "already sent" record
(PM meeting reminders) can't be hidden from the bell, only stop emailing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: The `topic` of the row that pauses every email for a login.
ALL = 'all'
SETTINGS_PATH = '/company/settings/notifications'


@dataclass(frozen=True)
class Topic:
    key: str
    label: str
    description: str
    #: The module whose purchase makes it relevant; None for everyone. A tuple
    #: of modules for a topic several agents share: any one of them is enough.
    agent: str | tuple | None
    #: `kind` values passed to `notify_company_users` that belong here.
    kinds: tuple = ()
    email_default: bool = False
    #: Whether it has a bell alert at all, and whether that can be turned off.
    in_app: bool = True
    in_app_locked: bool = False
    #: Whether it can email.
    email: bool = True


AGENT_LABELS = {
    'project_manager_agent': 'Project Manager',
    'hr_agent': 'HR',
    'frontline_agent': 'Frontline',
    'recruitment_agent': 'Recruitment',
    'exec_meeting_agent': 'Executive Meeting',
    'marketing_agent': 'Marketing',
    'operations_agent': 'Operations',
    None: 'Everyone',
}
#: The heading for topics that several agents share.
SHARED = 'shared'
SHARED_LABEL = 'Meetings and tasks'

TOPICS = (
    # Shared by several agents. These emails go to a person's work address, which
    # may or may not be a dashboard login: `address_wants_email` asks the login
    # with that address in the company, and sends when there is none.
    Topic('meeting_reminders', 'Meeting reminders',
          'Before a meeting in Project Manager, HR or Frontline that you organise or are in, and when '
          "invitees to yours haven't replied. Project Manager's are always in the bell; the bell is how "
          'a reminder is sent only once.',
          ('project_manager_agent', 'hr_agent', 'frontline_agent'), kinds=('hr_meeting_reminder', 'frontline_meeting_reminder'),
          email_default=True, in_app_locked=True),
    Topic('tasks_assigned', 'Tasks assigned to you',
          'Someone gives you a task in Project Manager or from an executive meeting, adds to one of '
          'yours, or takes one away.',
          ('project_manager_agent', 'exec_meeting_agent'), email_default=True, in_app=False),
    Topic('tasks_overdue', 'Your tasks that become overdue',
          'The morning after one of your Project Manager tasks was due, if it is still open.',
          'project_manager_agent', kinds=('pm_task_overdue',)),
    Topic('meeting_replies', 'Replies to meetings you organise',
          'An invitee accepts, declines or suggests another time, in Project Manager, HR or Executive Meeting.',
          ('project_manager_agent', 'hr_agent', 'exec_meeting_agent'),
          kinds=('pm_meeting_reply', 'hr_meeting_reply', 'exec_meeting_reply'),
          email_default=True),
    Topic('leave_requests', 'Leave requests waiting for a decision',
          "Someone you approve leave for, or anyone's if you run HR, asks for time off.",
          'hr_agent', kinds=('hr_leave_request',)),
    Topic('leave_decisions', 'Answers to your own leave requests',
          'Your leave is approved or declined, or someone else cancels or withdraws it.',
          'hr_agent', kinds=('hr_leave_decided',), email_default=True),
    Topic('leave_clashes', 'Someone in a meeting you run goes on leave',
          'Leave is approved for a person who is booked into a meeting or interview you organise.',
          'hr_agent', kinds=('hr_leave_clash',)),
    Topic('workflow_approvals', 'HR workflows waiting for approval',
          'An HR workflow stops until someone approves it.', 'hr_agent', kinds=('hr_workflow_approval',)),
    Topic('workflow_failures', 'HR workflows that fail or skip a step',
          'An HR workflow stops on an error, or finishes without one of its steps.', 'hr_agent',
          kinds=('hr_workflow_failed',)),
    Topic('new_hires', 'New hires from Recruitment',
          'Recruitment hands a hired candidate over to HR, or changes its mind about one.', 'hr_agent',
          kinds=('hr_new_starter', 'hr_hire_withdrawn')),
    Topic('handoffs', 'A customer asks for a person',
          'A customer in the chat widget wants to talk to someone.', 'frontline_agent',
          kinds=('frontline_handoff',)),
    Topic('tickets_assigned', 'Tickets assigned to you',
          'Someone gives you a ticket, or a hand-off is assigned to you.', 'frontline_agent',
          kinds=('frontline_ticket_assigned',)),
    Topic('tickets_near_deadline', 'A ticket is about to miss its response time',
          'A ticket assigned to you (or one nobody has, if you take hand-offs) is within an hour of its response time.',
          'frontline_agent', kinds=('frontline_ticket_near_deadline',)),
    Topic('ticket_task_done', "A ticket's project task is done",
          'The Project Manager task made from your ticket is finished.', 'frontline_agent',
          kinds=('frontline_ticket_task_done',)),
    Topic('ticket_created', 'Automation emails: ticket created',
          "Frontline's notification templates that send when a ticket is created.",
          'frontline_agent', email_default=True, in_app=False),
    Topic('ticket_updated', 'Automation emails: ticket updated',
          "Frontline's notification templates that send when a ticket changes.",
          'frontline_agent', email_default=True, in_app=False),
    Topic('automation_emails', 'Other automation emails',
          'Frontline workflow emails, scheduled and send-now templates.',
          'frontline_agent', email_default=True, in_app=False),
    Topic('weekly_digest', 'Weekly Frontline summary',
          "A weekly email with the last 7 days' tickets: created, resolved and past their SLA.",
          'frontline_agent', email_default=True, in_app=False),
    Topic('new_applications', 'New job applications',
          'Someone applies for a job you own through its public page.', 'recruitment_agent',
          kinds=('recruitment_new_application',)),
    Topic('interviews_booked', 'A candidate books an interview',
          'A candidate picks a time for an interview you run.', 'recruitment_agent',
          kinds=('recruitment_interview_booked',), email_default=True),
    Topic('pipeline_digest', 'Daily recruitment reminders',
          'Once a day: candidates on hold for over 3 days, online interviews in the next 24 hours with no meeting '
          'link, and interviews done with no outcome recorded.', 'recruitment_agent',
          kinds=('recruitment_pipeline_digest',)),
    Topic('exec_meetings', 'Executive meeting invitations and changes',
          'You are invited to an executive meeting, its time or details change, or you are taken off it.',
          'exec_meeting_agent', email_default=True, in_app=False),
    Topic('exec_tasks', 'Executive Meeting tasks',
          'Someone gives you a task in Executive Meeting, or moves on a task you gave them. '
          'The email for a new task is under "Tasks assigned to you".',
          'exec_meeting_agent', kinds=('exec_task_assigned', 'exec_task_progress'), email=False),
    Topic('marketing_action', 'Marketing campaigns that need you',
          "A campaign of yours cannot go on without you: it could not start, its mailbox stopped "
          "sending, or something else needs a decision. At most once a day for each.",
          'marketing_agent', kinds=('marketing_action_required',)),
    Topic('operations_failed', 'Documents that could not be read',
          'A document you uploaded to Operations failed to process.',
          'operations_agent', kinds=('operations_document_failed',)),
    Topic('handover', 'Work handed over to you',
          "HR gives you a leaver's tasks, projects, meetings, people, leave or interviews.", None,
          kinds=('handover_',)),
    Topic('account', 'Billing, plans and API keys',
          'Payments, token quotas and API key changes. Always in the bell.', None,
          kinds=('key_request_rejected',), in_app_locked=True, email=False),
)
BY_KEY = {t.key: t for t in TOPICS}
#: Frontline's automation emails — what its unsubscribe link turns off.
FRONTLINE_AUTOMATION = ('ticket_created', 'ticket_updated', 'automation_emails')


def topic_for_kind(kind):
    """The topic a `notify_company_users` kind belongs to, or None (then it is
    always in the bell and never emailed — as before topics existed)."""
    if not kind:
        return None
    for topic in TOPICS:
        for k in topic.kinds:
            if kind == k or (k.endswith('_') and kind.startswith(k)):
                return topic
    return None


def _stored(company_user_ids):
    from core.models import NotificationSetting
    found = {}
    for row in NotificationSetting.objects.filter(company_user_id__in=list(company_user_ids)):
        found.setdefault(row.company_user_id, {})[row.topic] = row
    return found


def _effective(topic, rows):
    """(in_app, email) for one topic, from a login's stored rows."""
    row = rows.get(topic.key)
    in_app = topic.in_app and (topic.in_app_locked or (row.in_app if row else True))
    email = topic.email and (row.email if row else topic.email_default)
    paused = rows.get(ALL)
    if paused is not None and not paused.email:
        email = False
    return in_app, email


def choices(company_users, topic_key):
    """{company_user id: (in_app, email)} for one topic, in one query."""
    topic = BY_KEY[topic_key]
    company_users = [cu for cu in company_users if cu]
    stored = _stored(cu.id for cu in company_users)
    return {cu.id: _effective(topic, stored.get(cu.id, {})) for cu in company_users}


def wants_email(company_user, topic_key) -> bool:
    if company_user is None or not getattr(company_user, 'email', ''):
        return False
    return choices([company_user], topic_key)[company_user.id][1]


def address_wants_email(company_id, address, topic_key) -> bool:
    """Should an email about this topic go to this address?

    For emails addressed to a person's work address and not to a dashboard login:
    task assignments, HR and Frontline meeting reminders. If the address is a
    dashboard login of this company, that login's settings decide, 'Pause all
    emails' included. Any other address (an employee with no dashboard login, a
    customer) has no settings and is sent to, as before.

    Only ever asked within one company: the same address can be a login in two,
    and one of them pausing must not silence the other.
    """
    address = (address or '').strip()
    if not address:
        return False
    if not company_id:
        return True
    try:
        from core.models import CompanyUser
        login = CompanyUser.objects.filter(company_id=company_id, email__iexact=address).first()
        return True if login is None else wants_email(login, topic_key)
    except Exception:
        logger.warning('Could not read the notification settings for an address; sending', exc_info=True)
        return True


def wants_in_app(company_user, topic_key) -> bool:
    if company_user is None:
        return False
    return choices([company_user], topic_key)[company_user.id][0]


def wanting_email(company_users, topic_key):
    """The logins among these who want this topic by email."""
    chosen = choices(company_users, topic_key)
    return [cu for cu in company_users if cu and cu.email and chosen.get(cu.id, (False, False))[1]]


def set_choice(company_user, topic_key, *, in_app=None, email=None):
    from core.models import NotificationSetting
    if topic_key == ALL:
        NotificationSetting.objects.update_or_create(company_user=company_user, topic=ALL,
                                                     defaults={'email': bool(email), 'in_app': True})
        return
    topic = BY_KEY[topic_key]
    current_in_app, current_email = _effective(topic, {
        k: v for k, v in _stored([company_user.id]).get(company_user.id, {}).items() if k != ALL})
    NotificationSetting.objects.update_or_create(company_user=company_user, topic=topic_key, defaults={
        'in_app': current_in_app if in_app is None or topic.in_app_locked else bool(in_app),
        'email': current_email if email is None or not topic.email else bool(email),
    })


def email_paused(company_user) -> bool:
    row = _stored([company_user.id]).get(company_user.id, {}).get(ALL)
    return row is not None and not row.email


def page(company_user) -> dict:
    """The settings page: the topics this company uses, with this login's choices."""
    from core.models import CompanyModulePurchase
    owned = {p.module_name for p in CompanyModulePurchase.objects.filter(company_id=company_user.company_id)
             if p.is_active()}
    stored = _stored([company_user.id]).get(company_user.id, {})
    unpaused = {k: v for k, v in stored.items() if k != ALL}
    topics = []
    for topic in TOPICS:
        several = isinstance(topic.agent, tuple)
        if topic.agent is not None and not owned.intersection(topic.agent if several else (topic.agent,)):
            continue
        in_app, email = _effective(topic, unpaused)
        topics.append({
            'key': topic.key, 'label': topic.label, 'description': topic.description,
            'agent': SHARED if several else (topic.agent or 'everyone'),
            'agent_label': SHARED_LABEL if several else AGENT_LABELS[topic.agent],
            'in_app': in_app, 'email': email,
            'offers_in_app': topic.in_app, 'in_app_locked': topic.in_app_locked, 'offers_email': topic.email,
        })
    return {'email_paused': email_paused(company_user), 'email_address': company_user.email, 'topics': topics}


# ---- the email ----------------------------------------------------------------

def frontend_url(path=''):
    from django.conf import settings
    base = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    return f'{base}{path}' if base and path else base


def send_email(company_user, topic_key, *, title, message, link=None):
    """Email one alert to one login, after the current transaction commits —
    through the worker when there is one."""
    from django.db import transaction

    def queue():
        try:
            from core.tasks import send_notification_email
            send_notification_email.delay(company_user.id, topic_key, str(title), str(message), link)
        except Exception:
            logger.warning('Could not queue a notification email; sending it now', exc_info=True)
            deliver(company_user.id, topic_key, title, message, link)

    transaction.on_commit(queue)


def deliver(company_user_id, topic_key, title, message, link=None):
    """Send it (the worker's half). Re-checks the setting: it may have changed."""
    from django.conf import settings
    from django.core.mail import send_mail
    from django.utils.html import escape
    from core.models import CompanyUser

    cu = CompanyUser.objects.filter(pk=company_user_id, is_active=True).first()
    if cu is None or not wants_email(cu, topic_key):
        return False
    topic = BY_KEY[topic_key]
    open_url = frontend_url(link) if link else ''
    settings_url = frontend_url(SETTINGS_PATH)
    why = f'You get this because email for "{topic.label}" is on in your notification settings.'
    text = '\n\n'.join(p for p in (
        message, f'Open: {open_url}' if open_url else '',
        f'—\n{why}' + (f'\nChange it: {settings_url}' if settings_url else '')) if p)
    html = (f'<p>{escape(message)}</p>'
            + (f'<p><a href="{escape(open_url)}">Open it</a></p>' if open_url else '')
            + f'<p style="color:#888;font-size:12px">{escape(why)}'
            + (f' <a href="{escape(settings_url)}">Change it</a>' if settings_url else '') + '</p>')
    send_mail(subject=str(title)[:200], message=text, html_message=html,
              from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
              recipient_list=[cu.email], fail_silently=True)
    return True
