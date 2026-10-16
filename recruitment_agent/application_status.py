"""What a candidate's "track your application" page says, kept in step with Recruitment.

The page shows the status of the candidate's JobApplication. Only one button on the
Company Dashboard ever changed it, so the page said "Under Review" for good: through
the AI's screening, an interview invitation, a rejection email, and a hire.

A candidate learns nothing here before they would have heard it otherwise. The AI's
own Reject is not shown: no person has confirmed it and the candidate has not been
told. A rejection shows once the rejection email has gone, or an interview outcome of
Rejected has been sent to them.
"""
REVIEWED, SHORTLISTED, REJECTED = 'reviewed', 'shortlisted', 'rejected'


def _application_of(cv_record):
    if cv_record is None or not cv_record.job_application_id:
        return None
    return cv_record.job_application


def _set(application, status):
    if application is not None and application.status != status:
        application.status = status
        application.save(update_fields=['status'])


def after_screening(cv_record):
    """The AI has screened the CV. A candidate it chose for interview is invited at once."""
    decision = (cv_record.qualification_decision or '').upper()
    _set(_application_of(cv_record), SHORTLISTED if decision == 'INTERVIEW' else REVIEWED)


def after_decision(cv_record, decision, *, told_rejected=False):
    """A person changed the candidate's decision."""
    decision = (decision or '').upper()
    if decision == 'INTERVIEW':
        status = SHORTLISTED
    elif decision == 'REJECT' and told_rejected:
        status = REJECTED
    else:
        status = REVIEWED
    _set(_application_of(cv_record), status)


def after_interview_outcome(interview):
    """The interview's outcome was recorded; the candidate is emailed it at the same time."""
    outcome = (interview.outcome or '').upper()
    application = _application_of(interview.cv_record) if interview.cv_record_id else None
    if outcome == 'REJECTED':
        _set(application, REJECTED)
    elif outcome in ('HIRED', 'PASSED', 'ONSITE_INTERVIEW'):
        _set(application, SHORTLISTED)
