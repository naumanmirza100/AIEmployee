"""What the public "apply for this job" address will accept.

Anyone on the internet can call it. It used to check only that four boxes were
filled in and that the same email or phone had not applied to that job: the
file was stored as sent, of any type and any size, though the form promises
'up to 10MB'; the email and the link boxes were not checked at all, so a
made-up address was mailed and whatever was typed as a LinkedIn link was shown
to recruiters as one; and there was no limit on how often it could be called.

The checks here all run before anything is stored. In particular the file is
checked before the row is made, because saving the row is what writes the file.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from rest_framework.throttling import AnonRateThrottle

MAX_CV_BYTES = 10 * 1024 * 1024
#: The kinds of CV the screening can read, and the bytes each must start with.
CV_KINDS = {'.pdf': b'%PDF', '.docx': b'PK\x03\x04'}
#: Free-text boxes have no length of their own in the database.
MAX_TEXT = {'education': 5000, 'cover_letter': 10000, 'other_links': 2000}
LABELS = {
    'first_name': 'First name', 'last_name': 'Last name', 'email': 'Email', 'phone': 'Phone',
    'current_location': 'Current location', 'salary_expectation': 'Salary expectation',
    'education': 'Education', 'previous_company': 'Previous company', 'previous_salary': 'Previous salary',
    'linkedin_url': 'LinkedIn link', 'github_url': 'GitHub link', 'other_links': 'Other links',
    'cover_letter': 'Cover letter',
}
_web_link = URLValidator(schemes=['http', 'https'])


class PublicApplyThrottle(AnonRateThrottle):
    """So many applications an hour from one caller address, across all jobs.

    Generous on purpose: a university or an office is one address for many
    people. The rate is 'public_apply' in settings.REST_FRAMEWORK."""
    scope = 'public_apply'


def waiting_cap() -> int:
    """How many applications one job may have waiting to be screened.

    A limit per caller address is no limit to someone who changes address; this
    one holds whatever they do. Screening an applicant takes them off the count."""
    return int(getattr(settings, 'PUBLIC_APPLY_MAX_WAITING_PER_JOB', 500))


def cv_problem(upload):
    """Why this uploaded file cannot be taken as a CV, or None if it can."""
    if upload is None:
        return None
    name = (getattr(upload, 'name', '') or '').lower()
    kind = next((ext for ext in CV_KINDS if name.endswith(ext)), None)
    if kind is None:
        return 'Please upload your CV as a PDF or a Word document (.docx).'
    if (getattr(upload, 'size', 0) or 0) > MAX_CV_BYTES:
        return 'Your CV is larger than 10 MB. Please upload a smaller file.'
    if not upload.size:
        return 'The CV file is empty.'
    try:
        start = upload.read(len(CV_KINDS[kind]))
        upload.seek(0)
    except Exception:
        return 'The CV file could not be read. Please try again.'
    if start != CV_KINDS[kind]:
        return f'That file is not a real {"PDF" if kind == ".pdf" else "Word document"}. Please upload your CV again.'
    return None


def details_problem(application):
    """Why what was typed cannot be stored, as one sentence, or None.

    The model already says what an email, a link and each length must be;
    this asks it, and adds the two things it does not say."""
    try:
        application.full_clean(exclude=['cv_file', 'cv_file_name', 'access_token', 'job', 'status'],
                               validate_unique=False, validate_constraints=False)
    except ValidationError as refused:
        field, messages = next(iter(refused.message_dict.items()))
        return f'{LABELS.get(field, field)}: {messages[0]}'
    for field in ('linkedin_url', 'github_url'):
        value = getattr(application, field)
        if value:
            try:
                _web_link(value)
            except ValidationError:
                return f'{LABELS[field]}: enter a web address that starts with http:// or https://.'
    for field, most in MAX_TEXT.items():
        if len(getattr(application, field) or '') > most:
            return f'{LABELS[field]}: please keep this under {most:,} characters.'
    return None
