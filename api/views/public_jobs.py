import secrets
from datetime import timedelta

from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

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

    email_taken = JobApplication.objects.filter(job=job, email=email).exists()
    phone_taken = JobApplication.objects.filter(job=job, phone=phone).exists()

    if email_taken and phone_taken:
        return Response(
            {
                'status': 'error',
                'code': 'ALREADY_APPLIED',
                'duplicate_fields': ['email', 'phone'],
                'message': 'An application with this email and phone already exists for this position.',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if email_taken:
        return Response(
            {
                'status': 'error',
                'code': 'ALREADY_APPLIED',
                'duplicate_fields': ['email'],
                'message': 'This email address is already registered for this position.',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if phone_taken:
        return Response(
            {
                'status': 'error',
                'code': 'ALREADY_APPLIED',
                'duplicate_fields': ['phone'],
                'message': 'This phone number is already registered for this position.',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    access_token = secrets.token_urlsafe(40)

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
        access_token=access_token,
    )

    # Build tracking URL — points to React frontend
    frontend_base = (getattr(settings, 'FRONTEND_URL', None) or getattr(settings, 'BACKEND_URL', None) or '').strip().rstrip('/')
    if frontend_base and not frontend_base.startswith('http'):
        frontend_base = f'https://{frontend_base}'
    tracking_url = f"{frontend_base}/track-application/{access_token}" if frontend_base else ''

    # Send confirmation email with magic tracking link
    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        if email and from_email:
            candidate_name = f"{first_name} {last_name}".strip()
            ctx = {
                'candidate_name': candidate_name,
                'job_title': job.title,
                'applied_at': application.applied_at,
                'tracking_url': tracking_url,
            }
            html_body = render_to_string('recruitment_agent/emails/application_confirmation.html', ctx)
            text_body = render_to_string('recruitment_agent/emails/application_confirmation.txt', ctx)
            send_mail(
                subject=f"Application Received – {job.title}",
                message=text_body,
                from_email=from_email,
                recipient_list=[email],
                html_message=html_body,
                fail_silently=True,
            )
    except Exception:
        pass  # Never block application submission due to email failure

    return Response(
        {
            'status': 'success',
            'message': 'Your application has been submitted successfully!',
            'data': {
                'application_id': application.id,
                'tracking_url': tracking_url,
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([AllowAny])
def public_track_application(request, token):
    """Public API — return application status by access_token (no auth required)."""
    try:
        application = JobApplication.objects.select_related('job').get(access_token=token)
    except JobApplication.DoesNotExist:
        return Response(
            {'status': 'error', 'code': 'NOT_FOUND', 'message': 'Invalid or expired tracking link.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({'status': 'success', 'data': _build_app_payload(application)})


# ─── Candidate Portal ───────────────────────────────────────────────────────

def _build_app_payload(app):
    """Shared helper: serialize a JobApplication + linked interview for the portal."""
    cv_record = None
    interview = None
    try:
        from recruitment_agent.models import CVRecord, Interview
        cv_record = CVRecord.objects.filter(job_application=app).first()
        if cv_record:
            interview = Interview.objects.filter(cv_record=cv_record).order_by('-created_at').first()
    except Exception:
        pass

    status_label_map = {
        'pending': 'Under Review',
        'reviewed': 'Reviewed',
        'shortlisted': 'Shortlisted',
        'rejected': 'Not Selected',
    }

    interview_data = None
    if interview:
        interview_data = {
            'status': interview.status,
            'interview_type': getattr(interview, 'interview_type', None),
            'scheduled_datetime': interview.scheduled_datetime.isoformat() if getattr(interview, 'scheduled_datetime', None) else None,
            'meeting_link': getattr(interview, 'meeting_link', None),
            'confirmation_token': getattr(interview, 'confirmation_token', None),
            'selected_slot': getattr(interview, 'selected_slot', None),
            'outcome': getattr(interview, 'outcome', None),
        }

    job = app.job
    return {
        'application': {
            'id': app.id,
            'status': app.status,
            'status_label': status_label_map.get(app.status, app.status.title()),
            'applied_at': app.applied_at.isoformat(),
            'first_name': app.first_name,
            'last_name': app.last_name,
            'email': app.email,
            'phone': app.phone,
            'current_location': app.current_location,
            'salary_expectation': app.salary_expectation,
            'education': app.education,
            'previous_company': app.previous_company,
            'previous_salary': app.previous_salary,
            'linkedin_url': app.linkedin_url,
            'github_url': app.github_url,
            'other_links': app.other_links,
            'cover_letter': app.cover_letter,
            'cv_file_name': app.cv_file_name,
            'cv_file_url': app.cv_file.url if app.cv_file else None,
            'access_token': app.access_token,
        },
        'job': {
            'id': job.id,
            'title': job.title,
            'company_name': getattr(job, 'company_name', None),
            'location': getattr(job, 'location', None),
            'department': getattr(job, 'department', None),
            'type': getattr(job, 'type', None),
        },
        'cv_record': {
            'qualification_decision': cv_record.qualification_decision,
            'role_fit_score': cv_record.role_fit_score,
        } if cv_record else None,
        'interview': interview_data,
    }


@api_view(['POST'])
@permission_classes([AllowAny])
def request_candidate_portal_access(request):
    """Send a magic-link to the candidate so they can view all their applications."""
    email = (request.data.get('email') or '').strip().lower()
    if not email:
        return Response({'status': 'error', 'message': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

    if JobApplication.objects.filter(email=email).exists():
        try:
            from django.core import signing
            token = signing.dumps({'email': email}, salt='candidate-portal')

            frontend_base = (getattr(settings, 'FRONTEND_URL', None) or getattr(settings, 'BACKEND_URL', None) or '').strip().rstrip('/')
            if frontend_base and not frontend_base.startswith('http'):
                frontend_base = f'https://{frontend_base}'
            portal_url = f"{frontend_base}/candidate-portal/{token}" if frontend_base else ''

            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
            if from_email and portal_url:
                html_body = render_to_string('recruitment_agent/emails/candidate_portal_access.html', {
                    'portal_url': portal_url,
                    'email': email,
                })
                text_body = render_to_string('recruitment_agent/emails/candidate_portal_access.txt', {
                    'portal_url': portal_url,
                    'email': email,
                })
                send_mail(
                    subject="Access Your Application Portal",
                    message=text_body,
                    from_email=from_email,
                    recipient_list=[email],
                    html_message=html_body,
                    fail_silently=True,
                )
        except Exception:
            pass

    # Always return success to avoid email enumeration
    return Response({'status': 'success', 'message': 'If we found applications for this email, an access link has been sent.'})


@api_view(['GET'])
@permission_classes([AllowAny])
def candidate_portal_data(request, token):
    """Return all applications for the candidate identified by a signed portal token."""
    from django.core import signing
    try:
        data = signing.loads(token, salt='candidate-portal', max_age=86400)  # 24-hour validity
        email = data.get('email', '')
    except Exception:
        return Response(
            {'status': 'error', 'code': 'INVALID_TOKEN', 'message': 'This link has expired or is invalid. Please request a new one.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    applications = JobApplication.objects.filter(email=email).select_related('job').order_by('-applied_at')
    payload = [_build_app_payload(app) for app in applications]

    return Response({'status': 'success', 'email': email, 'data': payload, 'total': len(payload)})
