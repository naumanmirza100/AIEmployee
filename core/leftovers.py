"""What a lapsed agent leaves behind, and the few calls that may still remove it.

Approved leave, company holidays, meetings and booked interviews go on blocking
bookings in the other agents after the agent that made them lapses. The only
screens that could cancel them are that agent's own, which are locked, so a
wrong entry stayed until the company subscribed again or support edited the
database.

`CLEAN_UPS` is the whole list of calls a company may still make to an agent it
no longer has. The gate (api/middleware/module_access.py) lets exactly these
through, for a company that had the agent and nobody else, and the lock screen
offers them (`upcoming`). Each call keeps its own rules about who may make it.

Not every GET, as was first proposed: that would hand a non-paying customer all
of the agent's data, and every GET that calls the AI.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, time
from datetime import timezone as dt_timezone

from django.utils import timezone

#: Sent as the reason, where the call asks for one.
REASON = 'Removed from the calendar while the agent is not active.'
#: The lock screen is not a calendar: the next few months are what block a booking.
LIMIT = 50


@dataclass(frozen=True)
class CleanUp:
    kind: str                   # what the entry is
    module: str                 # the agent it belongs to
    label: str                  # ...in words, on the lock screen
    button: str
    methods: tuple
    path: str                   # under /api/; {id} is the entry's id
    #: What the body must say when the address does other things too, and the
    #: only other keys it may then carry. Empty: the address does one thing.
    says: dict = field(default_factory=dict)
    also: tuple = ()

    @property
    def pattern(self):
        return re.compile('^' + re.escape(self.path).replace(re.escape('{id}'), r'\d+') + '/?$')

    def call(self, entry_id) -> dict:
        """The request the lock screen makes to remove entry `entry_id`."""
        body = dict(self.says)
        if 'meeting_id' in self.also:
            body['meeting_id'] = entry_id
        if 'reason' in self.also:
            body['reason'] = REASON
        return {'method': self.methods[0], 'path': '/' + self.path.replace('{id}', str(entry_id)), 'body': body}


CLEAN_UPS = (
    CleanUp('leave', 'hr_agent', 'Leave', 'Withdraw leave',
            ('POST',), 'hr/leave-requests/{id}/withdraw', also=('reason',)),
    CleanUp('holiday', 'hr_agent', 'Company holiday', 'Remove holiday',
            ('DELETE',), 'hr/holidays/{id}/delete'),
    CleanUp('hr_meeting', 'hr_agent', 'HR meeting', 'Cancel meeting',
            ('POST',), 'hr/meetings/{id}/cancel', also=('reason',)),
    CleanUp('pm_meeting', 'project_manager_agent', 'Meeting', 'Cancel meeting',
            ('POST',), 'project-manager/ai/meetings/respond',
            says={'action': 'withdrawn'}, also=('meeting_id', 'reason')),
    CleanUp('frontline_meeting', 'frontline_agent', 'Meeting', 'Cancel meeting',
            ('DELETE',), 'frontline/meetings/{id}/delete'),
    CleanUp('interview', 'recruitment_agent', 'Interview', 'Cancel interview',
            ('PATCH', 'PUT'), 'recruitment/interviews/{id}/update', says={'status': 'CANCELLED'}),
    CleanUp('campaign', 'marketing_agent', 'Campaign', 'Stop campaign',
            ('POST',), 'marketing/campaigns/{id}/stop'),
)
BY_KIND = {c.kind: c for c in CLEAN_UPS}

#: Why the entries matter, said once above them on the lock screen.
NOTES = {
    'hr_agent': 'Approved leave, company holidays and HR meetings still block meeting bookings in your '
                'other agents. Remove any that are no longer right.',
    'project_manager_agent': 'These meetings still block bookings in your other agents. '
                             'Cancel any that will not take place.',
    'frontline_agent': 'These meetings still block bookings in your other agents. '
                       'Cancel any that will not take place.',
    'recruitment_agent': "Booked interviews are still on the interviewers' calendars. "
                         'Cancel any that will not take place.',
    'marketing_agent': 'Nothing is being sent, but an active campaign starts again by itself the day '
                       'you subscribe again. Stop any you do not want to resume.',
}


def is_clean_up(module_name, method, path, read_body) -> bool:
    """Is this one of the calls above? `path` is what follows /api/ (and any
    version); `read_body` returns the raw body, and is asked only when the
    address does more than one thing."""
    for c in CLEAN_UPS:
        if c.module != module_name or method not in c.methods or not c.pattern.match(path):
            continue
        if not c.says:
            return True
        try:
            body = json.loads(read_body() or b'{}')
        except (ValueError, TypeError):
            return False
        if not isinstance(body, dict) or set(body) - set(c.says) - set(c.also):
            return False
        return all(str(body.get(key, '')).strip().lower() == str(value).lower()
                   for key, value in c.says.items())
    return False


def had_module(company, module_name) -> bool:
    """The company has, or once had, this agent. Nothing to clean up otherwise."""
    from core.models import CompanyModulePurchase
    company_id = getattr(company, 'pk', company)
    return bool(company_id) and CompanyModulePurchase.objects.filter(
        company_id=company_id, module_name=module_name).exists()


# ---- what is still there ------------------------------------------------------

def _entry(kind, entry_id, title, *, starts_at=None, ends_at=None, on=None, until=None):
    c = BY_KIND[kind]
    if starts_at:
        order = starts_at
    elif on:
        order = datetime.combine(on, time.min, tzinfo=dt_timezone.utc)
    else:
        order = datetime.max.replace(tzinfo=dt_timezone.utc)        # no date: after everything that has one
    return {
        'kind': kind, 'id': entry_id, 'label': c.label, 'title': title, 'button': c.button,
        'starts_at': starts_at.isoformat() if starts_at else None,
        'ends_at': ends_at.isoformat() if ends_at else None,
        'on': on.isoformat() if on else None,               # whole days: a date, not a time
        'until': until.isoformat() if until else None,
        'call': c.call(entry_id),
        '_sort': order,
    }


def _booked(source_key, company, now):
    """(row, booking) for each of the company's entries from one calendar source
    that still occupies somebody: the same rule the clash check uses."""
    from core.scheduling.sources import SOURCES
    source = SOURCES[source_key]
    for row in source.upcoming(now, company.id):
        booking = source.booking(row)
        if booking is not None and booking.ends_at > now and booking.unique_seats():
            yield row, booking


def _hr(login, company, now):
    from api.views.hr_agent import _caller_login_user_id, _is_hr_admin
    from hr_agent.models import Holiday
    admin = _is_hr_admin(login)
    me = _caller_login_user_id(login)
    for leave, booking in _booked('leave', company, now):
        mine = bool(me) and str(me) == str(leave.employee.user_id)
        yield (admin or mine), _entry('leave', leave.id, leave.employee.full_name,
                                      starts_at=booking.starts_at, on=leave.start_date, until=leave.end_date)
    # Only the holidays that block a booking: company-wide days off.
    for day in Holiday.objects.filter(company=company, region='', is_working_day=False,
                                      date__gte=timezone.localdate()).order_by('date'):
        yield admin, _entry('holiday', day.id, day.name, on=day.date, until=day.date)
    for meeting, booking in _booked('hr', company, now):
        # A private meeting's title (an exit interview, say) is for HR only.
        title = meeting.title if (admin or not booking.is_private) else 'Private meeting'
        yield True, _entry('hr_meeting', meeting.id, title, starts_at=booking.starts_at, ends_at=booking.ends_at)


def _project_manager(login, company, now):
    for meeting, booking in _booked('pm', company, now):
        yield meeting.organizer_id == login.id, _entry(           # only its organizer may cancel it
            'pm_meeting', meeting.id, meeting.title, starts_at=booking.starts_at, ends_at=booking.ends_at)


def _frontline(login, company, now):
    for meeting, booking in _booked('frontline', company, now):
        yield True, _entry('frontline_meeting', meeting.id, meeting.title,
                           starts_at=booking.starts_at, ends_at=booking.ends_at)


def _recruitment(login, company, now):
    for interview, booking in _booked('recruitment', company, now):
        yield True, _entry('interview', interview.id, f'{interview.candidate_name} ({interview.job_role})',
                           starts_at=booking.starts_at, ends_at=booking.ends_at)


def _marketing(login, company, now):
    # Nothing is sent for a lapsed agent, but a campaign left active starts
    # again by itself the day the company comes back. Campaigns belong to a
    # user: the one this login acts as (see marketing's own lookup).
    from django.contrib.auth import get_user_model
    from marketing_agent.models import Campaign
    owner = get_user_model().objects.filter(email=login.email).first() if login.email else None
    if owner is None:
        return
    for campaign in Campaign.objects.filter(owner=owner, status='active').order_by('name'):
        yield True, _entry('campaign', campaign.id, campaign.name)


_FINDERS = {
    'hr_agent': _hr,
    'project_manager_agent': _project_manager,
    'frontline_agent': _frontline,
    'recruitment_agent': _recruitment,
    'marketing_agent': _marketing,
}


def upcoming(login, module_name, now=None):
    """{'items': what this login may remove, soonest first,
        'others': how many more belong to somebody else,
        'more': how many of its own did not fit}.

    Empty unless the company had the agent and no longer has it: an agent that
    is open has its own screens for this.
    """
    from core.modules import has_module
    company = login.company
    finder = _FINDERS.get(module_name)
    if finder is None or not had_module(company, module_name) or has_module(company, module_name):
        return {'items': [], 'others': 0, 'more': 0, 'note': ''}
    now = now or timezone.now()
    mine, others = [], 0
    for allowed, entry in finder(login, company, now):
        if allowed:
            mine.append(entry)
        else:
            others += 1
    mine.sort(key=lambda e: e.pop('_sort'))
    return {'items': mine[:LIMIT], 'others': others, 'more': max(0, len(mine) - LIMIT),
            'note': NOTES[module_name]}
