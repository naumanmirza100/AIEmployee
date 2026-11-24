"""Recruitment is the company's, not each login's.

Recruitment used to show each dashboard login only the jobs, candidates and
interviews it had created, so two recruiters in one company couldn't see each
other's work, and a leaver's pipeline had nobody who could open it. Jobs, CVs
and interviews now belong to the company, as the other agents' data does.

What stays personal:
  * each login's settings: follow-up and reminder timings and switches,
    screening thresholds, default interview hours. A job uses its owner's
    settings (the login that posted it, or was handed it), so a job's
    candidates are screened and emailed the same way whoever presses the
    button. A job whose owner has left uses the settings of whoever is acting.
  * Q&A chats and saved graph prompts.

A job's interview hours and slots belong to the job, whoever set them up.

Roles (24 Nov 2026, models.RecruitmentRole): a recruiter sees and does everything, as above; a hiring manager the jobs
they posted or are named on, with their candidates and interviews; an interviewer the interviews they sit in or run,
and those candidates. What each may change is checked by path in api/middleware/recruitment_roles.py.
"""
from __future__ import annotations

from django.db.models import Q


RECRUITER, HIRING_MANAGER, INTERVIEWER = 'recruiter', 'hiring_manager', 'interviewer'


def role(company_user) -> str:
    """The login's Recruitment role: an owner or admin is always a recruiter, and so is a login with none set."""
    if company_user is None:
        return RECRUITER
    known = getattr(company_user, '_recruitment_role', None)
    if known is None:
        from recruitment_agent.models import RecruitmentRole
        known = RECRUITER
        if (company_user.role or '').lower() not in ('owner', 'admin'):
            known = (RecruitmentRole.objects.filter(company_user_id=company_user.pk)
                     .values_list('role', flat=True).first()) or RECRUITER
        company_user._recruitment_role = known      # kept for the request: asked many times in one
    return known


def _login_user_id(company_user):
    """The employee login behind a dashboard login: interviewers on an interview are employee logins."""
    from core.scheduling.identity import login_user_id_for_company_user
    return login_user_id_for_company_user(company_user)


def _company_jobs(company_user):
    from recruitment_agent.models import JobDescription
    cid = company_user.company_id
    return JobDescription.objects.filter(Q(company_id=cid)
                                         | Q(company__isnull=True, company_user__company_id=cid))


def _company_cvs(company_user):
    from recruitment_agent.models import CVRecord
    cid = company_user.company_id
    return CVRecord.objects.filter(Q(job_description__company_id=cid)
                                   | Q(job_description__company__isnull=True,
                                       job_description__company_user__company_id=cid))


def _company_interviews(company_user):
    from recruitment_agent.models import Interview
    cid = company_user.company_id
    return Interview.objects.filter(Q(company_user__company_id=cid)
                                    | Q(company_user__isnull=True, cv_record__job_description__company_id=cid))


def _own_interviews(company_user):
    """Interviews this login runs or sits in."""
    from recruitment_agent.models import Interview
    sits_in = Q(interviewers__id=_login_user_id(company_user)) if _login_user_id(company_user) else Q(pk__in=[])
    return Interview.objects.filter(Q(company_user=company_user) | sits_in).values('pk')


def jobs(company_user):
    """The company's jobs this login may see. Older jobs may have only the login that posted them."""
    found = _company_jobs(company_user)
    who = role(company_user)
    if who == HIRING_MANAGER:
        from recruitment_agent.models import JobDescription
        theirs = JobDescription.objects.filter(Q(company_user=company_user) | Q(hiring_managers=company_user))
        return found.filter(pk__in=theirs.values('pk'))
    if who == INTERVIEWER:
        from recruitment_agent.models import Interview
        return found.filter(pk__in=Interview.objects.filter(pk__in=_own_interviews(company_user))
                            .values('cv_record__job_description'))
    return found


def cvs(company_user):
    """The company's candidates this login may see: CVs matched against one of its jobs."""
    found = _company_cvs(company_user)
    who = role(company_user)
    if who == HIRING_MANAGER:
        return found.filter(job_description__in=jobs(company_user).values('pk'))
    if who == INTERVIEWER:
        from recruitment_agent.models import Interview
        return found.filter(pk__in=Interview.objects.filter(pk__in=_own_interviews(company_user))
                            .values('cv_record'))
    return found


def interviews(company_user):
    """The company's interviews this login may see, whoever runs them."""
    found = _company_interviews(company_user)
    who = role(company_user)
    if who == HIRING_MANAGER:
        return found.filter(Q(cv_record__job_description__in=jobs(company_user).values('pk'))
                            | Q(pk__in=_own_interviews(company_user)))
    if who == INTERVIEWER:
        return found.filter(pk__in=_own_interviews(company_user))
    return found


def owner(job, actor):
    """Whose settings `job` uses: its owner's, or `actor`'s when it has no
    owner still working here."""
    if job is not None and job.company_user_id and job.company_user.is_active:
        return job.company_user
    return actor


def job_interview_settings(job):
    """The job's interview hours and slots, whoever set them up."""
    from recruitment_agent.models import RecruiterInterviewSettings
    if job is None:
        return None
    rows = RecruiterInterviewSettings.objects.filter(job=job)
    return ((rows.filter(company_user_id=job.company_user_id).first() if job.company_user_id else None)
            or rows.order_by('id').first())


def email_settings(person):
    """`person`'s follow-up and reminder timings for new interviews, or None
    for the defaults."""
    from recruitment_agent.models import RecruiterEmailSettings
    found = RecruiterEmailSettings.objects.filter(company_user=person).first() if person else None
    if found is None:
        return None
    return {
        'followup_delay_hours': found.followup_delay_hours,
        'reminder_hours_before': found.reminder_hours_before,
        'max_followup_emails': found.max_followup_emails,
        'min_hours_between_followups': found.min_hours_between_followups,
    }


def thresholds(person):
    """(interview, hold) screening thresholds `person` set, or (None, None)
    for the defaults."""
    from recruitment_agent.models import RecruiterQualificationSettings
    found = RecruiterQualificationSettings.objects.filter(company_user=person).first() if person else None
    if found is not None and found.use_custom_thresholds:
        return found.interview_threshold, found.hold_threshold
    return None, None


def owner_payload(job, viewer):
    """Who a job belongs to, as the dashboard shows it."""
    cu = job.company_user if job.company_user_id else None
    if cu is None:
        return None
    return {'id': cu.id, 'name': cu.full_name or cu.email, 'is_you': cu.id == viewer.id,
            'active': cu.is_active}
