"""Screening the people who applied through a job's public page.

The steps are the ones the "Process with AI" button runs: read the CV, sum it up,
enrich it, decide, and invite to interview whoever the AI approves. They used to run
only when someone pressed that button, on the Company Dashboard, outside Recruitment,
while Recruitment's own screen said public applications "are screened automatically".
Now a new application is also screened as it arrives (screen_soon), when the company
has Recruitment and the job's interview hours are set.
"""
from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from recruitment_agent import application_status, sharing

logger = logging.getLogger(__name__)


def has_recruitment(company) -> bool:
    """True only when the company's Recruitment Agent is bought and active."""
    from core.models import CompanyModulePurchase
    if company is None:
        return False
    purchase = CompanyModulePurchase.objects.filter(company=company, module_name='recruitment_agent').first()
    return bool(purchase and purchase.is_active())


def missing_interview_settings(job) -> list:
    """What the job still needs before its applicants can be screened and invited."""
    settings_row = sharing.job_interview_settings(job)
    if not settings_row:
        return ['Interview settings not configured']
    missing = []
    if not settings_row.schedule_from_date:
        missing.append('Start date')
    if not settings_row.schedule_to_date:
        missing.append('End date')
    if not settings_row.start_time:
        missing.append('Start time')
    if not settings_row.end_time:
        missing.append('End time')
    if not (settings_row.time_slots_json and len(settings_row.time_slots_json) > 0):
        missing.append('Time slots')
    return missing


def recruiter_for(job):
    """Who screening on arrival acts as: the job's owner, or else an active admin of the company."""
    from core.models import CompanyUser
    if job.company_user_id and job.company_user.is_active:
        return job.company_user
    return (CompanyUser.objects.filter(company_id=job.company_id, is_active=True, role__in=('owner', 'admin'))
            .order_by('id').first())


# A run that died keeps its claim this long, then another run may take the applicant.
CLAIM_FOR = timedelta(minutes=30)


NO_KEYWORDS = ("this job's description has nothing the AI can match CVs against (no skills or requirements), so "
               "candidates were scored but nobody was invited. Add the skills and requirements to the description, "
               "then process again.")


def job_keywords(job, job_desc_agent) -> list:
    """The job's keywords. A job saved without them (the AI failed, or the company had no Recruitment then) was
    screened blind for good, and anyone with a long skills list was invited (CO-103): they are worked out now and
    saved."""
    from core.api_key_service import KeyServiceError
    try:
        keywords = (json.loads(job.keywords_json) if job.keywords_json else {}).get('keywords') or []
    except (json.JSONDecodeError, TypeError, AttributeError):
        keywords = []
    if keywords or job_desc_agent is None or not (job.description or '').strip():
        return keywords
    try:
        parsed = job_desc_agent.parse_text(job.description)
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed and isinstance(parsed[0], dict) else {}
        keywords = (parsed or {}).get('keywords') or []
        if keywords:
            job.keywords_json = json.dumps(parsed)
            job.save(update_fields=['keywords_json'])
    except KeyServiceError:
        raise
    except Exception:
        logger.warning('Keywords for job %s could not be worked out', job.id, exc_info=True)
    return keywords


def not_screened(applications):
    """Applications with no screened candidate behind them. A record with no decision is a run that stopped
    half-way: it used to mark the applicant 'AI Analysed' for good (CO-181)."""
    from recruitment_agent.models import CVRecord
    screened = (CVRecord.objects.filter(job_application__isnull=False).exclude(qualification_decision__isnull=True)
                .exclude(qualification_decision='').values('job_application_id'))
    return applications.exclude(pk__in=screened)


def _claim(app) -> bool:
    """Take the applicant for this run; False when another run has it."""
    from recruitment_agent.models import JobApplication
    now = timezone.now()
    return bool(JobApplication.objects.filter(pk=app.pk).filter(
        Q(screening_started_at__isnull=True) | Q(screening_started_at__lt=now - CLAIM_FOR)
    ).update(screening_started_at=now))


def _release(app):
    from recruitment_agent.models import JobApplication
    JobApplication.objects.filter(pk=app.pk).update(screening_started_at=None)


def screen(job, applications, actor, agents) -> list:
    """Screen each application in turn. Returns one result per application, as the button shows them."""
    from recruitment_agent.models import CVRecord, JobApplication

    cv_agent, sum_agent = agents['cv_agent'], agents['sum_agent']
    enrich_agent, qualify_agent = agents['enrich_agent'], agents['qualify_agent']
    interview_agent, django_repo = agents.get('interview_agent'), agents['django_repo']
    from recruitment_agent.interview_time import bookable_slots
    slots_left = bookable_slots(job)

    job_kw_list = job_keywords(job, agents.get('job_desc_agent')) or None
    job_description_text = job.description or ''

    # The job owner's screening thresholds and email timings
    settings_owner = sharing.owner(job, actor)
    interview_threshold, hold_threshold = sharing.thresholds(settings_owner)
    interview_settings = sharing.job_interview_settings(job)
    auto_interview_type = getattr(interview_settings, 'default_interview_type', None) or 'ONLINE'
    email_settings = sharing.email_settings(settings_owner)

    results = []
    for idx, app in enumerate(applications):
        name = f'{app.first_name} {app.last_name}'.strip()
        if not app.cv_file:
            results.append({'application_id': app.id, 'applicant': name, 'skipped': True,
                            'reason': 'No CV file uploaded'})
            continue
        if idx > 0:
            time.sleep(0.5)
        # Two runs at once (a second tab, a retry, arrival screening) screened and invited the same people twice.
        if not _claim(app):
            results.append({'application_id': app.id, 'applicant': name, 'skipped': True,
                            'reason': 'Being screened by another run'})
            continue
        if not not_screened(JobApplication.objects.filter(pk=app.pk)).exists():
            _release(app)
            results.append({'application_id': app.id, 'applicant': name, 'skipped': True,
                            'reason': 'Already screened'})
            continue

        temp_path = None
        record_id = None
        try:
            suffix = Path(app.cv_file.name).suffix or '.pdf'
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                app.cv_file.open('rb')
                tmp.write(app.cv_file.read())
                app.cv_file.close()
                temp_path = Path(tmp.name)

            parsed = cv_agent.parse_file(str(temp_path))

            summary = sum_agent.summarize(parsed, job_kw_list)
            if not isinstance(summary, dict):
                summary = summary[0] if isinstance(summary, list) and summary else {}
            # The model wrote this from the CV's own text; it does not get to name a candidate record
            summary.pop('record_id', None)

            enriched = enrich_agent.enrich(parsed, summary)
            if not isinstance(enriched, dict):
                enriched = enriched[0] if isinstance(enriched, list) and enriched else {}

            qualified = qualify_agent.qualify(parsed, summary, job_kw_list, enriched, interview_threshold, hold_threshold)
            if not isinstance(qualified, dict):
                qualified = qualified[0] if isinstance(qualified, list) and qualified else {}

            # Saved once it is scored: a record linked first and scored after was left with no score when
            # scoring failed, and the applicant was never picked up again (CO-181). A leftover from such a run goes.
            CVRecord.objects.filter(job_application=app).filter(
                Q(qualification_decision__isnull=True) | Q(qualification_decision='')).delete()
            record_id = django_repo.store_parsed(app.cv_file_name or app.cv_file.name, parsed)
            if record_id:
                try:
                    cv_record = CVRecord.objects.get(id=record_id)
                    cv_record.job_description = job
                    cv_record.job_application = app
                    cv_record.insights_json = json.dumps(summary)
                    cv_record.enriched_json = json.dumps(enriched)
                    cv_record.qualification_json = json.dumps(qualified)
                    cv_record.role_fit_score = summary.get('role_fit_score') if isinstance(summary, dict) else None
                    cv_record.qualification_decision = qualified.get('decision') if isinstance(qualified, dict) else None
                    cv_record.qualification_confidence = qualified.get('confidence_score') if isinstance(qualified, dict) else None
                    cv_record.qualification_priority = qualified.get('priority') if isinstance(qualified, dict) else None
                    cv_record.save()
                    application_status.after_screening(cv_record)
                except CVRecord.DoesNotExist:
                    pass

            interview_scheduled = False
            interview_error = ''
            qual_decision = qualified.get('decision', '') if isinstance(qualified, dict) else ''
            if qual_decision == 'INTERVIEW' and interview_agent and app.email and slots_left <= 0:
                # Nothing left to book: the invitation would lead to an empty page (CO-228).
                interview_error = 'No free interview slots'
            elif qual_decision == 'INTERVIEW' and not job_kw_list:
                # Scored without anything to match against: nobody is invited on that (CO-103).
                interview_error = 'No job requirements to match against'
            elif qual_decision == 'INTERVIEW' and interview_agent and app.email:
                candidate_name = name or 'Candidate'
                # The job's title, as hand uploads use. It took the description's first line, which is what the
                # interview list, the export, the calendar and the "by role" chart then showed (CO-226).
                job_role = job.title or 'Position'
                try:
                    interview_result = interview_agent.schedule_interview(
                        candidate_name=candidate_name,
                        candidate_email=app.email,
                        job_role=job_role,
                        interview_type=auto_interview_type,
                        candidate_phone=app.phone,
                        cv_record_id=record_id,
                        recruiter_id=None,
                        company_user_id=actor.id,
                        email_settings=email_settings,
                        custom_slots=None,
                    )
                    interview_scheduled = interview_result.get('invitation_sent', False)
                except Exception as ie:
                    logger.error(f'Interview scheduling failed for {app.email}: {ie}')

            results.append({
                'application_id': app.id,
                'applicant': name,
                'record_id': record_id,
                'decision': qual_decision,
                'role_fit_score': summary.get('role_fit_score') if isinstance(summary, dict) else None,
                'interview_scheduled': interview_scheduled,
                'interview_error': interview_error,
                'skipped': False,
            })
        except Exception as exc:
            logger.error(f'Error processing application {app.id}: {exc}', exc_info=True)
            from api.views.recruitment_agent import _unreadable_reason
            reason = (_unreadable_reason(app.cv_file_name or app.cv_file.name, exc)
                      if isinstance(exc, ValueError) else str(exc))
            results.append({'application_id': app.id, 'applicant': name, 'skipped': True, 'reason': reason})
        finally:
            _release(app)
            if temp_path:
                try:
                    temp_path.unlink()
                except Exception:
                    pass
    return results


def screen_new_application(application_id) -> str:
    """Screen one public application, as it arrives. Returns what happened, for the log."""
    from api.views.recruitment_agent import _make_agents
    from recruitment_agent.models import JobApplication

    app = not_screened(JobApplication.objects.select_related('job__company', 'job__company_user')
                       .filter(pk=application_id)).first()
    if app is None:
        return 'already screened'
    job = app.job
    if not has_recruitment(job.company):
        return 'no Recruitment agent'
    missing = missing_interview_settings(job)
    if missing:
        # Left waiting: "Process with AI" screens it once the hours are set.
        return 'interview hours not set: ' + ', '.join(missing)
    actor = recruiter_for(job)
    if actor is None:
        return 'nobody to act for the company'
    [result] = screen(job, [app], actor, _make_agents(job.company))
    if result.get('interview_error') == 'No free interview slots':
        from core.notification_utils import notify_company_users
        from recruitment_agent.interview_time import no_slots_message
        name = result.get('applicant') or app.email
        notify_company_users(
            [actor], title=f'{name} should be interviewed, but no slot is free'[:255],
            message=f'The AI chose {name} for an interview for {job.title}. ' + no_slots_message(job),
            link='/recruitment/settings/interview', kind='recruitment_new_application', severity='warning',
            data={'job_id': job.id, 'application_id': app.id})
    return 'skipped: ' + result['reason'] if result.get('skipped') else f"screened: {result.get('decision')}"


def tell_recruiter(application):
    """The recruiter's bell, when someone applies through the job's public page.

    The applicant was emailed a confirmation and nobody at the company was told."""
    from core.notification_utils import notify_company_users
    job = application.job
    recruiter = recruiter_for(job)
    if recruiter is None:
        return
    name = f'{application.first_name} {application.last_name}'.strip() or application.email
    if not has_recruitment(job.company):
        next_step = 'Open the job on the Company Dashboard to see the application.'
    elif missing_interview_settings(job):
        next_step = ("It is waiting to be screened: set the job's interview hours, then press "
                     "Process with AI on the job.")
    else:
        next_step = 'The AI is screening it now; its score and decision will be with the candidates.'
    notify_company_users(
        [recruiter], title=f'New application: {name}, {job.title}'[:255],
        message=f'{name} applied for {job.title} through its public page. {next_step}',
        link='/recruitment/candidates', kind='recruitment_new_application',
        data={'job_id': job.id, 'application_id': application.id})


def screen_soon(application_id):
    """Screen a new application without keeping the applicant waiting for the AI.

    It runs on its own thread, as Recruitment's other background work does. Under the
    test settings (tasks run at once) it runs in place, so a test can see the result."""
    def run():
        try:
            outcome = screen_new_application(application_id)
            logger.info('Public application %s: %s', application_id, outcome)
        except Exception:
            logger.exception('Screening public application %s failed', application_id)

    def on_its_own_thread():
        try:
            run()
        finally:
            connection.close()      # the thread's own database connection

    if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
        run()
    else:
        threading.Thread(target=on_its_own_thread, name=f'screen-application-{application_id}', daemon=True).start()
