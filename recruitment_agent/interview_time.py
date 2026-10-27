"""Interview times in the recruiter's own timezone, and who an interview occupies.

A recruiter's interview hours and slots are wall-clock times ("10:00"), stored
without a zone. Everything used to read them as the server's zone, UTC: the
candidate was told 10:00 AM, while the recruiter's dashboard, the Google Meet
event and the reminders all used 10:00 UTC — 3 PM for a recruiter in Karachi.

The rules, in one place:
  * An interview's zone is its own `timezone_name` once booked, else the
    recruiter's settings' zone, else UTC (what older data always meant).
  * A time the candidate or recruiter picks without an offset is read in that
    zone; one with an offset is an exact instant already.
  * Anything shown to a person says which zone it is in.
"""
from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from core.scheduling import zone_name as _valid_zone
from core.scheduling.conflicts import when_label, zone_caption, zone_info  # noqa: F401 (zone_caption is used from here)


def settings_for(interview):
    """The interview settings that apply to `interview`: the job's own, whoever
    set them up; else the defaults of the recruiter running it (company login
    first, then the legacy auth-user recruiter), then of the job's owner."""
    from recruitment_agent.models import RecruiterInterviewSettings
    from recruitment_agent.sharing import job_interview_settings

    job = (interview.cv_record.job_description
           if interview.cv_record_id and interview.cv_record and interview.cv_record.job_description_id
           else None)
    found = job_interview_settings(job)
    if found:
        return found
    owners = []
    if interview.company_user_id:
        owners.append({'company_user_id': interview.company_user_id})
    if interview.recruiter_id:
        owners.append({'recruiter_id': interview.recruiter_id})
    if job is not None and job.company_user_id:
        owners.append({'company_user_id': job.company_user_id})
    for owner in owners:
        found = RecruiterInterviewSettings.objects.filter(job__isnull=True, **owner).first()
        if found:
            return found
    return None


def zone_for(interview, settings=None) -> str:
    if interview.timezone_name:
        return interview.timezone_name
    settings = settings if settings is not None else settings_for(interview)
    if settings is not None and settings.timezone_name:
        return settings.timezone_name
    if interview.company_user_id:
        from recruitment_agent.models import RecruiterInterviewSettings
        other = (RecruiterInterviewSettings.objects
                 .filter(company_user_id=interview.company_user_id)
                 .exclude(timezone_name='').values_list('timezone_name', flat=True).first())
        if other:
            return other
    return 'UTC'


def stored_zone(interview) -> str:
    """The zone to show or match an already-booked `scheduled_datetime` in.

    Not `zone_for`: interviews booked before zones were recorded hold the
    recruiter's clock digits as if they were UTC, so they are shown in UTC —
    converting them with the recruiter's zone, now known, would move them.
    """
    return interview.timezone_name or 'UTC'


def when(interview) -> str:
    """The booked time as people should read it, or the stored text."""
    if interview.scheduled_datetime:
        return label(interview.scheduled_datetime, stored_zone(interview))
    return interview.selected_slot or 'TBD'


def aware(value, tz_name) -> datetime | None:
    """`value` (ISO text or a datetime) as an exact instant. Without an offset
    it is the recruiter's wall-clock time, so it is read in `tz_name`."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if timezone.is_naive(dt):
        dt = dt.replace(tzinfo=zone_info(tz_name))
    return dt


def local(dt, tz_name) -> datetime:
    return dt.astimezone(zone_info(tz_name))


def slot_key(dt, tz_name) -> str:
    """'YYYY-MM-DDTHH:MM' on the recruiter's clock — how slots are stored."""
    return f"{local(dt, tz_name):%Y-%m-%dT%H:%M}"


def label(dt, tz_name) -> str:
    """'Monday, October 06, 2026 at 10:00 AM (Asia/Karachi, UTC+05:00)'."""
    return when_label(dt, tz_name)


def remember_timezone(company_user, raw) -> None:
    """Record the recruiter's browser zone where none is known yet.

    Only fills blanks: a zone already chosen is kept, so opening the dashboard
    from another country doesn't silently move every slot. A recruiter with no
    settings at all gets a default row to hold it (its defaults are the same
    ones used when no row exists).
    """
    tz = _valid_zone(raw, default='')
    if not tz or company_user is None:
        return
    from recruitment_agent.models import RecruiterInterviewSettings
    qs = RecruiterInterviewSettings.objects.filter(company_user=company_user)
    if not qs.exists():
        RecruiterInterviewSettings.objects.get_or_create(
            company_user=company_user, job=None, defaults={'timezone_name': tz})
        return
    qs.filter(timezone_name='').update(timezone_name=tz)


def company_id_for(interview):
    if interview.company_user_id:
        return interview.company_user.company_id
    job = getattr(interview.cv_record, 'job_description', None) if interview.cv_record_id else None
    return getattr(job, 'company_id', None)


def people(interview, extra_user_ids=()) -> list[int]:
    """Employee logins an interview occupies — the recruiter and the
    interviewers, plus `extra_user_ids` — keeping only members of the company.
    Works before the interview has a time, unlike the calendar's booking."""
    from core.scheduling.identity import login_user_id_for_company_user, member_ids
    ids = set(extra_user_ids)
    if interview.pk:
        ids.update(interview.interviewers.values_list('id', flat=True))
    if interview.company_user_id:
        ids.add(login_user_id_for_company_user(interview.company_user))
    elif interview.recruiter_id:
        ids.add(interview.recruiter_id)
    company_id = company_id_for(interview)
    ids.discard(None)
    return sorted(member_ids(company_id, ids)) if company_id else []


def bookable_slots(job, now=None) -> int:
    """How many of `job`'s interview slots a candidate could still book: switched on, still ahead, and not taken by
    another interview for this job. Invitations went out with nothing left to book, and the link then said the period
    had ended or showed an empty grid (CO-228)."""
    from django.utils import timezone
    from recruitment_agent import sharing
    from recruitment_agent.models import Interview
    settings = sharing.job_interview_settings(job)
    if settings is None or not isinstance(settings.time_slots_json, list):
        return 0
    tz = settings.timezone_name or 'UTC'
    now = now or timezone.now()
    taken = {slot_key(other.scheduled_datetime, stored_zone(other))
             for other in Interview.objects.filter(cv_record__job_description=job, status__in=['SCHEDULED', 'CONFIRMED'],
                                                   scheduled_datetime__isnull=False)}
    count = 0
    for slot in settings.time_slots_json:
        if not slot.get('available', True):
            continue
        instant = aware(slot.get('datetime', ''), tz)
        if instant is None or instant <= now or slot_key(instant, tz) in taken:
            continue
        count += 1
    return count


def no_slots_message(job) -> str:
    return (f'No free interview slots for "{job.title}": add dates or hours in Interview Settings, then invite the '
            'candidates again. Nobody was emailed an invitation.')


def recruiter_on_calendar(interview) -> bool:
    """Whether the recruiter's dashboard login is a person on the shared calendar (linked to an employee login)."""
    if not interview.company_user_id:
        return True
    from core.scheduling.identity import login_user_id_for_company_user, member_ids
    user_id = login_user_id_for_company_user(interview.company_user)
    company_id = company_id_for(interview)
    return bool(user_id and company_id and member_ids(company_id, {user_id}))


def others_booked(interview):
    """Other booked interviews whose times this one must not overlap: those of the same job, whose slots are shared,
    and, when the recruiter's dashboard login is on no shared calendar, every interview that login runs. The calendar
    could not see such a recruiter, so two candidates of two jobs could book them at the same time (CO-186)."""
    from django.db.models import Q
    from recruitment_agent.models import Interview
    booked = (Interview.objects.filter(status__in=['SCHEDULED', 'CONFIRMED'], scheduled_datetime__isnull=False)
              .exclude(id=interview.id))
    job_id = interview.cv_record.job_description_id if interview.cv_record_id else None
    clash = Q(pk__in=[])
    if job_id:
        clash |= Q(cv_record__job_description_id=job_id)
    if interview.company_user_id and (not job_id or not recruiter_on_calendar(interview)):
        clash |= Q(company_user_id=interview.company_user_id)
    elif not job_id and interview.recruiter_id:
        clash |= Q(recruiter_id=interview.recruiter_id)
    return booked.filter(clash)


def booked_spans(interview) -> list:
    """(start, end) of each interview in `others_booked`."""
    from datetime import timedelta
    return [(other.scheduled_datetime, other.scheduled_datetime + timedelta(minutes=other.duration_minutes or 30))
            for other in others_booked(interview)]


def overlaps_any(spans, start, minutes) -> bool:
    """An overlap, not only an equal start: a booking a quarter-hour into another one clashes too (CO-186)."""
    from datetime import timedelta
    end = start + timedelta(minutes=minutes or 30)
    return any(s < end and start < e for s, e in spans)
