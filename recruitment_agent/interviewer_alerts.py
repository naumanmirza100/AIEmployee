"""Tell interviewers about their interviews.

Colleagues added to an interview were told nothing, at any point: not when
they were added, when the candidate picked a time, when it moved, or when it
was cancelled. Recruitment's emails go to the candidate and the recruiter. An
interviewer found out from their own Meetings page, or when another booking was
refused because they were "busy".

Each alert is a `core.Notification` in the employee's bell, opening their
Meetings page. This is called from the places where one of those things
happens, never from the Interview save signal: that fires on every reminder and
status save and would flood people.
"""
import logging

logger = logging.getLogger(__name__)

MEETINGS_PAGE = '/me/meetings'


def _job(interview) -> str:
    job = getattr(interview.cv_record, 'job_description', None) if interview.cv_record_id else None
    title = (job.title if job else (interview.job_role or '').split('\n')[0]).strip()
    return title[:80] or 'the role'


def _when(interview) -> str:
    from recruitment_agent import interview_time
    return interview_time.when(interview) if interview.scheduled_datetime else ''


def _words(interview, event):
    who, job, when = interview.candidate_name, _job(interview), _when(interview)
    if event == 'added':
        return (f"You're interviewing {who}",
                f"For {job}. " + (f"{when}." if when else "The candidate has not picked a time yet; you'll hear when they do."))
    if event == 'removed':
        return (f"You're no longer interviewing {who}", f"You were taken off the interview for {job}.")
    if event == 'booked':
        return (f"Interview booked: {who}", f"For {job}. {when}.")
    if event == 'moved':
        return (f"Interview moved: {who}", f"For {job}. Now {when}.")
    if event == 'cancelled':
        return (f"Interview cancelled: {who}", f"The interview for {job}" + (f" ({when})" if when else '') + " is off.")
    raise ValueError(event)


def tell(interview, event, users=None) -> int:
    """Alert the interview's interviewers (or just `users`) that `event`
    happened: 'added', 'removed', 'booked', 'moved' or 'cancelled'. Returns how
    many were told. Never raises: an alert must not undo a booking."""
    try:
        from django.contrib.auth import get_user_model
        from core.models import Notification

        if users is None:
            people = list(interview.interviewers.all()) if interview.pk else []
        else:
            ids = [getattr(u, 'pk', u) for u in users]
            people = list(get_user_model().objects.filter(pk__in=ids))
        if not people:
            return 0
        title, message = _words(interview, event)
        Notification.objects.bulk_create([
            Notification(user=person, type=f'interview_{event}', notification_type='meeting_request',
                         title=title[:255], message=message, action_url=MEETINGS_PAGE)
            for person in people
        ])
        return len(people)
    except Exception:
        logger.exception("Could not alert interviewers of interview %s (%s)", getattr(interview, 'pk', None), event)
        return 0
