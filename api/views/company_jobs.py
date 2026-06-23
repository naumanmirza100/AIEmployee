import json
import logging
import tempfile
import time
from pathlib import Path

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404

from recruitment_agent.models import (
    JobDescription, CareerApplication, JobApplication, CVRecord,
    RecruiterInterviewSettings, RecruiterQualificationSettings, RecruiterEmailSettings,
)
from api.serializers.career import JobDescriptionSerializer, CareerApplicationSerializer, JobApplicationSerializer
from api.permissions import IsCompanyUser, IsCompanyUserOnly
from api.authentication import CompanyUserTokenAuthentication
from core.models import CompanyUser, Company
from api.views.recruitment_agent import _make_agents

logger = logging.getLogger(__name__)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_company_job(request):
    """Create job position (Company only)"""
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        company = company_user.company
        
        data = request.data.copy()
        data['company'] = company.id
        # Honour is_active from the request; default True if not provided
        if 'is_active' not in data:
            data['is_active'] = True
        
        # Handle parse_keywords - can be boolean True/False or string "true"/"false"
        # Default to True to match Django views.py behavior
        parse_keywords_val = data.get('parse_keywords', True)
        if isinstance(parse_keywords_val, str):
            parse_keywords = parse_keywords_val.lower() in ('true', '1', 'yes')
        else:
            parse_keywords = bool(parse_keywords_val)
        
        serializer = JobDescriptionSerializer(data=data)
        
        if serializer.is_valid():
            # Save with company and company_user
            job = serializer.save(company=company, company_user=company_user)
            
            # Parse keywords if requested (defaults to True, same as Django views.py)
            keywords_json = None
            if parse_keywords and job.description:
                try:
                    agents = _make_agents(company)
                    job_desc_agent = agents['job_desc_agent']
                    log_service = agents['log_service']

                    logger.info(f"Parsing keywords for company job: {job.title}")
                    parsed = job_desc_agent.parse_text(job.description)
                    keywords_json = json.dumps(parsed)
                    logger.info(f"Keywords parsed successfully. Keywords count: {len(parsed.get('keywords', []))}")

                    # Update job with keywords
                    job.keywords_json = keywords_json
                    job.save(update_fields=['keywords_json'])

                except Exception as exc:
                    logger.error(f"Error parsing keywords: {str(exc)}", exc_info=True)
                    # Continue without keywords if parsing fails
            
            # Verify keywords were saved
            keywords_saved = job.keywords_json is not None
            logger.info(f"Company job created. ID: {job.id}, Title: {job.title}, Keywords saved: {keywords_saved}")
            
            return Response({
                'status': 'success',
                'message': 'Job position created successfully',
                'data': JobDescriptionSerializer(job).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error creating company job: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to create job position',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_company_jobs(request):
    """Get company's job positions (Company only)"""
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        company = company_user.company
        
        # Filter jobs by company_user - each user only sees their own jobs
        jobs = JobDescription.objects.filter(company_user=company_user).order_by('-created_at')
        
        # Filter by is_active if provided
        is_active = request.GET.get('is_active')
        if is_active is not None:
            is_active = is_active.lower() == 'true'
            jobs = jobs.filter(is_active=is_active)
        
        serializer = JobDescriptionSerializer(jobs, many=True)
        
        return Response({
            'status': 'success',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch job positions',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_company_job(request, id):
    """Update job position (Company only)"""
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        company = company_user.company
        # Users can only update their own jobs
        job = get_object_or_404(JobDescription, id=id, company_user=company_user)
        
        # When description is updated, always regenerate keywords
        description_changed = 'description' in request.data
        
        serializer = JobDescriptionSerializer(job, data=request.data, partial=True)
        
        if serializer.is_valid():
            job = serializer.save()
            
            if description_changed and job.description:
                try:
                    agents = _make_agents(company)
                    job_desc_agent = agents['job_desc_agent']
                    log_service = agents['log_service']

                    logger.info(f"Parsing keywords for company job update: {job.id}")
                    parsed = job_desc_agent.parse_text(job.description)
                    keywords_json = json.dumps(parsed)
                    logger.info(f"Keywords parsed successfully. Keywords count: {len(parsed.get('keywords', []))}")
                    
                    # Update job with keywords
                    job.keywords_json = keywords_json
                    job.save(update_fields=['keywords_json'])
                    
                except Exception as exc:
                    logger.error(f"Error parsing keywords: {str(exc)}", exc_info=True)
                    # Continue without updating keywords if parsing fails
            
            return Response({
                'status': 'success',
                'message': 'Job position updated successfully',
                'data': JobDescriptionSerializer(job).data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'status': 'error',
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error updating company job: {str(e)}", exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to update job position',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_company_job_applications(request, jobId):
    """Get job applications for a specific job (Company only)"""
    try:
        company_user = request.user
        job = get_object_or_404(JobDescription, id=jobId, company_user=company_user)

        applications = JobApplication.objects.filter(job=job).order_by('-applied_at')
        serializer = JobApplicationSerializer(applications, many=True, context={'request': request})

        return Response({
            'status': 'success',
            'data': serializer.data,
            'total': applications.count(),
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch applications',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_company_application_status(request, id):
    """Update application status (Company only)"""
    try:
        # request.user is a CompanyUser instance when authenticated via CompanyUserTokenAuthentication
        company_user = request.user
        company = company_user.company
        # Users can only update applications for their own jobs
        company_user = request.user
        application = get_object_or_404(JobApplication, id=id, job__company_user=company_user)

        new_status = request.data.get('status')

        if not new_status:
            return Response({
                'status': 'error',
                'message': 'Status is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        valid_statuses = ['pending', 'reviewed', 'shortlisted', 'rejected']
        if new_status not in valid_statuses:
            return Response({
                'status': 'error',
                'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }, status=status.HTTP_400_BAD_REQUEST)

        application.status = new_status
        application.save()

        serializer = JobApplicationSerializer(application, context={'request': request})

        return Response({
            'status': 'success',
            'message': 'Application status updated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update application status',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def process_job_applicants(request, jobId):
    """Run AI pipeline on all unprocessed JobApplications for a job.

    Fetches every JobApplication where cv_record is null, downloads the CV
    file, runs parse → summarize → enrich → qualify, creates a linked CVRecord,
    and auto-schedules interviews for INTERVIEW decisions.
    """
    try:
        company_user = request.user
        company = company_user.company
        job = get_object_or_404(JobDescription, id=jobId, company_user=company_user)

        # Verify interview settings are complete (same guard as process_cvs)
        interview_settings = RecruiterInterviewSettings.objects.filter(
            company_user=company_user, job=job
        ).first()
        missing_fields = []
        if not interview_settings:
            missing_fields.append('Interview settings not configured')
        else:
            if not interview_settings.schedule_from_date:
                missing_fields.append('Start date')
            if not interview_settings.schedule_to_date:
                missing_fields.append('End date')
            if not interview_settings.start_time:
                missing_fields.append('Start time')
            if not interview_settings.end_time:
                missing_fields.append('End time')
            if not (interview_settings.time_slots_json and len(interview_settings.time_slots_json) > 0):
                missing_fields.append('Time slots')

        if missing_fields:
            return Response({
                'status': 'error',
                'message': f'Interview settings are incomplete for job "{job.title}". Missing: {", ".join(missing_fields)}. '
                           f'Please complete interview settings in Settings > Interview Settings before processing.',
                'missing_fields': missing_fields,
            }, status=status.HTTP_400_BAD_REQUEST)

        # Fetch unprocessed applications (no linked cv_record yet)
        unprocessed = list(
            JobApplication.objects.filter(job=job, cv_record__isnull=True).order_by('applied_at')
        )

        if not unprocessed:
            return Response({
                'status': 'success',
                'message': 'No new applications to process. All applicants have already been analysed.',
                'processed': 0,
                'results': [],
            }, status=status.HTTP_200_OK)

        agents = _make_agents(company)
        cv_agent = agents['cv_agent']
        sum_agent = agents['sum_agent']
        enrich_agent = agents['enrich_agent']
        qualify_agent = agents['qualify_agent']
        interview_agent = agents.get('interview_agent')
        django_repo = agents['django_repo']

        # Build keyword list from job
        job_kw_list = None
        job_description_text = job.description or ''
        if job.keywords_json:
            try:
                stored = json.loads(job.keywords_json)
                extracted = stored.get('keywords', [])
                if extracted:
                    job_kw_list = extracted
            except (json.JSONDecodeError, TypeError):
                pass

        # Qualification thresholds
        interview_threshold = None
        hold_threshold = None
        try:
            qual_settings = RecruiterQualificationSettings.objects.filter(company_user=company_user).first()
            if qual_settings and qual_settings.use_custom_thresholds:
                interview_threshold = qual_settings.interview_threshold
                hold_threshold = qual_settings.hold_threshold
        except Exception as e:
            logger.warning(f'Error fetching qualification settings: {e}')

        # Email / interview defaults
        auto_interview_type = 'ONLINE'
        if interview_settings and getattr(interview_settings, 'default_interview_type', None):
            auto_interview_type = interview_settings.default_interview_type
        try:
            email_settings_obj = RecruiterEmailSettings.objects.get(company_user=company_user)
            email_settings = {
                'followup_delay_hours': email_settings_obj.followup_delay_hours,
                'reminder_hours_before': email_settings_obj.reminder_hours_before,
                'max_followup_emails': email_settings_obj.max_followup_emails,
                'min_hours_between_followups': email_settings_obj.min_hours_between_followups,
            }
        except RecruiterEmailSettings.DoesNotExist:
            email_settings = None

        results = []
        for idx, app in enumerate(unprocessed):
            if not app.cv_file:
                results.append({
                    'application_id': app.id,
                    'applicant': f'{app.first_name} {app.last_name}'.strip(),
                    'skipped': True,
                    'reason': 'No CV file uploaded',
                })
                continue

            if idx > 0:
                time.sleep(0.5)

            temp_path = None
            try:
                suffix = Path(app.cv_file.name).suffix or '.pdf'
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    app.cv_file.open('rb')
                    tmp.write(app.cv_file.read())
                    app.cv_file.close()
                    temp_path = Path(tmp.name)

                parsed = cv_agent.parse_file(str(temp_path))
                record_id = django_repo.store_parsed(app.cv_file_name or app.cv_file.name, parsed)

                # Link CVRecord to company_user, job, and the JobApplication
                if record_id:
                    try:
                        cv_record = CVRecord.objects.get(id=record_id)
                        cv_record.company_user = company_user
                        cv_record.job_description = job
                        cv_record.job_application = app
                        cv_record.save()
                    except CVRecord.DoesNotExist:
                        pass

                summary = sum_agent.summarize(parsed, job_kw_list)
                if not isinstance(summary, dict):
                    summary = summary[0] if isinstance(summary, list) and summary else {}

                enriched = enrich_agent.enrich(parsed, summary)
                if not isinstance(enriched, dict):
                    enriched = enriched[0] if isinstance(enriched, list) and enriched else {}

                qualified = qualify_agent.qualify(parsed, summary, job_kw_list, enriched, interview_threshold, hold_threshold)
                if not isinstance(qualified, dict):
                    qualified = qualified[0] if isinstance(qualified, list) and qualified else {}

                # Persist full analysis back to CVRecord
                if record_id:
                    try:
                        cv_record = CVRecord.objects.get(id=record_id)
                        cv_record.insights_json = json.dumps(summary)
                        cv_record.enriched_json = json.dumps(enriched)
                        cv_record.qualification_json = json.dumps(qualified)
                        cv_record.role_fit_score = summary.get('role_fit_score') if isinstance(summary, dict) else None
                        cv_record.qualification_decision = qualified.get('decision') if isinstance(qualified, dict) else None
                        cv_record.qualification_confidence = qualified.get('confidence_score') if isinstance(qualified, dict) else None
                        cv_record.qualification_priority = qualified.get('priority') if isinstance(qualified, dict) else None
                        cv_record.rank = idx + 1
                        cv_record.save()
                    except CVRecord.DoesNotExist:
                        pass

                interview_scheduled = False
                qual_decision = qualified.get('decision', '') if isinstance(qualified, dict) else ''
                if qual_decision == 'INTERVIEW' and interview_agent and app.email:
                    candidate_name = f'{app.first_name} {app.last_name}'.strip() or 'Candidate'
                    import re
                    job_role = re.sub(r'[\r\n\t\s]+', ' ', (job_description_text.split('\n')[0][:100])).strip() if job_description_text else job.title
                    try:
                        interview_result = interview_agent.schedule_interview(
                            candidate_name=candidate_name,
                            candidate_email=app.email,
                            job_role=job_role,
                            interview_type=auto_interview_type,
                            candidate_phone=app.phone,
                            cv_record_id=record_id,
                            recruiter_id=None,
                            company_user_id=company_user.id,
                            email_settings=email_settings,
                            custom_slots=None,
                        )
                        interview_scheduled = interview_result.get('invitation_sent', False)
                    except Exception as ie:
                        logger.error(f'Interview scheduling failed for {app.email}: {ie}')

                results.append({
                    'application_id': app.id,
                    'applicant': f'{app.first_name} {app.last_name}'.strip(),
                    'record_id': record_id,
                    'decision': qual_decision,
                    'role_fit_score': summary.get('role_fit_score') if isinstance(summary, dict) else None,
                    'interview_scheduled': interview_scheduled,
                    'skipped': False,
                })

            except Exception as exc:
                logger.error(f'Error processing application {app.id}: {exc}', exc_info=True)
                results.append({
                    'application_id': app.id,
                    'applicant': f'{app.first_name} {app.last_name}'.strip(),
                    'skipped': True,
                    'reason': str(exc),
                })
            finally:
                if temp_path:
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass

        processed_count = sum(1 for r in results if not r.get('skipped'))
        return Response({
            'status': 'success',
            'message': f'Processed {processed_count} of {len(unprocessed)} application(s).',
            'processed': processed_count,
            'total': len(unprocessed),
            'results': results,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f'Error processing job applicants: {e}', exc_info=True)
        return Response({
            'status': 'error',
            'message': 'Failed to process applicants',
            'error': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
