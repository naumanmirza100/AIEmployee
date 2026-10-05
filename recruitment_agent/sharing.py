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
"""
from __future__ import annotations

from django.db.models import Q


def jobs(company_user):
    """The company's jobs. Older jobs may have only the login that posted them."""
    from recruitment_agent.models import JobDescription
    cid = company_user.company_id
    return JobDescription.objects.filter(Q(company_id=cid)
                                         | Q(company__isnull=True, company_user__company_id=cid))


def cvs(company_user):
    """The company's candidates: CVs matched against one of its jobs."""
    from recruitment_agent.models import CVRecord
    cid = company_user.company_id
    return CVRecord.objects.filter(Q(job_description__company_id=cid)
                                   | Q(job_description__company__isnull=True,
                                       job_description__company_user__company_id=cid))


def interviews(company_user):
    """The company's interviews, whoever runs them."""
    from recruitment_agent.models import Interview
    cid = company_user.company_id
    return Interview.objects.filter(Q(company_user__company_id=cid)
                                    | Q(company_user__isnull=True, cv_record__job_description__company_id=cid))


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
