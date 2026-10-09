"""Keep each meeting's Google Calendar event in step with the meeting.

Recruitment interviews and sales calls put an event on the company's Google
calendar when they are booked. Nothing ever updated or deleted one, so a
meeting that moved or was called off stayed in Google at its old time.

Signals, not call sites: an interview or a call is saved from the booking
page, the reschedule dialog, the status menu, the board, the detail screen and
background jobs. Each save, once it has committed, asks
`core.google_calendar.follow` to look again; it calls Google only when the
event exists and is out of step. Deleting the row deletes the event.

Google is called after the transaction commits, never inside it: a booking
holds locks on the people it involves, and a slow answer from Google would
hold up every other booking for them.

Queryset `.update()` sends no signal. The one place that books that way (the
public sales booking page) calls `follow_meeting` itself.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_delete

logger = logging.getLogger(__name__)


def _interview_company(interview):
    from recruitment_agent.agents.interview_scheduling.interview_scheduling_agent import _company_for_interview
    return _company_for_interview(interview)


def _call_company(meeting):
    company_user = getattr(meeting, 'company_user', None)
    return getattr(company_user, 'company', None)


#: For each model: its start and length fields, the statuses that mean it is
#: off, and how to find its company. A finished meeting is not "off": its
#: event stays in the calendar as the record of what happened.
KINDS = {
    'recruitment_agent.Interview': {
        'start': 'scheduled_datetime', 'minutes': 'duration_minutes',
        'off': ('CANCELLED',), 'company': _interview_company,
    },
    'ai_sdr_agent.SDRMeeting': {
        'start': 'scheduled_at', 'minutes': 'duration_minutes',
        'off': ('cancelled',), 'company': _call_company,
    },
}


def _kind(meeting):
    return KINDS[meeting._meta.label]


def follow_meeting(meeting) -> str:
    """Bring this meeting's Google event in step with it now. See
    `core.google_calendar.follow` for what it returns. Never raises."""
    from core.google_calendar import follow
    try:
        kind = _kind(meeting)
        return follow(meeting, company=kind['company'](meeting),
                      start_dt=getattr(meeting, kind['start']),
                      duration_minutes=getattr(meeting, kind['minutes']),
                      active=meeting.status not in kind['off'])
    except Exception:
        logger.exception("Could not bring the Google event of %s #%s in step",
                         meeting._meta.label, getattr(meeting, 'pk', None))
        return 'failed'


def _saved(sender, instance, raw=False, **kwargs):
    if raw or not getattr(instance, 'google_event_id', ''):
        return
    # `follow` compares the event with the meeting and asks Google nothing when they agree, so
    # a save that moved nothing costs nothing.
    transaction.on_commit(lambda: follow_meeting(instance))


def _deleting(sender, instance, **kwargs):
    event_id = getattr(instance, 'google_event_id', '') or ''
    if not event_id:
        return
    from core.google_calendar import delete_google_event
    try:
        company = _kind(instance)['company'](instance)
    except Exception:
        logger.exception("Could not find the company of %s #%s", instance._meta.label, instance.pk)
        return
    transaction.on_commit(lambda: delete_google_event(company, event_id))


def connect_signals():
    from django.apps import apps
    installed = {config.label for config in apps.get_app_configs()}
    for label in KINDS:
        if label.split('.')[0] not in installed:
            continue
        model = apps.get_model(label)
        post_save.connect(_saved, sender=model, weak=False, dispatch_uid=f'google-event-{label}-save')
        pre_delete.connect(_deleting, sender=model, weak=False, dispatch_uid=f'google-event-{label}-delete')
