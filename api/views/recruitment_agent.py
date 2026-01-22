"""
Recruitment Agent API Views for Company Users
"""
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Q

from recruitment_agent.agents.cv_parser import CVParserAgent
from recruitment_agent.agents.summarization import SummarizationAgent
from recruitment_agent.agents.lead_enrichment import LeadResearchEnrichmentAgent
from recruitment_agent.agents.lead_qualification import LeadQualificationAgent
from recruitment_agent.agents.job_description_parser import JobDescriptionParserAgent
from recruitment_agent.agents.interview_scheduling import InterviewSchedulingAgent
from recruitment_agent.core import GroqClient
from recruitment_agent.log_service import LogService
from recruitment_agent.django_repository import DjangoRepository
from recruitment_agent.models import Interview, CVRecord, JobDescription, RecruiterEmailSettings, RecruiterInterviewSettings, RecruiterQualificationSettings

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import CompanyUser

logger = logging.getLogger(__name__)

# Initialize agents (singleton pattern for efficiency)
_agents_cache = None

def get_agents():
    """Get initialized agents (singleton pattern)"""
    global _agents_cache
    
    if _agents_cache is None:
        log_service = LogService()
        groq_client = GroqClient()
        django_repo = DjangoRepository()
        
        _agents_cache = {
            'log_service': log_service,
            'groq_client': groq_client,
            'cv_agent': CVParserAgent(groq_client=groq_client, log_service=log_service),
            'sum_agent': SummarizationAgent(groq_client=groq_client, log_service=log_service),
            'enrich_agent': LeadResearchEnrichmentAgent(log_service=log_service, sql_repository=django_repo),
            'qualify_agent': LeadQualificationAgent(log_service=log_service, sql_repository=django_repo),
            'job_desc_agent': JobDescriptionParserAgent(groq_client=groq_client, log_service=log_service),
            'interview_agent': InterviewSchedulingAgent(log_service=log_service),
            'django_repo': django_repo,
        }
    
    return _agents_cache


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def process_cvs(request):
    """Process CV files and return ranked results"""
    try:
        company_user = request.user
        company = company_user.company
        
        agents = get_agents()
        cv_agent = agents['cv_agent']
        sum_agent = agents['sum_agent']
        enrich_agent = agents['enrich_agent']
        qualify_agent = agents['qualify_agent']
        job_desc_agent = agents['job_desc_agent']
        django_repo = agents['django_repo']
        log_service = agents['log_service']
        
        # Get files from request
        files = request.FILES.getlist('files')
        if not files or len(files) == 0:
            return Response({
                'status': 'error',
                'message': 'No files uploaded. Please upload at least one CV.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get job description and keywords
        job_description_id = request.data.get('job_description_id')
        job_description_text = request.data.get('job_description_text', '').strip()
        job_keywords = request.data.get('job_keywords', '').strip()
        top_n = request.data.get('top_n')
        top_n = int(top_n) if top_n else None
        parse_only = request.data.get('parse_only', False)
        
        # Initialize job_kw_list
        job_kw_list = None
        job_desc = None
        
        # If job description ID is provided, fetch it
        if job_description_id:
            try:
                job_desc = JobDescription.objects.filter(
                    id=job_description_id,
                    company_user=company_user
                ).first()
                if job_desc:
                    job_description_text = job_desc.description
                    if job_desc.keywords_json:
                        try:
                            stored_keywords = json.loads(job_desc.keywords_json)
                            extracted_keywords = stored_keywords.get("keywords", [])
                            if extracted_keywords:
                                job_kw_list = extracted_keywords
                        except (json.JSONDecodeError, TypeError):
                            pass
            except Exception as e:
                logger.error(f"Error fetching job description: {e}")
        
        # Parse keywords from text if not already loaded
        if not job_kw_list and job_description_text:
            try:
                job_desc_parsed = job_desc_agent.parse_text(job_description_text)
                # Handle case where parse_text might return a list instead of dict
                if isinstance(job_desc_parsed, list):
                    # If it's a list, try to extract keywords from first item or use empty list
                    if job_desc_parsed and isinstance(job_desc_parsed[0], dict):
                        extracted_keywords = job_desc_parsed[0].get("keywords", [])
                    else:
                        extracted_keywords = []
                else:
                    extracted_keywords = job_desc_parsed.get("keywords", []) if isinstance(job_desc_parsed, dict) else []
                if extracted_keywords:
                    job_kw_list = extracted_keywords
            except Exception as exc:
                log_service.log_error("job_description_text_parsing_failed", {"error": str(exc)})
        
        # Use manual keywords if provided
        if not job_kw_list and job_keywords:
            job_kw_list = [kw.strip() for kw in job_keywords.split(",") if kw.strip()]
        
        # Process CV files
        parsed_results = []
        temp_paths = []
        
        try:
            for uploaded_file in files:
                suffix = Path(uploaded_file.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    for chunk in uploaded_file.chunks():
                        tmp.write(chunk)
                    temp_path = Path(tmp.name)
                    temp_paths.append(temp_path)
                
                parsed = cv_agent.parse_file(str(temp_path))
                
                record_id = django_repo.store_parsed(uploaded_file.name, parsed) if django_repo else None
                
                # Link to company_user and job description if provided
                if record_id:
                    try:
                        cv_record = CVRecord.objects.get(id=record_id)
                        cv_record.company_user = company_user
                        if job_desc:
                            cv_record.job_description = job_desc
                        cv_record.save()
                    except CVRecord.DoesNotExist:
                        pass
                
                parsed_results.append({
                    'file_name': uploaded_file.name,
                    'parsed': parsed,
                    'record_id': record_id,
                })
            
            # Clean up temp files
            for temp_path in temp_paths:
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            
            # If parse_only, return parsed results
            if parse_only:
                return Response({
                    'status': 'success',
                    'results': parsed_results,
                    'parse_only': True
                })
            
            # Get qualification settings for company user (fetch once, use for all CVs)
            interview_threshold = None
            hold_threshold = None
            try:
                qual_settings = RecruiterQualificationSettings.objects.filter(company_user=company_user).first()
                if qual_settings and qual_settings.use_custom_thresholds:
                    interview_threshold = qual_settings.interview_threshold
                    hold_threshold = qual_settings.hold_threshold
            except Exception as e:
                logger.warning(f"Error fetching qualification settings: {e}")
            
            # Summarize, enrich, and qualify
            all_results = []
            for result in parsed_results:
                parsed = result['parsed']
                
                # Summarize
                summary = sum_agent.summarize(parsed, job_kw_list)
                # Ensure summary is a dict
                if not isinstance(summary, dict):
                    summary = summary[0] if isinstance(summary, list) and len(summary) > 0 else {}
                
                # Enrich
                enriched = enrich_agent.enrich(parsed, summary)
                # Ensure enriched is a dict
                if not isinstance(enriched, dict):
                    enriched = enriched[0] if isinstance(enriched, list) and len(enriched) > 0 else {}
                
                # Qualify - correct parameter order: (parsed_cv, candidate_insights, job_keywords, enriched_data, interview_threshold, hold_threshold)
                qualified = qualify_agent.qualify(parsed, summary, job_kw_list, enriched, interview_threshold, hold_threshold)
                # Ensure qualified is a dict
                if not isinstance(qualified, dict):
                    qualified = qualified[0] if isinstance(qualified, list) and len(qualified) > 0 else {}
                
                all_results.append({
                    'file_name': result['file_name'],
                    'record_id': result['record_id'],
                    'parsed': parsed,
                    'summary': summary,
                    'enriched': enriched,
                    'qualified': qualified,
                })
            
            # Rank results - use role_fit_score from summary, not qualified
            ranked = sorted(
                all_results,
                key=lambda x: x['summary'].get('role_fit_score', 0) if isinstance(x.get('summary'), dict) else 0,
                reverse=True
            )
            
            # Apply top_n limit
            if top_n:
                ranked = ranked[:top_n]
            
            # Get interview agent for auto-scheduling
            interview_agent = agents.get('interview_agent')
            
            # Get company user email settings for interview defaults
            try:
                email_settings_obj = RecruiterEmailSettings.objects.get(company_user=company_user)
                email_settings = {
                    'followup_delay_hours': email_settings_obj.followup_delay_hours,
                    'reminder_hours_before': email_settings_obj.reminder_hours_before,
                    'max_followup_emails': email_settings_obj.max_followup_emails,
                    'min_hours_between_followups': email_settings_obj.min_hours_between_followups,
                }
                followup_delay = email_settings_obj.followup_delay_hours
                reminder_hours = email_settings_obj.reminder_hours_before
                max_followups = email_settings_obj.max_followup_emails
                min_between = email_settings_obj.min_hours_between_followups
            except RecruiterEmailSettings.DoesNotExist:
                email_settings = None
                followup_delay = 48
                reminder_hours = 24
                max_followups = 3
                min_between = 24
            
            # Update CV records with qualification data and auto-schedule interviews
            for idx, result in enumerate(ranked):
                if result['record_id']:
                    try:
                        cv_record = CVRecord.objects.get(id=result['record_id'])
                        cv_record.insights_json = json.dumps(result['summary'])
                        cv_record.enriched_json = json.dumps(result['enriched'])
                        cv_record.qualification_json = json.dumps(result['qualified'])
                        # role_fit_score comes from summary, not qualified
                        cv_record.role_fit_score = result['summary'].get('role_fit_score') if isinstance(result.get('summary'), dict) else None
                        cv_record.qualification_decision = result['qualified'].get('decision') if isinstance(result.get('qualified'), dict) else None
                        # qualified has confidence_score, not confidence
                        cv_record.qualification_confidence = result['qualified'].get('confidence_score') if isinstance(result.get('qualified'), dict) else None
                        cv_record.qualification_priority = result['qualified'].get('priority') if isinstance(result.get('qualified'), dict) else None
                        cv_record.rank = idx + 1
                        cv_record.save()
                    except CVRecord.DoesNotExist:
                        pass
                
                # Auto-schedule interview if decision is INTERVIEW
                qual_decision = result.get('qualified', {}).get('decision', '') if isinstance(result.get('qualified'), dict) else ''
                if qual_decision == "INTERVIEW" and interview_agent:
                    parsed_cv = result.get('parsed', {})
                    candidate_name = parsed_cv.get('name', 'Candidate') if isinstance(parsed_cv, dict) else 'Candidate'
                    candidate_email = parsed_cv.get('email') if isinstance(parsed_cv, dict) else None
                    candidate_phone = parsed_cv.get('phone') if isinstance(parsed_cv, dict) else None
                    
                    # Get job role from job description or use default
                    job_role = "Position"
                    if job_description_text:
                        import re
                        job_role = job_description_text.split('\n')[0][:100] if job_description_text else "Position"
                        job_role = re.sub(r'[\r\n\t]+', ' ', job_role)
                        job_role = re.sub(r'\s+', ' ', job_role).strip()
                    elif job_kw_list and len(job_kw_list) > 0:
                        job_role = job_kw_list[0]
                    
                    if candidate_email:
                        logger.info(f"Auto-scheduling interview for approved candidate: {candidate_name} ({candidate_email})")
                        try:
                            interview_result = interview_agent.schedule_interview(
                                candidate_name=candidate_name,
                                candidate_email=candidate_email,
                                job_role=job_role,
                                interview_type='ONLINE',  # Default to ONLINE
                                candidate_phone=candidate_phone,
                                cv_record_id=result.get('record_id'),
                                recruiter_id=None,  # Not using Django User
                                company_user_id=company_user.id,
                                email_settings=email_settings,
                                custom_slots=None,
                            )
                            
                            if interview_result.get('invitation_sent'):
                                logger.info(f"Interview invitation sent successfully for {candidate_email}")
                                result['interview_scheduled'] = True
                                result['interview_id'] = interview_result.get('interview_id')
                            else:
                                logger.warning(f"Interview created but email failed for {candidate_email}")
                                result['interview_scheduled'] = False
                                result['interview_error'] = interview_result.get('message', 'Unknown error')
                        except Exception as interview_exc:
                            logger.error(f"Failed to schedule interview for {candidate_email}: {str(interview_exc)}")
                            log_service.log_error("auto_interview_scheduling_error", {
                                "record_id": result.get('record_id'),
                                "candidate_email": candidate_email,
                                "error": str(interview_exc),
                            })
                            result['interview_scheduled'] = False
                            result['interview_error'] = str(interview_exc)
                    else:
                        logger.warning(f"Skipping interview scheduling - no email found for {candidate_name}")
                        result['interview_scheduled'] = False
                        result['interview_error'] = "No email address found"
            
            return Response({
                'status': 'success',
                'results': ranked,
                'total': len(ranked)
            })
            
        except Exception as e:
            # Clean up temp files on error
            for temp_path in temp_paths:
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            
            logger.error(f"CV processing error: {e}")
            return Response({
                'status': 'error',
                'message': f'Processing failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    except Exception as e:
        logger.error(f"CV processing error: {e}")
        return Response({
            'status': 'error',
            'message': f'Processing failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_job_descriptions(request):
    """List all job descriptions for the company user"""
    try:
        company_user = request.user
        
        job_descriptions = JobDescription.objects.filter(
            company_user=company_user
        ).order_by('-created_at')
        
        job_list = []
        for jd in job_descriptions:
            job_list.append({
                'id': jd.id,
                'title': jd.title,
                'description': jd.description,
                'location': jd.location,
                'department': jd.department,
                'type': jd.type,
                'requirements': jd.requirements,
                'is_active': jd.is_active,
                'keywords_json': jd.keywords_json,
                'created_at': jd.created_at.isoformat() if jd.created_at else None,
                'updated_at': jd.updated_at.isoformat() if jd.updated_at else None,
            })
        
        return Response({
            'status': 'success',
            'data': job_list
        })
    
    except Exception as e:
        logger.error(f"Error listing job descriptions: {e}")
        return Response({
            'status': 'error',
            'message': f'Failed to list job descriptions: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_job_description(request):
    """Create a new job description"""
    try:
        company_user = request.user
        company = company_user.company
        
        agents = get_agents()
        job_desc_agent = agents['job_desc_agent']
        log_service = agents['log_service']
        
        title = request.data.get('title', '').strip()
        description = request.data.get('description', '').strip()
        parse_keywords = request.data.get('parse_keywords', True)
        location = request.data.get('location', '').strip() or None
        department = request.data.get('department', '').strip() or None
        job_type = request.data.get('type', 'Full-time').strip()
        requirements = request.data.get('requirements', '').strip() or None
        
        if not title or not description:
            return Response({
                'status': 'error',
                'message': 'Missing required fields: title, description'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse keywords if requested
        keywords_json = None
        if parse_keywords:
            try:
                parsed = job_desc_agent.parse_text(description)
                keywords_json = json.dumps(parsed)
            except Exception as exc:
                log_service.log_error("job_description_keyword_parsing_failed", {"error": str(exc)})
        
        job_desc = JobDescription.objects.create(
            title=title,
            description=description,
            keywords_json=keywords_json,
            company=company,
            company_user=company_user,
            is_active=True,
            location=location,
            department=department,
            type=job_type,
            requirements=requirements,
        )
        
        return Response({
            'status': 'success',
            'message': 'Job description created successfully',
            'data': {
                'id': job_desc.id,
                'title': job_desc.title,
                'description': job_desc.description,
                'is_active': job_desc.is_active,
                'created_at': job_desc.created_at.isoformat(),
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(f"Error creating job description: {e}")
        return Response({
            'status': 'error',
            'message': f'Creation failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_job_description(request, job_description_id):
    """Update an existing job description"""
    try:
        company_user = request.user
        
        job_desc = JobDescription.objects.filter(
            id=job_description_id,
            company_user=company_user
        ).first()
        
        if not job_desc:
            return Response({
                'status': 'error',
                'message': 'Job description not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        agents = get_agents()
        job_desc_agent = agents['job_desc_agent']
        log_service = agents['log_service']
        
        title = request.data.get('title', '').strip()
        description = request.data.get('description', '').strip()
        is_active = request.data.get('is_active', job_desc.is_active)
        parse_keywords = request.data.get('parse_keywords', False)
        location = request.data.get('location', '').strip() or None
        department = request.data.get('department', '').strip() or None
        job_type = request.data.get('type', job_desc.type).strip()
        requirements = request.data.get('requirements', '').strip() or None
        
        if title:
            job_desc.title = title
        if description:
            job_desc.description = description
        
        job_desc.is_active = is_active
        if location is not None:
            job_desc.location = location
        if department is not None:
            job_desc.department = department
        if job_type:
            job_desc.type = job_type
        if requirements is not None:
            job_desc.requirements = requirements
        
        # Parse keywords if requested
        if parse_keywords and description:
            try:
                parsed = job_desc_agent.parse_text(description)
                job_desc.keywords_json = json.dumps(parsed)
            except Exception as exc:
                log_service.log_error("job_description_keyword_parsing_failed", {"error": str(exc)})
        
        job_desc.save()
        
        return Response({
            'status': 'success',
            'message': 'Job description updated successfully',
            'data': {
                'id': job_desc.id,
                'title': job_desc.title,
                'description': job_desc.description,
                'is_active': job_desc.is_active,
                'updated_at': job_desc.updated_at.isoformat(),
            }
        })
    
    except Exception as e:
        logger.error(f"Error updating job description: {e}")
        return Response({
            'status': 'error',
            'message': f'Update failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_job_description(request, job_description_id):
    """Delete a job description"""
    try:
        company_user = request.user
        
        job_desc = JobDescription.objects.filter(
            id=job_description_id,
            company_user=company_user
        ).first()
        
        if not job_desc:
            return Response({
                'status': 'error',
                'message': 'Job description not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        job_desc.delete()
        
        return Response({
            'status': 'success',
            'message': 'Job description deleted successfully'
        })
    
    except Exception as e:
        logger.error(f"Error deleting job description: {e}")
        return Response({
            'status': 'error',
            'message': f'Delete failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_interviews(request):
    """List all interviews for the company user"""
    try:
        company_user = request.user
        
        status_filter = request.query_params.get('status')
        interviews = Interview.objects.filter(company_user=company_user)
        
        if status_filter:
            interviews = interviews.filter(status=status_filter)
        
        interviews = interviews.order_by('-created_at')[:100]  # Limit to 100 most recent
        
        interview_list = []
        for interview in interviews:
            interview_list.append({
                'id': interview.id,
                'candidate_name': interview.candidate_name,
                'candidate_email': interview.candidate_email,
                'candidate_phone': interview.candidate_phone,
                'job_role': interview.job_role,
                'interview_type': interview.interview_type,
                'status': interview.status,
                'scheduled_datetime': interview.scheduled_datetime.isoformat() if interview.scheduled_datetime else None,
                'selected_slot': interview.selected_slot,
                'confirmation_token': interview.confirmation_token,
                'created_at': interview.created_at.isoformat() if interview.created_at else None,
            })
        
        return Response({
            'status': 'success',
            'data': interview_list
        })
    
    except Exception as e:
        logger.error(f"Error listing interviews: {e}")
        return Response({
            'status': 'error',
            'message': f'Failed to list interviews: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def schedule_interview(request):
    """Schedule an interview for an approved candidate"""
    try:
        company_user = request.user
        
        agents = get_agents()
        interview_agent = agents['interview_agent']
        log_service = agents['log_service']
        
        candidate_name = request.data.get('candidate_name', '').strip()
        candidate_email = request.data.get('candidate_email', '').strip()
        job_role = request.data.get('job_role', '').strip()
        interview_type = request.data.get('interview_type', 'ONLINE').strip().upper()
        candidate_phone = request.data.get('candidate_phone', '').strip() or None
        cv_record_id = request.data.get('cv_record_id')
        cv_record_id = int(cv_record_id) if cv_record_id else None
        custom_slots = request.data.get('custom_slots')
        
        # Validate required fields
        if not candidate_name or not candidate_email or not job_role:
            return Response({
                'status': 'error',
                'message': 'Missing required fields: candidate_name, candidate_email, job_role'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate interview type
        if interview_type not in ['ONLINE', 'ONSITE']:
            return Response({
                'status': 'error',
                'message': 'Invalid interview_type. Must be ONLINE or ONSITE'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify CV record belongs to company user if provided
        if cv_record_id:
            cv_record = CVRecord.objects.filter(
                id=cv_record_id,
                job_description__company_user=company_user
            ).first()
            if not cv_record:
                return Response({
                    'status': 'error',
                    'message': 'CV record not found or access denied'
                }, status=status.HTTP_404_NOT_FOUND)
        
        # Get company user email settings for interview defaults
        try:
            email_settings_obj = RecruiterEmailSettings.objects.get(company_user=company_user)
            email_settings = {
                'followup_delay_hours': email_settings_obj.followup_delay_hours,
                'reminder_hours_before': email_settings_obj.reminder_hours_before,
                'max_followup_emails': email_settings_obj.max_followup_emails,
                'min_hours_between_followups': email_settings_obj.min_hours_between_followups,
            }
            followup_delay = email_settings_obj.followup_delay_hours
            reminder_hours = email_settings_obj.reminder_hours_before
            max_followups = email_settings_obj.max_followup_emails
            min_between = email_settings_obj.min_hours_between_followups
        except RecruiterEmailSettings.DoesNotExist:
            # Use defaults
            email_settings = None
            followup_delay = 48
            reminder_hours = 24
            max_followups = 3
            min_between = 24
        
        # Schedule interview - pass company_user_id and email settings
        result = interview_agent.schedule_interview(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            job_role=job_role,
            interview_type=interview_type,
            candidate_phone=candidate_phone,
            cv_record_id=cv_record_id,
            recruiter_id=None,  # Not using Django User
            company_user_id=company_user.id,
            email_settings=email_settings,
            custom_slots=custom_slots,
        )
        
        # Update interview with company_user and email settings if not already set
        # schedule_interview should already have set company_user, but update email settings to be sure
        if result.get('interview_id'):
            try:
                interview = Interview.objects.get(id=result['interview_id'])
                # Update company_user if not already set
                if not interview.company_user:
                    interview.company_user = company_user
                # Ensure company user email settings are applied
                interview.followup_delay_hours = followup_delay
                interview.reminder_hours_before = reminder_hours
                interview.max_followup_emails = max_followups
                interview.min_hours_between_followups = min_between
                interview.save()
            except Interview.DoesNotExist:
                pass
        
        return Response({
            'status': 'success' if result.get('invitation_sent') else ('error' if result.get('interview_id') else 'error'),
            'message': result.get('message', 'Interview scheduled'),
            'data': result
        })
    
    except Exception as e:
        logger.error(f"Error scheduling interview: {e}")
        return Response({
            'status': 'error',
            'message': f'Scheduling failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_interview_details(request, interview_id):
    """Get interview details"""
    try:
        company_user = request.user
        
        interview = Interview.objects.filter(
            id=interview_id,
            company_user=company_user
        ).first()
        
        if not interview:
            return Response({
                'status': 'error',
                'message': 'Interview not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        agents = get_agents()
        interview_agent = agents['interview_agent']
        
        details = interview_agent.get_interview_details(interview_id)
        
        if not details:
            return Response({
                'status': 'error',
                'message': 'Failed to get interview details'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'status': 'success',
            'data': details
        })
    
    except Exception as e:
        logger.error(f"Error getting interview details: {e}")
        return Response({
            'status': 'error',
            'message': f'Failed to get interview details: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_cv_records(request):
    """List CV records for the company user"""
    try:
        company_user = request.user
        
        job_id = request.query_params.get('job_id')
        decision = request.query_params.get('decision')  # INTERVIEW, HOLD, REJECT
        
        cv_records = CVRecord.objects.filter(
            job_description__company_user=company_user
        )
        
        if job_id:
            cv_records = cv_records.filter(job_description_id=job_id)
        
        if decision:
            cv_records = cv_records.filter(qualification_decision=decision)
        
        cv_records = cv_records.order_by('-rank', '-created_at')
        
        records_list = []
        for cv in cv_records:
            parsed_data = json.loads(cv.parsed_json) if cv.parsed_json else {}
            insights_data = json.loads(cv.insights_json) if cv.insights_json else {}
            enriched_data = json.loads(cv.enriched_json) if cv.enriched_json else {}
            qualification_data = json.loads(cv.qualification_json) if cv.qualification_json else {}
            
            records_list.append({
                'id': cv.id,
                'file_name': cv.file_name,
                'role_fit_score': cv.role_fit_score,
                'rank': cv.rank,
                'qualification_decision': cv.qualification_decision,
                'qualification_confidence': cv.qualification_confidence,
                'qualification_priority': cv.qualification_priority,
                'job_description_id': cv.job_description_id,
                'job_description_title': cv.job_description.title if cv.job_description else None,
                'parsed': parsed_data,
                'insights': insights_data,
                'enriched': enriched_data,
                'qualified': qualification_data,
                'created_at': cv.created_at.isoformat() if cv.created_at else None,
            })
        
        return Response({
            'status': 'success',
            'data': records_list
        })
    
    except Exception as e:
        logger.error(f"Error listing CV records: {e}")
        return Response({
            'status': 'error',
            'message': f'Failed to list CV records: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def email_settings(request):
    """Get or update email settings for company user"""
    try:
        company_user = request.user
        
        if request.method == 'GET':
            settings, created = RecruiterEmailSettings.objects.get_or_create(
                company_user=company_user,
                defaults={
                    'followup_delay_hours': 48,
                    'min_hours_between_followups': 24,
                    'max_followup_emails': 3,
                    'reminder_hours_before': 24,
                    'auto_send_followups': True,
                    'auto_send_reminders': True,
                }
            )
            
            return Response({
                'status': 'success',
                'data': {
                    'followup_delay_hours': settings.followup_delay_hours,
                    'min_hours_between_followups': settings.min_hours_between_followups,
                    'max_followup_emails': settings.max_followup_emails,
                    'reminder_hours_before': settings.reminder_hours_before,
                    'auto_send_followups': settings.auto_send_followups,
                    'auto_send_reminders': settings.auto_send_reminders,
                }
            })
        
        else:  # POST
            settings, created = RecruiterEmailSettings.objects.get_or_create(
                company_user=company_user
            )
            
            if 'followup_delay_hours' in request.data:
                settings.followup_delay_hours = float(request.data['followup_delay_hours'])
            if 'min_hours_between_followups' in request.data:
                settings.min_hours_between_followups = float(request.data['min_hours_between_followups'])
            if 'max_followup_emails' in request.data:
                settings.max_followup_emails = int(request.data['max_followup_emails'])
            if 'reminder_hours_before' in request.data:
                settings.reminder_hours_before = float(request.data['reminder_hours_before'])
            if 'auto_send_followups' in request.data:
                settings.auto_send_followups = bool(request.data['auto_send_followups'])
            if 'auto_send_reminders' in request.data:
                settings.auto_send_reminders = bool(request.data['auto_send_reminders'])
            
            settings.save()
            
            return Response({
                'status': 'success',
                'message': 'Email settings updated successfully',
                'data': {
                    'followup_delay_hours': settings.followup_delay_hours,
                    'min_hours_between_followups': settings.min_hours_between_followups,
                    'max_followup_emails': settings.max_followup_emails,
                    'reminder_hours_before': settings.reminder_hours_before,
                    'auto_send_followups': settings.auto_send_followups,
                    'auto_send_reminders': settings.auto_send_reminders,
                }
            })
    
    except Exception as e:
        logger.error(f"Error with email settings: {e}")
        return Response({
            'status': 'error',
            'message': f'Failed to process email settings: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def interview_settings(request):
    """Get or update interview settings for company user"""
    try:
        company_user = request.user
        
        if request.method == 'GET':
            settings, created = RecruiterInterviewSettings.objects.get_or_create(
                company_user=company_user,
                defaults={
                    'start_time': '09:00',
                    'end_time': '17:00',
                    'interview_time_gap': 30,
                    'time_slots_json': [],
                }
            )
            
            return Response({
                'status': 'success',
                'data': {
                    'schedule_from_date': settings.schedule_from_date.isoformat() if settings.schedule_from_date else None,
                    'schedule_to_date': settings.schedule_to_date.isoformat() if settings.schedule_to_date else None,
                    'start_time': settings.start_time.strftime('%H:%M') if settings.start_time else '09:00',
                    'end_time': settings.end_time.strftime('%H:%M') if settings.end_time else '17:00',
                    'interview_time_gap': settings.interview_time_gap,
                    'time_slots_json': settings.time_slots_json,
                }
            })
        
        else:  # POST
            settings, created = RecruiterInterviewSettings.objects.get_or_create(
                company_user=company_user
            )
            
            update_availability_only = request.data.get('update_availability', False)
            
            if 'schedule_from_date' in request.data:
                from datetime import datetime
                date_str = request.data['schedule_from_date']
                if date_str:
                    settings.schedule_from_date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
                else:
                    settings.schedule_from_date = None
            if 'schedule_to_date' in request.data:
                from datetime import datetime
                date_str = request.data['schedule_to_date']
                if date_str:
                    settings.schedule_to_date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
                else:
                    settings.schedule_to_date = None
            if 'start_time' in request.data:
                from datetime import datetime
                time_str = request.data['start_time']
                settings.start_time = datetime.strptime(time_str, '%H:%M').time()
            if 'end_time' in request.data:
                from datetime import datetime
                time_str = request.data['end_time']
                settings.end_time = datetime.strptime(time_str, '%H:%M').time()
            if 'interview_time_gap' in request.data:
                gap_value = int(request.data['interview_time_gap'])
                if gap_value < 15:
                    return Response({
                        'status': 'error',
                        'message': 'interview_time_gap must be at least 15 minutes.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                if gap_value > 120:
                    return Response({
                        'status': 'error',
                        'message': 'interview_time_gap cannot exceed 120 minutes.'
                    }, status=status.HTTP_400_BAD_REQUEST)
                settings.interview_time_gap = gap_value
            
            # Validate date range
            if settings.schedule_from_date and settings.schedule_to_date:
                if settings.schedule_from_date > settings.schedule_to_date:
                    return Response({
                        'status': 'error',
                        'message': 'schedule_from_date cannot be after schedule_to_date.'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate time range
            if settings.start_time and settings.end_time:
                if settings.start_time >= settings.end_time:
                    return Response({
                        'status': 'error',
                        'message': 'start_time must be before end_time.'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Handle time slots
            # Check if we're only updating availability (not generating new slots)
            if update_availability_only and 'time_slots_json' in request.data:
                # Only update availability for existing slots
                availability_data = request.data['time_slots_json']
                if settings.time_slots_json:
                    availability_map = {item['datetime']: item.get('available', True) for item in availability_data}
                    for slot in settings.time_slots_json:
                        if slot.get('datetime') in availability_map:
                            slot['available'] = availability_map[slot['datetime']]
                    settings.time_slots_json = settings.time_slots_json
                else:
                    return Response({
                        'status': 'error',
                        'message': 'No time slots found. Please generate time slots first.'
                    }, status=status.HTTP_400_BAD_REQUEST)
            # Generate time slots automatically if date range is provided (only if not updating availability)
            elif settings.schedule_from_date and settings.schedule_to_date:
                # Generate time slots if date range is provided and slots don't exist
                from datetime import timedelta, time as dt_time
                
                time_slots = []
                current_date = settings.schedule_from_date
                
                # Parse start and end times
                if isinstance(settings.start_time, dt_time):
                    start_hour = settings.start_time.hour
                    start_min = settings.start_time.minute
                else:
                    time_parts = str(settings.start_time).split(':')
                    start_hour = int(time_parts[0])
                    start_min = int(time_parts[1])
                
                if isinstance(settings.end_time, dt_time):
                    end_hour = settings.end_time.hour
                    end_min = settings.end_time.minute
                else:
                    time_parts = str(settings.end_time).split(':')
                    end_hour = int(time_parts[0])
                    end_min = int(time_parts[1])
                
                start_minutes = start_hour * 60 + start_min
                end_minutes = end_hour * 60 + end_min
                
                # Preserve existing availability if slots already exist
                existing_availability = {}
                if settings.time_slots_json:
                    existing_availability = {slot.get('datetime'): slot.get('available', True) for slot in settings.time_slots_json}
                
                # Generate slots for each date
                while current_date <= settings.schedule_to_date:
                    current_minutes = start_minutes
                    while current_minutes < end_minutes:
                        hours = current_minutes // 60
                        minutes = current_minutes % 60
                        time_str = f"{hours:02d}:{minutes:02d}"
                        datetime_str = f"{current_date.isoformat()}T{time_str}"
                        
                        # Preserve availability status for existing slots
                        available = True
                        if datetime_str in existing_availability:
                            available = existing_availability[datetime_str]
                        
                        time_slots.append({
                            'date': current_date.isoformat(),
                            'time': time_str,
                            'datetime': datetime_str,
                            'available': available
                        })
                        
                        current_minutes += settings.interview_time_gap
                    
                    current_date += timedelta(days=1)
                
                settings.time_slots_json = time_slots
            
            settings.save()
            
            return Response({
                'status': 'success',
                'message': 'Interview settings updated successfully',
                'data': {
                    'schedule_from_date': settings.schedule_from_date.isoformat() if settings.schedule_from_date else None,
                    'schedule_to_date': settings.schedule_to_date.isoformat() if settings.schedule_to_date else None,
                    'start_time': settings.start_time.strftime('%H:%M') if settings.start_time else '09:00',
                    'end_time': settings.end_time.strftime('%H:%M') if settings.end_time else '17:00',
                    'interview_time_gap': settings.interview_time_gap,
                    'time_slots_json': settings.time_slots_json,
                }
            })
    
    except Exception as e:
        logger.error(f"Error with interview settings: {e}")
        return Response({
            'status': 'error',
            'message': f'Failed to process interview settings: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def qualification_settings(request):
    """Get or update qualification/decision threshold settings for company user"""
    try:
        company_user = request.user
        
        if request.method == 'GET':
            settings, created = RecruiterQualificationSettings.objects.get_or_create(
                company_user=company_user,
                defaults={
                    'interview_threshold': 65,
                    'hold_threshold': 45,
                    'use_custom_thresholds': False,
                }
            )
            
            return Response({
                'status': 'success',
                'data': {
                    'interview_threshold': settings.interview_threshold,
                    'hold_threshold': settings.hold_threshold,
                    'use_custom_thresholds': settings.use_custom_thresholds,
                }
            })
        
        else:  # POST
            settings, created = RecruiterQualificationSettings.objects.get_or_create(
                company_user=company_user
            )
            
            if 'interview_threshold' in request.data:
                threshold = int(request.data['interview_threshold'])
                if threshold < 0 or threshold > 100:
                    return Response({
                        'status': 'error',
                        'message': 'interview_threshold must be between 0 and 100'
                    }, status=status.HTTP_400_BAD_REQUEST)
                settings.interview_threshold = threshold
            
            if 'hold_threshold' in request.data:
                threshold = int(request.data['hold_threshold'])
                if threshold < 0 or threshold > 100:
                    return Response({
                        'status': 'error',
                        'message': 'hold_threshold must be between 0 and 100'
                    }, status=status.HTTP_400_BAD_REQUEST)
                settings.hold_threshold = threshold
            
            if 'use_custom_thresholds' in request.data:
                settings.use_custom_thresholds = bool(request.data['use_custom_thresholds'])
            
            # Validate thresholds
            if settings.interview_threshold <= settings.hold_threshold:
                return Response({
                    'status': 'error',
                    'message': 'interview_threshold must be greater than hold_threshold'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            settings.save()
            
            return Response({
                'status': 'success',
                'message': 'Qualification settings updated successfully',
                'data': {
                    'interview_threshold': settings.interview_threshold,
                    'hold_threshold': settings.hold_threshold,
                    'use_custom_thresholds': settings.use_custom_thresholds,
                }
            })
    
    except Exception as e:
        logger.error(f"Error with qualification settings: {e}")
        return Response({
            'status': 'error',
            'message': f'Failed to process qualification settings: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

