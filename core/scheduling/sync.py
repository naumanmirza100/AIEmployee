"""Keep `CalendarBlock` in step with the three meeting tables.

Signals, not call sites. Meetings are created and changed from the PM chat,
the HR form, chat and workflow engine, the Frontline dialog, email action
links and the Django admin. Hooking each of those by hand is how a path gets
missed, so every save, delete and attendee change on the meeting models
resyncs that meeting here, inside the caller's transaction. The clash check in
the next request therefore always sees it.

Queryset `.update()` sends no signal. Every such call in the meeting code is
followed by a save of the meeting itself, which resyncs it; anything else is
corrected by the nightly `rebuild()`.

A failed sync is logged, never raised: it runs in its own savepoint, so the
user's action still succeeds and the nightly rebuild repairs the table.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.utils import timezone

from core.scheduling.identity import member_ids
from core.scheduling.sources import SOURCES

logger = logging.getLogger(__name__)


def sync_meeting(source_key: str, meeting) -> int:
    """Rewrite one meeting's blocks. Returns how many rows it now has."""
    from core.models import CalendarBlock

    source = SOURCES[source_key]
    booking = source.booking(meeting)
    with transaction.atomic():
        CalendarBlock.objects.filter(source=source_key, source_id=meeting.pk).delete()
        if booking is None or not booking.company_id:
            return 0
        seats = booking.unique_seats()
        allowed = member_ids(booking.company_id, [s.user_id for s in seats])
        rows = [
            CalendarBlock(
                company_id=booking.company_id,
                user_id=seat.user_id,
                starts_at=booking.starts_at,
                ends_at=booking.ends_at,
                source=source_key,
                source_id=meeting.pk,
                role=seat.role,
                response=seat.response[:20],
                title=booking.title[:255],
                is_private=booking.is_private,
            )
            for seat in seats if seat.user_id in allowed
        ]
        CalendarBlock.objects.bulk_create(rows)
        return len(rows)


def delete_meeting_blocks(source_key: str, meeting_id) -> None:
    from core.models import CalendarBlock
    CalendarBlock.objects.filter(source=source_key, source_id=meeting_id).delete()


def safe_sync(source_key: str, meeting) -> None:
    try:
        sync_meeting(source_key, meeting)
    except Exception:
        logger.exception("CalendarBlock sync failed for %s #%s", source_key, getattr(meeting, 'pk', None))


def safe_sync_id(source_key: str, meeting_id) -> None:
    meeting = SOURCES[source_key].model.objects.filter(pk=meeting_id).first()
    if meeting is None:
        try:
            delete_meeting_blocks(source_key, meeting_id)
        except Exception:
            logger.exception("CalendarBlock delete failed for %s #%s", source_key, meeting_id)
        return
    safe_sync(source_key, meeting)


# ---------------------------------------------------------------------------
# Rebuild
# ---------------------------------------------------------------------------

def rebuild(*, company_id=None, since=None, log=None) -> dict:
    """Recompute blocks for every meeting that hasn't ended, and drop blocks
    whose meeting no longer exists. Past meetings are left alone: they can't
    clash with anything new.
    """
    from core.models import CalendarBlock

    since = since or timezone.now()
    stats = {}
    for key, source in SOURCES.items():
        synced = rows = 0
        for meeting in source.upcoming(since, company_id).iterator(chunk_size=200):
            try:
                rows += sync_meeting(key, meeting)
                synced += 1
            except Exception:
                logger.exception("rebuild: sync failed for %s #%s", key, meeting.pk)
        orphans = CalendarBlock.objects.filter(source=key).exclude(
            source_id__in=source.model.objects.values('pk'))
        if company_id:
            orphans = orphans.filter(company_id=company_id)
        removed, _ = orphans.delete()
        stats[key] = {'meetings': synced, 'blocks': rows, 'orphans_removed': removed}
        if log:
            log(f"{key}: {synced} meetings -> {rows} blocks, {removed} orphan rows removed")
    return stats


# ---------------------------------------------------------------------------
# Signal wiring
# ---------------------------------------------------------------------------

def _meeting_saved(source_key):
    relevant = SOURCES[source_key].relevant_fields

    def handler(sender, instance, created=False, raw=False, update_fields=None, **kwargs):
        if raw:
            return
        if update_fields is not None and not (set(update_fields) & relevant):
            return
        safe_sync(source_key, instance)
    return handler


def _meeting_deleted(source_key):
    def handler(sender, instance, **kwargs):
        try:
            delete_meeting_blocks(source_key, instance.pk)
        except Exception:
            logger.exception("CalendarBlock delete failed for %s #%s", source_key, instance.pk)
    return handler


def _participant_changed(source_key):
    def handler(sender, instance, raw=False, **kwargs):
        if raw:
            return
        safe_sync_id(source_key, instance.meeting_id)
    return handler


def _attendees_changed(source_key):
    def handler(sender, instance, action, reverse, pk_set, **kwargs):
        if action not in ('post_add', 'post_remove', 'post_clear'):
            return
        if not reverse:
            safe_sync(source_key, instance)
            return
        # Changed from the person's side (e.g. user.frontline_meetings.add(m)).
        # post_clear from that side carries no pk_set; the nightly rebuild
        # covers it.
        for meeting_id in pk_set or ():
            safe_sync_id(source_key, meeting_id)
    return handler


# Strong references: Django's dispatcher holds receivers weakly by default,
# and these closures would otherwise be collected straight away.
_RECEIVERS = []


def _connect(signal, receiver, sender, uid):
    _RECEIVERS.append(receiver)
    signal.connect(receiver, sender=sender, weak=False, dispatch_uid=uid)


def connect_signals():
    from django.apps import apps

    installed = {config.label for config in apps.get_app_configs()}
    for key, source in SOURCES.items():
        if source.model_label.split('.')[0] not in installed:
            continue
        model = source.model
        _connect(post_save, _meeting_saved(key), model, f'calblock-{key}-save')
        _connect(post_delete, _meeting_deleted(key), model, f'calblock-{key}-delete')
        if source.participant_model_label:
            pmodel = source.participant_model
            _connect(post_save, _participant_changed(key), pmodel, f'calblock-{key}-seat-save')
            _connect(post_delete, _participant_changed(key), pmodel, f'calblock-{key}-seat-delete')
        # HR and Frontline attendees are many-to-many fields; `.set()` / `.add()`
        # on those send m2m_changed rather than post_save. (PM's `participants`
        # is a reverse foreign key, covered by the participant handlers above.)
        attendees = getattr(model, 'participants', None)
        through = getattr(attendees, 'through', None)
        if through is not None:
            _connect(m2m_changed, _attendees_changed(key), through, f'calblock-{key}-attendees')
