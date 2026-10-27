"""Tell people about their tasks that have just become overdue (CO-62, found 5 Oct 2026, done 28 Oct).

An overdue task raised an alert only when someone pressed Scan in Smart Notifications, and only in that person's bell.
Now a daily job tells each assignee, once, about their open tasks that were due yesterday on the company's clock: a
dashboard login in its bell (and by email if they chose it), an employee login in My Space's bell and by email. A
task with nobody on it is told to whoever made its project. "Once" needs no marker: a task is due on one day only.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone


def _lines(tasks):
    shown = [f'- {t.title} ({t.project.name})' for t in tasks[:6]]
    if len(tasks) > 6:
        shown.append(f'- and {len(tasks) - 6} more')
    return '\n'.join(shown)


def tell_newly_overdue(now=None):
    """Alert the owners of the open tasks due yesterday, per company. Returns how many people were told."""
    from core.models import Company, CompanyUser, Task
    from core.modules import active_company_ids
    from core.notification_utils import notify_company_users, notify_employees
    from core.scheduling import zone_name

    now = now or timezone.now()
    told = 0
    for company in Company.objects.filter(id__in=active_company_ids('project_manager_agent')):
        zone = ZoneInfo(zone_name(company.timezone_name))
        yesterday = now.astimezone(zone).date() - timedelta(days=1)
        start = datetime.combine(yesterday, time.min, tzinfo=zone)
        tasks = (Task.objects.filter(project__company=company, due_date__gte=start,
                                     due_date__lt=start + timedelta(days=1))
                 .exclude(status='done').select_related('assignee', 'project', 'project__created_by_company_user')
                 .order_by('due_date', 'id'))
        logins = {cu.login_user_id: cu for cu in CompanyUser.objects.filter(company=company, is_active=True)
                  .exclude(login_user=None)}
        for_login, for_employee, unowned = defaultdict(list), defaultdict(list), defaultdict(list)
        for task in tasks:
            if task.assignee_id in logins:
                for_login[logins[task.assignee_id]].append(task)
            elif task.assignee_id:
                for_employee[task.assignee].append(task)
            elif task.project.created_by_company_user_id:
                unowned[task.project.created_by_company_user].append(task)

        def title(items, whose='Your task'):
            if len(items) == 1:
                return f'{whose} is overdue: {items[0].title[:150]}'
            return f'{len(items)} {"of your tasks" if whose == "Your task" else "tasks with no owner"} are overdue'

        for login, items in for_login.items():
            told += bool(notify_company_users(
                [login], title=title(items), severity='warning', kind='pm_task_overdue',
                message=f'Due yesterday ({yesterday:%d %b}) and still open:\n{_lines(items)}',
                link='/project-manager/dashboard?tab=tasks'))
        for user, items in for_employee.items():
            told += bool(notify_employees(
                [user], title=title(items), kind='pm_task_overdue', link='/me/work', email_subject=title(items),
                message=f'Due yesterday ({yesterday:%d %b}) and still open:\n{_lines(items)}'))
        for login, items in unowned.items():
            told += bool(notify_company_users(
                [login], title=title(items, whose='A task with no owner'), severity='warning', kind='pm_task_overdue',
                message=f'Due yesterday ({yesterday:%d %b}), still open, and nobody is on it:\n{_lines(items)}',
                link='/project-manager/dashboard?tab=tasks'))
    return told
