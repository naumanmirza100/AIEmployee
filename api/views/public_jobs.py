from datetime import timedelta

from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status

from recruitment_agent.models import JobDescription, JobApplication


def _check_job_open(job):
    """
    Returns (ok, error_response) — error_response is None when the job is open.
    Checks: is_active flag, application_open_date, application_close_date.

    A ±1 day tolerance is applied to both date checks to absorb UTC offset
    differences (server is UTC; applicants may be in UTC+5 or similar zones).
    If no dates are set the job is freely accessible while active.
    """
    if not job.is_active:
        return False, Response(
            {
                'status': 'error',
                'code': 'POSITION_CLOSED',
                'message': 'This position is no longer accepting applications.',
            },
            status=status.HTTP_410_GONE,
        )

    if not job.application_open_date and not job.application_close_date:
        return True, None

    today = timezone.now().date()

    # Block only if today is strictly MORE than 1 day before the open date,
    # giving a 1-day grace period for UTC+ timezones.
    if job.application_open_date and today < (job.application_open_date - timedelta(days=1)):
        open_str = job.application_open_date.strftime('%B %d, %Y')
        return False, Response(
            {
                'status': 'error',
                'code': 'NOT_YET_OPEN',
                'message': f'Applications for this position open on {open_str}.',
                'open_date': job.application_open_date.isoformat(),
            },
            status=status.HTTP_410_GONE,
        )

    # Block only if today is strictly MORE than 1 day after the close date.
    if job.application_close_date and today > (job.application_close_date + timedelta(days=1)):
        return False, Response(
            {
                'status': 'error',
                'code': 'POSITION_CLOSED',
                'message': 'Applications for this position are now closed.',
                'close_date': job.application_close_date.isoformat(),
            },
            status=status.HTTP_410_GONE,
        )

    return True, None


def _no_cache(response):
    """Prevent browsers and proxies from caching job status responses."""
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response['Pragma'] = 'no-cache'
    return response


@api_view(['GET'])
@permission_classes([AllowAny])
def public_job_detail(request, job_id):
    try:
        job = JobDescription.objects.select_related('company').get(pk=job_id)
    except JobDescription.DoesNotExist:
        return _no_cache(Response(
            {'status': 'error', 'code': 'NOT_FOUND', 'message': 'Job not found.'},
            status=status.HTTP_404_NOT_FOUND,
        ))

    ok, err = _check_job_open(job)
    if not ok:
        return _no_cache(err)

    return _no_cache(Response({
        'status': 'success',
        'data': {
            'id': job.id,
            'title': job.title,
            'description': job.description,
            'location': job.location or '',
            'department': job.department or '',
            'type': job.type or '',
            'requirements': job.requirements or '',
            'company_name': job.company.name if job.company else '',
            'application_open_date': job.application_open_date.isoformat() if job.application_open_date else None,
            'application_close_date': job.application_close_date.isoformat() if job.application_close_date else None,
            'created_at': job.created_at.isoformat(),
        },
    }))


@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def public_job_apply(request, job_id):
    try:
        job = JobDescription.objects.get(pk=job_id)
    except JobDescription.DoesNotExist:
        return Response(
            {'status': 'error', 'code': 'NOT_FOUND', 'message': 'Job not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    ok, err = _check_job_open(job)
    if not ok:
        return err

    first_name = (request.data.get('first_name') or '').strip()
    last_name = (request.data.get('last_name') or '').strip()
    email = (request.data.get('email') or '').strip().lower()
    phone = (request.data.get('phone') or '').strip()
    current_location = (request.data.get('current_location') or '').strip() or None
    salary_expectation = (request.data.get('salary_expectation') or '').strip() or None
    education = (request.data.get('education') or '').strip() or None
    previous_company = (request.data.get('previous_company') or '').strip() or None
    previous_salary = (request.data.get('previous_salary') or '').strip() or None
    linkedin_url = (request.data.get('linkedin_url') or '').strip() or None
    github_url = (request.data.get('github_url') or '').strip() or None
    other_links = (request.data.get('other_links') or '').strip() or None
    cover_letter = (request.data.get('cover_letter') or '').strip() or None
    cv_file = request.FILES.get('cv_file')

    if not all([first_name, last_name, email, phone]):
        return Response(
            {'status': 'error', 'message': 'First name, last name, email, and phone are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not education:
        return Response(
            {'status': 'error', 'message': 'Education details are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if JobApplication.objects.filter(job=job, email=email).exists():
        return Response(
            {'status': 'error', 'message': 'You have already applied to this position with this email address.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if JobApplication.objects.filter(job=job, phone=phone).exists():
        return Response(
            {'status': 'error', 'message': 'This phone number has already been used to apply for this position.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    application = JobApplication.objects.create(
        job=job,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        current_location=current_location,
        salary_expectation=salary_expectation,
        education=education,
        previous_company=previous_company,
        previous_salary=previous_salary,
        linkedin_url=linkedin_url,
        github_url=github_url,
        other_links=other_links,
        cover_letter=cover_letter,
        cv_file=cv_file,
        cv_file_name=cv_file.name if cv_file else None,
    )

    return Response(
        {
            'status': 'success',
            'message': 'Your application has been submitted successfully!',
            'data': {'application_id': application.id},
        },
        status=status.HTTP_201_CREATED,
    )
