"""Executive Meeting's alerts, in the bell everyone looks at.

The agent wrote its reminders and its due and overdue alerts only to its own Notifications tab (ExecNotification),
which nobody opens to look, and which an employee cannot open at all: an employee takes part through a seat, an
inactive login. Invitations reached nobody's bell. (The demo plan's "Ready?" column, 28 Oct 2026: "its alerts stay
inside the agent".)

Each alert now also reaches the bell: a dashboard login's, under the topic its kind belongs to
(core.notification_settings, where each person chooses bell, email or both), or, for a seat, the employee's own
bell in My Space.
"""
import logging

logger = logging.getLogger(__name__)

AGENT_LINK = '/exec-meeting/dashboard'
EMPLOYEE_MEETINGS = '/me/meetings'
EMPLOYEE_TASKS = '/me/tasks'


def ring(people, *, title, message, kind, link=AGENT_LINK, employee_link=EMPLOYEE_MEETINGS, severity='info',
         data=None, email=True):
    """Tell these CompanyUser rows: logins in their bell, seats as the employee behind them.

    `email=False` when the caller sends its own email (an invitation). Never raises."""
    from django.contrib.auth import get_user_model
    from core.notification_utils import notify_company_users, notify_employees
    from core.scheduling import login_user_id_for_company_user
    try:
        logins, employee_ids = [], set()
        for person in people:
            if person is None:
                continue
            if person.is_active:
                logins.append(person)
            else:
                user_id = login_user_id_for_company_user(person)
                if user_id:
                    employee_ids.add(user_id)
        if logins:
            notify_company_users(logins, title=title, message=message, link=link, severity=severity, kind=kind,
                                 email=email, data=data)
        if employee_ids:
            notify_employees(get_user_model().objects.filter(id__in=employee_ids), title=title, message=message,
                             link=employee_link, kind=kind)
    except Exception as exc:                # an alert must not break what raised it
        logger.warning('Executive Meeting bell (%s) failed: %s', kind, exc)


def task_people(task):
    """Whoever a task concerns: its owner and the people it is assigned to."""
    return [task.company_user, *task.assignees.all()]
