"""Telling people they have been booked into a meeting, when the agent that
booked them is HR or Frontline.

Only Project Manager told the people it invited. HR and Frontline blocked a
person's calendar the moment a meeting was saved and said nothing: no alert,
no invitation. An HR invitee found out by happening to open My work, or from a
reminder a day or fifteen minutes before; HR's Edit and Cancel told nobody at
all. (Recruitment tells its interviewers in `recruitment_agent.interviewer_alerts`.)

It is called from the places a meeting is booked, changed or cancelled, with a
picture of the meeting taken before the change:

    before = meeting_notices.snapshot('hr', meeting)      # None for a new meeting
    ...save the change...
    meeting_notices.tell('hr', meeting, before, actor_user_id=...)

Not from a save signal: the calendar is rewritten on every save, every reply
and by the nightly rebuild, and each of those would announce the meeting again.
Project Manager announces its own meetings, so it is not a source here.
"""
from __future__ import annotations

import logging

from core.scheduling.conflicts import when_label
from core.scheduling.identity import member_ids
from core.scheduling.sources import SOURCES

logger = logging.getLogger(__name__)

MEETINGS_PAGE = '/me/meetings'

#: The agents this speaks for, and what each one's invitation asks of the person.
AGENTS = {
    'hr': ('HR', 'Open your Meetings page to accept it or suggest another time.'),
    'frontline': ('Frontline', 'It is on your Meetings page.'),
}


def snapshot(source_key, meeting):
    """Who a meeting occupies and when, as things stand now: what `tell`
    compares against after a change. None when it occupies nobody (cancelled,
    withdrawn, finished)."""
    booking = SOURCES[source_key].booking(meeting)
    if booking is None or not booking.company_id:
        return None
    people = member_ids(booking.company_id, [seat.user_id for seat in booking.seats])
    return {'starts': booking.starts_at, 'ends': booking.ends_at, 'people': frozenset(people)}


def _when(meeting, moment):
    return when_label(moment, getattr(meeting, 'timezone_name', '') or 'UTC')


def tell(source_key, meeting, before, *, after='read', actor_user_id=None) -> int:
    """Tell everyone a change touches, in their bell and by email. `before` is
    the snapshot taken ahead of the change (None for a new meeting). Pass
    `after=None` for a meeting that has just been deleted; otherwise it is read
    from the meeting as saved.

    Whoever made the change (`actor_user_id`, their employee login) is not
    told about it. Returns how many people were told; never raises.
    """
    from core.notification_utils import notify_employees
    try:
        agent, ask = AGENTS[source_key]
        deleted = after is None
        if after == 'read':
            after = snapshot(source_key, meeting)
        title = (getattr(meeting, 'title', '') or 'Meeting').strip()
        was, now = (before or {}).get('people', frozenset()), (after or {}).get('people', frozenset())
        minutes = int(getattr(meeting, 'duration_minutes', 0) or 0)

        groups = []          # (people, bell title, message)
        if after is None:
            # A meeting marked completed occupies nobody either, and is not a
            # cancellation: only one that was cancelled or deleted is said to be off.
            if before is not None and (deleted or getattr(meeting, 'status', '') == 'cancelled'):
                groups.append((was, f"Meeting cancelled: {title}",
                               f'{agent} cancelled "{title}", which was {_when(meeting, before["starts"])}.'))
        else:
            when = _when(meeting, after['starts'])
            length = f" ({minutes} min)" if minutes else ''
            groups.append((now - was, f"You're invited: {title}",
                           f'{agent} booked you into "{title}", {when}{length}. {ask}'))
            groups.append((was - now, f"You're no longer in: {title}",
                           f'{agent} took you off "{title}".'))
            if before is not None and (before['starts'], before['ends']) != (after['starts'], after['ends']):
                groups.append((was & now, f"Meeting moved: {title}",
                               f'{agent} moved "{title}". It is now {when}{length}. {ask}'))

        from django.contrib.auth import get_user_model
        told = 0
        for people, heading, message in groups:
            ids = [u for u in people if u != actor_user_id]
            if not ids:
                continue
            told += notify_employees(get_user_model().objects.filter(pk__in=ids), title=heading, message=message,
                                     link=MEETINGS_PAGE, kind=f'{source_key}_meeting', email_subject=heading)
        return told
    except Exception:
        logger.exception("Could not tell people about %s meeting %s", source_key, getattr(meeting, 'pk', None))
        return 0
