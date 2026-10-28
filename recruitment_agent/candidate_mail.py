"""Emails to candidates, in the hiring company's name, with replies going to a person (CO-187).

Every candidate email was headed 'Pay Per Project', signed 'Recruitment Team' and sent from the platform's one
address with no reply-to: the company's name appeared nowhere, the follow-up said 'reply to this email' to a mailbox
nobody reads, and the footer of the same email said not to reply. `who_hires` gives the templates the company's name
and whom to contact; `send` sends from '<Company> via Pay Per Project' with Reply-To that person.
"""
from email.utils import formataddr, parseaddr

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def _job_of(interview):
    cv = getattr(interview, 'cv_record', None) if interview is not None and interview.cv_record_id else None
    return cv.job_description if cv is not None and cv.job_description_id else None


def who_hires(interview=None, job=None) -> dict:
    """{'company_name', 'contact_name', 'contact_email'} for an interview or a job; empty strings when unknown."""
    job = job or (_job_of(interview) if interview is not None else None)
    company = getattr(job, 'company', None) if job is not None else None
    runs = interview.company_user if interview is not None and interview.company_user_id else None
    if company is None and runs is not None:
        company = runs.company
    contact = None
    for person in (runs, getattr(job, 'company_user', None) if job is not None else None):
        if person is not None and person.is_active and (person.email or '').strip():
            contact = person
            break
    email = contact.email.strip() if contact else ((getattr(company, 'email', '') or '').strip())
    return {
        'company_name': (getattr(company, 'name', '') or '').strip(),
        'contact_name': ((contact.full_name or '').strip() if contact else ''),
        'contact_email': email,
    }


def _from_address(company_name) -> str:
    name, address = parseaddr(getattr(settings, 'DEFAULT_FROM_EMAIL', '') or 'noreply@example.com')
    shown = f'{company_name} via Pay Per Project' if company_name else (name or 'Pay Per Project')
    return formataddr((' '.join(shown.split()), address))


def send(subject, text, html, to, *, interview=None, job=None, fail_silently=False) -> int:
    """Send one candidate email in the company's name, Reply-To the person to contact."""
    who = who_hires(interview, job)
    message = EmailMultiAlternatives(subject=' '.join(str(subject).split()), body=text,
                                     from_email=_from_address(who['company_name']), to=[to],
                                     reply_to=[who['contact_email']] if who['contact_email'] else None)
    if html:
        message.attach_alternative(html, 'text/html')
    return message.send(fail_silently=fail_silently)
