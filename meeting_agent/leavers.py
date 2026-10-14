"""Executive Meeting's part when a dashboard login is switched off (core/leavers.py).

Only the login that organised an executive meeting can open, move or cancel it.
When that login was switched off its meetings stayed booked on every invited
person's calendar, in every agent, with nobody able to cancel them, and its
tasks became invisible to everyone. A leaver who had only been invited stayed on
the participant list and went on being emailed the full details of every change.

Now, when the login goes off:
  * the meetings they organise that are still to come, and their open tasks,
    pass to another login of the company (the admin who switched them off when
    there is one, otherwise an owner or admin), who can move or cancel them;
  * they are taken off the meetings still to come that they were invited to, and
    off the open tasks they were assigned, without the 'removed' emails;
  * nobody who has left is emailed about a meeting or a task again
    (`still_with_the_company`, asked before every email this agent sends).

Finished meetings are left as they are, with their notes.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

#: A meeting in one of these states still takes people's time.
TO_COME = ('scheduled', 'in_progress', 'pending_confirmation')


def _still_to_come(meetings):
    # Times are kept as typed and filed as UTC (meeting_agent/clock.py), so "now"
    # can be off by the company's zone: a day's margin takes in every zone.
    return meetings.filter(status__in=TO_COME, scheduled_at__gte=timezone.now() - timedelta(days=1))


def _resync(meetings):
    from core.scheduling.sync import safe_sync
    for meeting in meetings:
        safe_sync('exec', meeting)


def still_with_the_company(company_user) -> bool:
    """Is the person behind this row still someone the company may email?

    A real dashboard login: while it is switched on. A stand-in row made so that
    an employee could be invited (always 'off', on purpose): while an employee
    login with that address is an active member of the company."""
    if company_user is None:
        return False
    if company_user.is_active:
        return True
    try:
        from core.tenancy import members_of
        address = (company_user.email or '').strip()
        return bool(address) and members_of(company_user.company).filter(
            email__iexact=address, is_active=True).exists()
    except Exception:
        logger.warning('Could not tell whether %s is still with the company; emailing as before',
                       getattr(company_user, 'pk', None), exc_info=True)
        return True


def login_switched_off(company_user, by=None) -> str:
    from core.leavers import heir_for
    from meeting_agent.models import ExecutiveMeeting, ExecutiveMeetingParticipant, ExecutiveTask

    said = []

    # Invited to: their seat goes, quietly, and the calendar follows.
    invited = list(_still_to_come(ExecutiveMeeting.objects.filter(participants__company_user=company_user)).distinct())
    if invited:
        ExecutiveMeetingParticipant.objects.filter(company_user=company_user, meeting__in=invited).delete()
        _resync(invited)
        said.append(f'They were taken off {len(invited)} executive meeting{"" if len(invited) == 1 else "s"} '
                    'they were invited to.')
    for task in ExecutiveTask.objects.filter(assignees=company_user).exclude(status='done'):
        task.assignees.remove(company_user)

    # Organised by them, or theirs: to somebody who can act on it.
    organised = list(_still_to_come(ExecutiveMeeting.objects.filter(organizer=company_user)))
    own_tasks = ExecutiveTask.objects.filter(company_user=company_user).exclude(status='done')
    task_count = own_tasks.count()
    if not organised and not task_count:
        return ' '.join(said)
    heir = heir_for(company_user, by)
    if heir is None:
        said.append('Their executive meetings and tasks are still under their login: '
                    'the company has no other login to give them to.')
        return ' '.join(said)
    name = heir.full_name or heir.email
    if organised:
        ids = [meeting.pk for meeting in organised]
        # The new organiser cannot also hold an invited seat in the same meeting.
        ExecutiveMeetingParticipant.objects.filter(company_user=heir, meeting_id__in=ids).delete()
        ExecutiveMeeting.objects.filter(pk__in=ids).update(organizer=heir)
        _resync(ExecutiveMeeting.objects.filter(pk__in=ids))
        said.append(f'{len(ids)} executive meeting{"" if len(ids) == 1 else "s"} they organised now '
                    f'belong{"s" if len(ids) == 1 else ""} to {name}, who can move or cancel '
                    f'{"it" if len(ids) == 1 else "them"}; '
                    f'{"it is" if len(ids) == 1 else "they are"} on {name}\'s calendar now.')
    if task_count:
        own_tasks.update(company_user=heir)
        said.append(f'{task_count} open executive task{"" if task_count == 1 else "s"} of theirs now '
                    f'belong{"s" if task_count == 1 else ""} to {name}.')
    return ' '.join(said)
