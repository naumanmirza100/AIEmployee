import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from core.models import UserProfile

from recruitment_agent.agents.cv_parser import CVParserAgent
from recruitment_agent.agents.summarization import SummarizationAgent
from recruitment_agent.agents.lead_enrichment import LeadResearchEnrichmentAgent
from recruitment_agent.agents.lead_qualification import LeadQualificationAgent
from recruitment_agent.agents.job_description_parser import JobDescriptionParserAgent
from recruitment_agent.agents.interview_scheduling import InterviewSchedulingAgent
from recruitment_agent.core import GroqClient
from recruitment_agent.log_service import LogService
from recruitment_agent.django_repository import DjangoRepository
from recruitment_agent.models import Interview, CVRecord, JobDescription

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize agents (singleton pattern for efficiency)
_log_service = None
_groq_client = None
_cv_agent = None
_sum_agent = None
_enrich_agent = None
_qualify_agent = None
_job_desc_agent = None
_interview_agent = None
_django_repo = None

def get_agents():
    """Get initialized agents (singleton pattern)"""
    global _log_service, _groq_client, _cv_agent, _sum_agent, _enrich_agent, _qualify_agent, _job_desc_agent, _interview_agent, _django_repo
    
    if _log_service is None:
        _log_service = LogService()
    
    if _groq_client is None:
        _groq_client = GroqClient()
    
    if _cv_agent is None:
        _cv_agent = CVParserAgent(groq_client=_groq_client, log_service=_log_service)
    
    if _sum_agent is None:
        _sum_agent = SummarizationAgent(groq_client=_groq_client, log_service=_log_service)
    
    if _django_repo is None:
        _django_repo = DjangoRepository()
    
    if _enrich_agent is None:
        _enrich_agent = LeadResearchEnrichmentAgent(log_service=_log_service, sql_repository=_django_repo)
    
    if _qualify_agent is None:
        _qualify_agent = LeadQualificationAgent(log_service=_log_service, sql_repository=_django_repo)
    
    if _job_desc_agent is None:
        _job_desc_agent = JobDescriptionParserAgent(groq_client=_groq_client, log_service=_log_service)
    
    if _interview_agent is None:
        _interview_agent = InterviewSchedulingAgent(log_service=_log_service)
    
    return {
        'log_service': _log_service,
        'groq_client': _groq_client,
        'cv_agent': _cv_agent,
        'sum_agent': _sum_agent,
        'enrich_agent': _enrich_agent,
        'qualify_agent': _qualify_agent,
        'job_desc_agent': _job_desc_agent,
        'interview_agent': _interview_agent,
        'django_repo': _django_repo,
    }


@login_required
def recruitment_dashboard(request):
    """Main recruitment agent dashboard"""
    # Ensure user has a profile
    from core.models import UserProfile
    UserProfile.objects.get_or_create(user=request.user)
    
    # Check if user has recruitment_agent role (either in profile or selected role for admin)
    is_recruitment_agent = request.user.profile.is_recruitment_agent()
    
    # For admin users, also check selected role in session
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'recruitment_agent':
            is_recruitment_agent = True
    
    if not is_recruitment_agent:
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.error(request, "You must be a Recruitment Agent to access this dashboard.")
        return redirect('dashboard')
    
    # Get job descriptions
    job_descriptions = JobDescription.objects.all().order_by('-created_at')[:20]
    
    # Get recent CV records (for display)
    recent_cvs = CVRecord.objects.all().order_by('-created_at')[:10]
    
    # Get filter job description ID from request
    filter_job_id = request.GET.get('filter_job_id', '').strip()
    filter_job = None
    if filter_job_id:
        try:
            filter_job = JobDescription.objects.get(id=filter_job_id)
        except (JobDescription.DoesNotExist, ValueError):
            filter_job = None
    
    # Get candidates by status
    # Selected for Interview = CV records with qualification_decision = 'INTERVIEW'
    selected_for_interview_qs = CVRecord.objects.filter(
        qualification_decision='INTERVIEW'
    )
    
    # Apply job filter if selected
    if filter_job:
        selected_for_interview_qs = selected_for_interview_qs.filter(job_description=filter_job)
    
    selected_for_interview_qs = selected_for_interview_qs.order_by('-created_at')[:50]
    
    # Parse candidate info from JSON for each CV
    selected_for_interview = []
    for cv in selected_for_interview_qs:
        candidate_info = {'cv_record': cv, 'name': cv.file_name, 'email': None}
        if cv.parsed_json:
            try:
                parsed_data = json.loads(cv.parsed_json)
                candidate_info['name'] = parsed_data.get('name') or cv.file_name
                candidate_info['email'] = parsed_data.get('email')
            except (json.JSONDecodeError, TypeError):
                pass
        selected_for_interview.append(candidate_info)
    
    # Interview Email Sent = Interviews with invitation_sent_at not null
    interview_email_sent_qs = Interview.objects.filter(
        invitation_sent_at__isnull=False
    )
    
    # Apply job filter - filter through cv_record__job_description for accurate filtering
    if filter_job:
        # Filter interviews through CVRecord's job_description foreign key
        interview_email_sent_qs = interview_email_sent_qs.filter(
            cv_record__job_description=filter_job
        )
    
    interview_email_sent = interview_email_sent_qs.order_by('-invitation_sent_at')[:50]
    
    # Get all interviews grouped by status
    interviews_qs_pending = Interview.objects.filter(status='PENDING')
    interviews_qs_scheduled = Interview.objects.filter(status='SCHEDULED')
    interviews_qs_completed = Interview.objects.filter(status='COMPLETED')
    
    # Apply job filter to interviews through cv_record__job_description
    if filter_job:
        interviews_qs_pending = interviews_qs_pending.filter(cv_record__job_description=filter_job)
        interviews_qs_scheduled = interviews_qs_scheduled.filter(cv_record__job_description=filter_job)
        interviews_qs_completed = interviews_qs_completed.filter(cv_record__job_description=filter_job)
    
    interviews_by_status = {
        'PENDING': interviews_qs_pending.order_by('-created_at')[:50],
        'SCHEDULED': interviews_qs_scheduled.order_by('-scheduled_datetime')[:50],
        'COMPLETED': interviews_qs_completed.order_by('-updated_at')[:20],
    }
    
    return render(request, 'recruitment_agent/dashboard.html', {
        'job_descriptions': job_descriptions,
        'recent_cvs': recent_cvs,
        'selected_for_interview': selected_for_interview,
        'interview_email_sent': interview_email_sent,
        'interviews_by_status': interviews_by_status,
        'filter_job': filter_job,
        'filter_job_id': filter_job_id,
    })


@login_required
@require_http_methods(["POST"])
def process_cvs(request):
    """Process CV files and return ranked results"""
    # Ensure user has a profile
    from core.models import UserProfile
    UserProfile.objects.get_or_create(user=request.user)
    
    # Check if user has recruitment_agent role (either in profile or selected role for admin)
    is_recruitment_agent = request.user.profile.is_recruitment_agent()
    
    # For admin users, also check selected role in session
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'recruitment_agent':
            is_recruitment_agent = True
    
    if not is_recruitment_agent:
        return JsonResponse({"error": "Unauthorized. Recruitment Agent role required."}, status=403)
    
    agents = get_agents()
    cv_agent = agents['cv_agent']
    sum_agent = agents['sum_agent']
    enrich_agent = agents['enrich_agent']
    qualify_agent = agents['qualify_agent']
    job_desc_agent = agents['job_desc_agent']
    django_repo = agents['django_repo']
    log_service = agents['log_service']
    
    try:
        # Get files from request
        files = request.FILES.getlist('files')
        if not files or len(files) == 0:
            return JsonResponse({"error": "No files uploaded. Please upload at least one CV."}, status=400)
        
        # Get job description and keywords
        job_description_id = request.POST.get('job_description_id')
        job_description_file = request.FILES.get('job_description')
        job_description_text = request.POST.get('job_description_text', '').strip()
        job_keywords = request.POST.get('job_keywords', '').strip()
        
        # Initialize job_kw_list - will be set from stored keywords or parsed
        job_kw_list = None
        
        # If job description ID is provided, fetch the job description text and keywords
        if job_description_id and not job_description_text:
            try:
                job_desc = JobDescription.objects.get(id=job_description_id)
                job_description_text = job_desc.description
                
                # Use stored keywords if available (from when job was saved)
                if job_desc.keywords_json:
                    try:
                        stored_keywords = json.loads(job_desc.keywords_json)
                        extracted_keywords = stored_keywords.get("keywords", [])
                        if extracted_keywords:
                            job_kw_list = extracted_keywords
                            log_service.log_event("using_stored_keywords", {
                                "job_description_id": job_description_id,
                                "keywords_count": len(extracted_keywords)
                            })
                    except (json.JSONDecodeError, TypeError):
                        # If stored keywords are invalid, will parse again below
                        pass
            except JobDescription.DoesNotExist:
                pass
        top_n = request.POST.get('top_n')
        top_n = int(top_n) if top_n else None
        parse_only = request.POST.get('parse_only', 'false').lower() == 'true'
        
        # Extract keywords from job description if provided
        # Note: job_kw_list may already be set from stored keywords above
        
        # Priority 1: Parse from uploaded file (only if keywords not already loaded)
        if not job_kw_list and job_description_file:
            try:
                suffix = Path(job_description_file.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    for chunk in job_description_file.chunks():
                        tmp.write(chunk)
                    temp_path = Path(tmp.name)
                
                job_desc_parsed = job_desc_agent.parse_file(str(temp_path))
                extracted_keywords = job_desc_parsed.get("keywords", [])
                
                if extracted_keywords:
                    job_kw_list = extracted_keywords
                else:
                    log_service.log_error("job_description_parsing_failed", {"path": job_description_file.name, "error": "No keywords extracted"})
                
                # Clean up temp file
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            except Exception as exc:
                log_service.log_error("job_description_parsing_failed", {"path": job_description_file.name, "error": str(exc)})
        
        # Priority 2: Parse from text input (only if keywords not already loaded from stored data)
        if not job_kw_list and job_description_text:
            try:
                job_desc_parsed = job_desc_agent.parse_text(job_description_text)
                extracted_keywords = job_desc_parsed.get("keywords", [])
                
                if extracted_keywords:
                    job_kw_list = extracted_keywords
                    log_service.log_event("keywords_parsed_from_text", {
                        "keywords_count": len(extracted_keywords),
                        "source": "text_input"
                    })
                else:
                    log_service.log_error("job_description_text_parsing_failed", {"error": "No keywords extracted from text"})
            except Exception as exc:
                log_service.log_error("job_description_text_parsing_failed", {"error": str(exc)})
        
        # Priority 3: Use manual keywords
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
                
                # Debug: Print parsing result (can be removed in production)
                print("\n" + "="*60)
                print(f"📄 PARSING RESULT for: {uploaded_file.name}")
                print("="*60)
                print(json.dumps(parsed, indent=2, ensure_ascii=False))
                print("="*60 + "\n")
                
                record_id = django_repo.store_parsed(uploaded_file.name, parsed) if django_repo else None
                # Link to job description if provided
                if job_description_id and record_id:
                    try:
                        job_desc = JobDescription.objects.get(id=job_description_id)
                        cv_record = CVRecord.objects.get(id=record_id)
                        cv_record.job_description = job_desc
                        cv_record.save()
                    except (JobDescription.DoesNotExist, CVRecord.DoesNotExist):
                        pass
                parsed_results.append({"file": uploaded_file.name, "data": parsed, "record_id": record_id})
            
            if parse_only:
                return JsonResponse(parsed_results, safe=False)
            
            # Summarize
            insights = []
            for item in parsed_results:
                insight = sum_agent.summarize(item["data"], job_keywords=job_kw_list)
                insights.append({
                    "file": item["file"],
                    "parsed": item["data"],
                    "insights": insight,
                    "record_id": item.get("record_id"),
                })
            
            insights_sorted = sorted(
                insights,
                key=lambda r: r["insights"].get("role_fit_score")
                if r["insights"].get("role_fit_score") is not None
                else -1,
                reverse=True,
            )
            for rank, item in enumerate(insights_sorted, start=1):
                item["rank"] = rank
                if django_repo and item.get("record_id"):
                    django_repo.store_insights(item["record_id"], item["insights"], rank=rank)
            
            # Enrichment
            enriched_items = []
            for item in insights_sorted:
                parsed_with_id = {**item["parsed"], "record_id": item.get("record_id")}
                insights_with_id = {**item["insights"], "record_id": item.get("record_id")}
                enrichment = enrich_agent.enrich(parsed_with_id, insights_with_id)
                enriched_items.append({**item, "enrichment": enrichment})
            
            # Qualification
            qualified = []
            for item in enriched_items:
                insights_with_id = {**item["insights"], "record_id": item.get("record_id")}
                enriched_data = item.get("enrichment")
                qual = qualify_agent.qualify(
                    item["parsed"], insights_with_id, job_keywords=job_kw_list, enriched_data=enriched_data
                )
                qualified.append({**item, "qualification": qual})
            
            # Rank by SKILLS MATCH
            if not job_kw_list or len(job_kw_list) == 0:
                def fit_score_sort_key(r: Dict[str, Any]) -> float:
                    insights = r.get("insights", {})
                    return insights.get("role_fit_score") if insights.get("role_fit_score") is not None else 0.0
                qualified_sorted = sorted(qualified, key=fit_score_sort_key, reverse=True)
            else:
                def skills_based_sort_key(r: Dict[str, Any]) -> Tuple[float, int, int, int, float]:
                    qual = r.get("qualification", {})
                    insights = r.get("insights", {})
                    matched = qual.get("matched_skills") or []
                    inferred = qual.get("inferred_skills") or []
                    missing = qual.get("missing_skills") or []
                    confidence = qual.get("confidence_score") if qual.get("confidence_score") is not None else 0
                    role_fit = insights.get("role_fit_score") if insights.get("role_fit_score") is not None else 0.0
                    
                    matched_count = len(matched) if isinstance(matched, list) else 0
                    missing_count = len(missing) if isinstance(missing, list) else 0
                    total_keywords = matched_count + missing_count
                    
                    match_ratio = matched_count / max(total_keywords, 1) if total_keywords > 0 else 0.0
                    inferred_count = len(inferred) if isinstance(inferred, list) else 0
                    
                    return (match_ratio, matched_count, inferred_count, confidence, role_fit)
                
                qualified_sorted = sorted(qualified, key=skills_based_sort_key, reverse=True)
            
            # Store qualification and auto-schedule interviews for INTERVIEW decisions
            interview_agent = agents['interview_agent']
            for rank, item in enumerate(qualified_sorted, start=1):
                item["rank"] = rank
                if django_repo and item.get("record_id"):
                    django_repo.store_qualification(item["record_id"], item["qualification"], rank=rank)
                
                # Auto-schedule interview if decision is INTERVIEW
                qual_decision = item.get("qualification", {}).get("decision", "")
                if qual_decision == "INTERVIEW":
                    parsed_cv = item.get("parsed", {})
                    candidate_name = parsed_cv.get("name", "Candidate")
                    candidate_email = parsed_cv.get("email")
                    candidate_phone = parsed_cv.get("phone")
                    
                    # Get job role from job description or use default
                    job_role = job_kw_list[0] if job_kw_list and len(job_kw_list) > 0 else "Position"
                    if job_description_text:
                        # Try to extract job title from job description (clean it)
                        job_role = job_description_text.split('\n')[0][:100] if job_description_text else "Position"
                        # Remove newlines and clean whitespace
                        import re
                        job_role = re.sub(r'[\r\n\t]+', ' ', job_role)
                        job_role = re.sub(r'\s+', ' ', job_role).strip()
                    
                    if candidate_email:
                        print("\n" + "="*60)
                        print("🎯 AUTO-SCHEDULING INTERVIEW FOR APPROVED CANDIDATE")
                        print("="*60)
                        print(f"✓ Candidate: {candidate_name}")
                        print(f"✓ Email: {candidate_email}")
                        print(f"✓ Decision: {qual_decision}")
                        print(f"✓ Job Role: {job_role}")
                        
                        try:
                            interview_result = interview_agent.schedule_interview(
                                candidate_name=candidate_name,
                                candidate_email=candidate_email,
                                job_role=job_role,
                                interview_type='ONLINE',  # Default to ONLINE
                                candidate_phone=candidate_phone,
                                cv_record_id=item.get("record_id"),
                                recruiter_id=request.user.id,
                            )
                            
                            if interview_result.get("invitation_sent"):
                                print(f"✅ Interview invitation sent successfully!")
                                item["interview_scheduled"] = True
                                item["interview_id"] = interview_result.get("interview_id")
                            else:
                                print(f"⚠️  Interview created but email failed")
                                item["interview_scheduled"] = False
                                item["interview_error"] = interview_result.get("message", "Unknown error")
                        except Exception as interview_exc:
                            print(f"❌ ERROR: Failed to schedule interview: {interview_exc}")
                            log_service.log_error("auto_interview_scheduling_error", {
                                "record_id": item.get("record_id"),
                                "candidate_email": candidate_email,
                                "error": str(interview_exc),
                            })
                            item["interview_scheduled"] = False
                            item["interview_error"] = str(interview_exc)
                    else:
                        print(f"\n⚠️  Skipping interview scheduling - no email found for {candidate_name}")
                        item["interview_scheduled"] = False
                        item["interview_error"] = "No email address found"
            
            if top_n is not None:
                qualified_sorted = qualified_sorted[:top_n]
            
            return JsonResponse(qualified_sorted, safe=False)
            
        finally:
            # Clean up temp files
            for path in temp_paths:
                try:
                    path.unlink()
                except Exception:
                    pass
                    
    except Exception as e:
        log_service.log_error("cv_processing_error", {"error": str(e)})
        return JsonResponse({"error": f"Processing failed: {str(e)}"}, status=500)


@login_required
@require_http_methods(["POST"])
def schedule_interview(request):
    """
    Schedule an interview for an approved candidate.
    Expected POST data:
    - candidate_name (required)
    - candidate_email (required)
    - job_role (required)
    - interview_type (optional, default: ONLINE)
    - candidate_phone (optional)
    - cv_record_id (optional)
    - custom_slots (optional, JSON array)
    """
    # Check if user has recruitment_agent role
    is_recruitment_agent = request.user.profile.is_recruitment_agent()
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'recruitment_agent':
            is_recruitment_agent = True
    
    if not is_recruitment_agent:
        return JsonResponse({"error": "Unauthorized. Recruitment Agent role required."}, status=403)
    
    agents = get_agents()
    interview_agent = agents['interview_agent']
    log_service = agents['log_service']
    
    try:
        candidate_name = request.POST.get('candidate_name', '').strip()
        candidate_email = request.POST.get('candidate_email', '').strip()
        job_role = request.POST.get('job_role', '').strip()
        interview_type = request.POST.get('interview_type', 'ONLINE').strip().upper()
        candidate_phone = request.POST.get('candidate_phone', '').strip() or None
        cv_record_id = request.POST.get('cv_record_id')
        cv_record_id = int(cv_record_id) if cv_record_id else None
        
        # Parse custom slots if provided
        custom_slots = None
        custom_slots_json = request.POST.get('custom_slots')
        if custom_slots_json:
            try:
                custom_slots = json.loads(custom_slots_json)
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON in custom_slots"}, status=400)
        
        # Validate required fields
        if not candidate_name or not candidate_email or not job_role:
            return JsonResponse({"error": "Missing required fields: candidate_name, candidate_email, job_role"}, status=400)
        
        # Validate interview type
        if interview_type not in ['ONLINE', 'ONSITE']:
            return JsonResponse({"error": "Invalid interview_type. Must be ONLINE or ONSITE"}, status=400)
        
        # Schedule interview
        result = interview_agent.schedule_interview(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            job_role=job_role,
            interview_type=interview_type,
            candidate_phone=candidate_phone,
            cv_record_id=cv_record_id,
            recruiter_id=request.user.id,
            custom_slots=custom_slots,
        )
        
        return JsonResponse(result)
        
    except Exception as e:
        log_service.log_error("interview_scheduling_error", {"error": str(e)})
        return JsonResponse({"error": f"Scheduling failed: {str(e)}"}, status=500)


@require_http_methods(["GET", "POST"])
@csrf_exempt  # Allow external access for candidate slot selection
def confirm_interview_slot(request):
    """
    Confirm a selected interview slot (can be called by candidate via email link or API).
    Expected POST data:
    - interview_id (required)
    - selected_slot_datetime (required, ISO format)
    """
    agents = get_agents()
    interview_agent = agents['interview_agent']
    log_service = agents['log_service']
    
    try:
        interview_id = request.POST.get('interview_id') or request.GET.get('interview_id')
        selected_slot_datetime = request.POST.get('selected_slot_datetime') or request.GET.get('selected_slot_datetime')
        
        if not interview_id or not selected_slot_datetime:
            return JsonResponse({"error": "Missing required fields: interview_id, selected_slot_datetime"}, status=400)
        
        interview_id = int(interview_id)
        result = interview_agent.confirm_slot(interview_id, selected_slot_datetime)
        
        if result.get('success'):
            return JsonResponse(result)
        else:
            return JsonResponse(result, status=400)
            
    except ValueError:
        return JsonResponse({"error": "Invalid interview_id"}, status=400)
    except Exception as e:
        log_service.log_error("slot_confirmation_error", {"error": str(e)})
        return JsonResponse({"error": f"Confirmation failed: {str(e)}"}, status=500)


@login_required
@require_http_methods(["GET", "POST"])
def get_interview_details(request, interview_id):
    """Get interview details"""
    # Check if user has recruitment_agent role
    is_recruitment_agent = request.user.profile.is_recruitment_agent()
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'recruitment_agent':
            is_recruitment_agent = True
    
    if not is_recruitment_agent:
        return JsonResponse({"error": "Unauthorized. Recruitment Agent role required."}, status=403)
    
    agents = get_agents()
    interview_agent = agents['interview_agent']
    
    try:
        interview_id = int(interview_id)
        details = interview_agent.get_interview_details(interview_id)
        
        if details:
            return JsonResponse(details)
        else:
            return JsonResponse({"error": "Interview not found"}, status=404)
            
    except ValueError:
        return JsonResponse({"error": "Invalid interview_id"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# Follow-up reminders are now sent AUTOMATICALLY ONLY via management command
# Manual sending has been disabled to ensure consistent automatic processing
# Run: python manage.py send_interview_reminders (via cron/scheduler)

@csrf_exempt
@require_http_methods(["GET", "POST"])
def auto_check_interview_followups(request):
    """
    Automatic endpoint to check and send follow-up emails.
    This can be called by cron jobs, scheduled tasks, or automatically.
    No authentication required for automated systems (can be secured with API key if needed).
    """
    print("\n" + "="*70)
    print("🔧 MANUAL FOLLOW-UP CHECK TRIGGERED")
    print("="*70)
    try:
        from recruitment_agent.tasks import check_and_send_followup_emails
        from recruitment_agent.models import Interview
        
        # Show current pending interviews
        pending = Interview.objects.filter(status='PENDING', invitation_sent_at__isnull=False)
        print(f"📋 Found {pending.count()} PENDING interview(s)")
        for interview in pending:
            print(f"   • Interview #{interview.id}: {interview.candidate_name} - Invited: {interview.invitation_sent_at}")
        
        # Run the automatic check
        stats = check_and_send_followup_emails()
        
        print("="*70 + "\n")
        
        return JsonResponse({
            "success": True,
            "message": "Follow-up email check completed",
            "stats": stats,
            "pending_interviews_count": pending.count()
        })
    except Exception as e:
        import traceback
        print(f"❌ ERROR: {str(e)}")
        print(traceback.format_exc())
        print("="*70 + "\n")
        return JsonResponse({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }, status=500)


@login_required
@require_http_methods(["GET", "POST"])
def recruiter_email_settings(request):
    """
    Get or update recruiter email timing preferences.
    GET: Returns current settings
    POST: Updates settings
    """
    from recruitment_agent.models import RecruiterEmailSettings
    
    # Check if user has recruitment_agent role
    is_recruitment_agent = request.user.profile.is_recruitment_agent()
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'recruitment_agent':
            is_recruitment_agent = True
    
    if not is_recruitment_agent:
        logger.warning(f"❌ Unauthorized email settings access attempt by user: {request.user.username}")
        return JsonResponse({"error": "Unauthorized. Recruitment Agent role required."}, status=403)
    
    if request.method == 'GET':
        # Get current settings or return defaults
        print("\n" + "="*70)
        print("📧 EMAIL SETTINGS API CALLED (GET)")
        print("="*70)
        print(f"👤 User: {request.user.username} (ID: {request.user.id})")
        logger.info(f"Email settings GET request by user: {request.user.username}")
        
        try:
            settings = request.user.recruiter_email_settings
            print("✅ Found existing email settings:")
            print(f"   • Follow-up delay: {settings.followup_delay_hours} hours")
            print(f"   • Min hours between follow-ups: {settings.min_hours_between_followups} hours")
            print(f"   • Max follow-up emails: {settings.max_followup_emails}")
            print(f"   • Reminder hours before: {settings.reminder_hours_before} hours")
            print(f"   • Auto send follow-ups: {settings.auto_send_followups}")
            print(f"   • Auto send reminders: {settings.auto_send_reminders}")
            print("="*70 + "\n")
            
            logger.info(f"Retrieved email settings for {request.user.username}: "
                       f"followup_delay={settings.followup_delay_hours}h, "
                       f"min_between={settings.min_hours_between_followups}h, "
                       f"max_followups={settings.max_followup_emails}, "
                       f"reminder_before={settings.reminder_hours_before}h")
            
            return JsonResponse({
                "success": True,
                "settings": {
                    "followup_delay_hours": settings.followup_delay_hours,
                    "min_hours_between_followups": settings.min_hours_between_followups,
                    "max_followup_emails": settings.max_followup_emails,
                    "reminder_hours_before": settings.reminder_hours_before,
                    "auto_send_followups": settings.auto_send_followups,
                    "auto_send_reminders": settings.auto_send_reminders,
                }
            })
        except RecruiterEmailSettings.DoesNotExist:
            print("ℹ️  No custom settings found, returning defaults:")
            print(f"   • Follow-up delay: 48 hours")
            print(f"   • Min hours between follow-ups: 24 hours")
            print(f"   • Max follow-up emails: 3")
            print(f"   • Reminder hours before: 24 hours")
            print(f"   • Auto send follow-ups: True")
            print(f"   • Auto send reminders: True")
            print("="*70 + "\n")
            
            logger.info(f"Returned default email settings for {request.user.username} (no custom settings)")
            
            # Return defaults
            return JsonResponse({
                "success": True,
                "settings": {
                    "followup_delay_hours": 48,
                    "min_hours_between_followups": 24,
                    "max_followup_emails": 3,
                    "reminder_hours_before": 24,
                    "auto_send_followups": True,
                    "auto_send_reminders": True,
                }
            })
    
    elif request.method == 'POST':
        # Update settings
        print("\n" + "="*70)
        print("📧 EMAIL SETTINGS API CALLED (POST - UPDATE)")
        print("="*70)
        print(f"👤 User: {request.user.username} (ID: {request.user.id})")
        logger.info(f"Email settings POST request by user: {request.user.username}")
        
        try:
            data = json.loads(request.body) if request.body else {}
            
            # Get or create settings
            settings, created = RecruiterEmailSettings.objects.get_or_create(
                recruiter=request.user,
                defaults={
                    'followup_delay_hours': 48,
                    'min_hours_between_followups': 24,
                    'max_followup_emails': 3,
                    'reminder_hours_before': 24,
                    'auto_send_followups': True,
                    'auto_send_reminders': True,
                }
            )
            
            if created:
                print("✅ Created new email settings record")
            else:
                print("📝 Updating existing email settings:")
            
            # Store old values for comparison
            old_values = {
                'followup_delay_hours': settings.followup_delay_hours,
                'min_hours_between_followups': settings.min_hours_between_followups,
                'max_followup_emails': settings.max_followup_emails,
                'reminder_hours_before': settings.reminder_hours_before,
                'auto_send_followups': settings.auto_send_followups,
                'auto_send_reminders': settings.auto_send_reminders,
            }
            
            # Track what's being updated
            updates = []
            
            # Update fields if provided
            if 'followup_delay_hours' in data:
                new_value = float(data['followup_delay_hours'])
                if old_values['followup_delay_hours'] != new_value:
                    updates.append(f"followup_delay_hours: {old_values['followup_delay_hours']} → {new_value} hours")
                settings.followup_delay_hours = new_value
                
            if 'min_hours_between_followups' in data:
                new_value = float(data['min_hours_between_followups'])
                if old_values['min_hours_between_followups'] != new_value:
                    updates.append(f"min_hours_between_followups: {old_values['min_hours_between_followups']} → {new_value} hours")
                settings.min_hours_between_followups = new_value
                
            if 'max_followup_emails' in data:
                new_value = int(data['max_followup_emails'])
                if old_values['max_followup_emails'] != new_value:
                    updates.append(f"max_followup_emails: {old_values['max_followup_emails']} → {new_value}")
                settings.max_followup_emails = new_value
                
            if 'reminder_hours_before' in data:
                new_value = float(data['reminder_hours_before'])
                if old_values['reminder_hours_before'] != new_value:
                    updates.append(f"reminder_hours_before: {old_values['reminder_hours_before']} → {new_value} hours")
                settings.reminder_hours_before = new_value
                
            if 'auto_send_followups' in data:
                new_value = bool(data['auto_send_followups'])
                if old_values['auto_send_followups'] != new_value:
                    updates.append(f"auto_send_followups: {old_values['auto_send_followups']} → {new_value}")
                settings.auto_send_followups = new_value
                
            if 'auto_send_reminders' in data:
                new_value = bool(data['auto_send_reminders'])
                if old_values['auto_send_reminders'] != new_value:
                    updates.append(f"auto_send_reminders: {old_values['auto_send_reminders']} → {new_value}")
                settings.auto_send_reminders = new_value
            
            if updates:
                print("\n📋 Settings Changed:")
                for update in updates:
                    print(f"   • {update}")
            else:
                print("ℹ️  No changes detected (values unchanged)")
            
            settings.save()
            
            print("\n✅ Final Settings Saved:")
            print(f"   • Follow-up delay: {settings.followup_delay_hours} hours")
            print(f"   • Min hours between follow-ups: {settings.min_hours_between_followups} hours")
            print(f"   • Max follow-up emails: {settings.max_followup_emails}")
            print(f"   • Reminder hours before: {settings.reminder_hours_before} hours")
            print(f"   • Auto send follow-ups: {settings.auto_send_followups}")
            print(f"   • Auto send reminders: {settings.auto_send_reminders}")
            print("="*70 + "\n")
            
            logger.info(f"Email settings updated for {request.user.username}: {', '.join(updates) if updates else 'No changes'}")
            
            return JsonResponse({
                "success": True,
                "message": "Email settings updated successfully",
                "settings": {
                    "followup_delay_hours": settings.followup_delay_hours,
                    "min_hours_between_followups": settings.min_hours_between_followups,
                    "max_followup_emails": settings.max_followup_emails,
                    "reminder_hours_before": settings.reminder_hours_before,
                    "auto_send_followups": settings.auto_send_followups,
                    "auto_send_reminders": settings.auto_send_reminders,
                }
            })
            
        except Exception as e:
            print(f"\n❌ ERROR updating email settings: {str(e)}")
            print("="*70 + "\n")
            logger.error(f"Error updating email settings for {request.user.username}: {str(e)}", exc_info=True)
            return JsonResponse({
                "success": False,
                "error": str(e)
            }, status=500)


@login_required
@require_http_methods(["GET", "POST"])
def recruiter_interview_settings(request):
    """
    Get or update recruiter interview scheduling preferences.
    GET: Returns current settings
    POST: Updates settings
    """
    from recruitment_agent.models import RecruiterInterviewSettings
    from datetime import date, time
    
    # Check if user has recruitment_agent role
    is_recruitment_agent = request.user.profile.is_recruitment_agent()
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'recruitment_agent':
            is_recruitment_agent = True
    
    if not is_recruitment_agent:
        logger.warning(f"❌ Unauthorized interview settings access attempt by user: {request.user.username}")
        return JsonResponse({"error": "Unauthorized. Recruitment Agent role required."}, status=403)
    
    if request.method == 'GET':
        # Get current settings or return defaults
        print("\n" + "="*70)
        print("📅 INTERVIEW SETTINGS API CALLED (GET)")
        print("="*70)
        print(f"👤 User: {request.user.username} (ID: {request.user.id})")
        logger.info(f"Interview settings GET request by user: {request.user.username}")
        
        try:
            settings = request.user.recruiter_interview_settings
            print("✅ Found existing interview settings:")
            print(f"   • Schedule from date: {settings.schedule_from_date}")
            print(f"   • Schedule to date: {settings.schedule_to_date}")
            print(f"   • Start time: {settings.start_time}")
            print(f"   • End time: {settings.end_time}")
            print(f"   • Interviews per day: {settings.interviews_per_day}")
            print("="*70 + "\n")
            
            logger.info(f"Retrieved interview settings for {request.user.username}")
            
            return JsonResponse({
                "success": True,
                "settings": {
                    "schedule_from_date": settings.schedule_from_date.isoformat() if settings.schedule_from_date else None,
                    "schedule_to_date": settings.schedule_to_date.isoformat() if settings.schedule_to_date else None,
                    "start_time": settings.start_time.strftime('%H:%M') if settings.start_time else '09:00',
                    "end_time": settings.end_time.strftime('%H:%M') if settings.end_time else '17:00',
                    "interviews_per_day": settings.interviews_per_day,
                }
            })
        except RecruiterInterviewSettings.DoesNotExist:
            print("ℹ️  No custom settings found, returning defaults:")
            print(f"   • Schedule from date: None (starts from today)")
            print(f"   • Schedule to date: None (no end date)")
            print(f"   • Start time: 09:00")
            print(f"   • End time: 17:00")
            print(f"   • Interviews per day: 3")
            print("="*70 + "\n")
            
            logger.info(f"Returned default interview settings for {request.user.username} (no custom settings)")
            
            # Return defaults
            return JsonResponse({
                "success": True,
                "settings": {
                    "schedule_from_date": None,
                    "schedule_to_date": None,
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "interviews_per_day": 3,
                }
            })
    
    elif request.method == 'POST':
        # Update settings
        print("\n" + "="*70)
        print("📅 INTERVIEW SETTINGS API CALLED (POST - UPDATE)")
        print("="*70)
        print(f"👤 User: {request.user.username} (ID: {request.user.id})")
        logger.info(f"Interview settings POST request by user: {request.user.username}")
        
        try:
            data = json.loads(request.body) if request.body else {}
            
            # Get or create settings
            settings, created = RecruiterInterviewSettings.objects.get_or_create(
                recruiter=request.user,
                defaults={
                    'start_time': time(9, 0),  # 9 AM
                    'end_time': time(17, 0),  # 5 PM
                    'interviews_per_day': 3,
                }
            )
            
            if created:
                print("✅ Created new interview settings record")
            else:
                print("📝 Updating existing interview settings:")
            
            # Store old values for comparison
            old_values = {
                'schedule_from_date': settings.schedule_from_date,
                'schedule_to_date': settings.schedule_to_date,
                'start_time': settings.start_time,
                'end_time': settings.end_time,
                'interviews_per_day': settings.interviews_per_day,
            }
            
            # Track what's being updated
            updates = []
            
            # Update fields if provided
            if 'schedule_from_date' in data:
                new_value = None
                if data['schedule_from_date']:
                    try:
                        new_value = date.fromisoformat(data['schedule_from_date'])
                    except (ValueError, TypeError):
                        return JsonResponse({"error": "Invalid schedule_from_date format. Use YYYY-MM-DD."}, status=400)
                if old_values['schedule_from_date'] != new_value:
                    updates.append(f"schedule_from_date: {old_values['schedule_from_date']} → {new_value}")
                settings.schedule_from_date = new_value
                
            if 'schedule_to_date' in data:
                new_value = None
                if data['schedule_to_date']:
                    try:
                        new_value = date.fromisoformat(data['schedule_to_date'])
                    except (ValueError, TypeError):
                        return JsonResponse({"error": "Invalid schedule_to_date format. Use YYYY-MM-DD."}, status=400)
                if old_values['schedule_to_date'] != new_value:
                    updates.append(f"schedule_to_date: {old_values['schedule_to_date']} → {new_value}")
                settings.schedule_to_date = new_value
                
            if 'start_time' in data:
                try:
                    time_str = data['start_time']
                    if isinstance(time_str, str):
                        # Parse HH:MM format
                        hour, minute = map(int, time_str.split(':'))
                        new_value = time(hour, minute)
                    else:
                        return JsonResponse({"error": "Invalid start_time format. Use HH:MM."}, status=400)
                except (ValueError, TypeError, AttributeError):
                    return JsonResponse({"error": "Invalid start_time format. Use HH:MM."}, status=400)
                if old_values['start_time'] != new_value:
                    updates.append(f"start_time: {old_values['start_time']} → {new_value}")
                settings.start_time = new_value
                
            if 'end_time' in data:
                try:
                    time_str = data['end_time']
                    if isinstance(time_str, str):
                        # Parse HH:MM format
                        hour, minute = map(int, time_str.split(':'))
                        new_value = time(hour, minute)
                    else:
                        return JsonResponse({"error": "Invalid end_time format. Use HH:MM."}, status=400)
                except (ValueError, TypeError, AttributeError):
                    return JsonResponse({"error": "Invalid end_time format. Use HH:MM."}, status=400)
                if old_values['end_time'] != new_value:
                    updates.append(f"end_time: {old_values['end_time']} → {new_value}")
                settings.end_time = new_value
                
            if 'interviews_per_day' in data:
                new_value = int(data['interviews_per_day'])
                if new_value < 1:
                    return JsonResponse({"error": "interviews_per_day must be at least 1."}, status=400)
                if old_values['interviews_per_day'] != new_value:
                    updates.append(f"interviews_per_day: {old_values['interviews_per_day']} → {new_value}")
                settings.interviews_per_day = new_value
            
            # Validate date range
            if settings.schedule_from_date and settings.schedule_to_date:
                if settings.schedule_from_date > settings.schedule_to_date:
                    return JsonResponse({"error": "schedule_from_date cannot be after schedule_to_date."}, status=400)
            
            # Validate time range
            if settings.start_time >= settings.end_time:
                return JsonResponse({"error": "start_time must be before end_time."}, status=400)
            
            if updates:
                print("\n📋 Settings Changed:")
                for update in updates:
                    print(f"   • {update}")
            else:
                print("ℹ️  No changes detected (values unchanged)")
            
            settings.save()
            
            print("\n✅ Final Settings Saved:")
            print(f"   • Schedule from date: {settings.schedule_from_date}")
            print(f"   • Schedule to date: {settings.schedule_to_date}")
            print(f"   • Start time: {settings.start_time}")
            print(f"   • End time: {settings.end_time}")
            print(f"   • Interviews per day: {settings.interviews_per_day}")
            print("="*70 + "\n")
            
            logger.info(f"Interview settings updated for {request.user.username}: {', '.join(updates) if updates else 'No changes'}")
            
            return JsonResponse({
                "success": True,
                "message": "Interview settings updated successfully",
                "settings": {
                    "schedule_from_date": settings.schedule_from_date.isoformat() if settings.schedule_from_date else None,
                    "schedule_to_date": settings.schedule_to_date.isoformat() if settings.schedule_to_date else None,
                    "start_time": settings.start_time.strftime('%H:%M') if settings.start_time else '09:00',
                    "end_time": settings.end_time.strftime('%H:%M') if settings.end_time else '17:00',
                    "interviews_per_day": settings.interviews_per_day,
                }
            })
            
        except Exception as e:
            print(f"\n❌ ERROR updating interview settings: {str(e)}")
            print("="*70 + "\n")
            logger.error(f"Error updating interview settings for {request.user.username}: {str(e)}", exc_info=True)
            return JsonResponse({
                "success": False,
                "error": str(e)
            }, status=500)


@login_required
@require_http_methods(["GET"])
def list_interviews(request):
    """List all interviews with optional filtering"""
    # Check if user has recruitment_agent role
    is_recruitment_agent = request.user.profile.is_recruitment_agent()
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'recruitment_agent':
            is_recruitment_agent = True
    
    if not is_recruitment_agent:
        return JsonResponse({"error": "Unauthorized. Recruitment Agent role required."}, status=403)
    
    try:
        status_filter = request.GET.get('status')
        interviews = Interview.objects.all()
        
        if status_filter:
            interviews = interviews.filter(status=status_filter)
        
        interviews = interviews.order_by('-created_at')[:100]  # Limit to 100 most recent
        
        interview_list = []
        for interview in interviews:
            interview_list.append({
                'id': interview.id,
                'candidate_name': interview.candidate_name,
                'candidate_email': interview.candidate_email,
                'job_role': interview.job_role,
                'interview_type': interview.interview_type,
                'status': interview.status,
                'scheduled_datetime': interview.scheduled_datetime.isoformat() if interview.scheduled_datetime else None,
                'created_at': interview.created_at.isoformat(),
            })
        
        return JsonResponse({'interviews': interview_list}, safe=False)
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
@csrf_exempt
def get_available_slots_for_interview(request, token):
    """
    API endpoint to get available slots for an interview based on interview settings.
    Returns constraints and available slots dynamically.
    """
    from recruitment_agent.models import Interview, RecruiterInterviewSettings
    from django.utils import timezone
    from datetime import date, time, datetime, timedelta
    
    try:
        interview = Interview.objects.get(confirmation_token=token, status='PENDING')
    except Interview.DoesNotExist:
        return JsonResponse({"error": "Invalid or expired interview link"}, status=404)
    
    # Get recruiter interview settings
    recruiter = interview.recruiter
    schedule_from_date = None
    schedule_to_date = None
    start_time = time(9, 0)  # Default
    end_time = time(17, 0)  # Default
    interviews_per_day = 3  # Default
    
    if recruiter:
        try:
            settings = recruiter.recruiter_interview_settings
            schedule_from_date = settings.schedule_from_date
            schedule_to_date = settings.schedule_to_date
            start_time = settings.start_time
            end_time = settings.end_time
            interviews_per_day = settings.interviews_per_day
        except RecruiterInterviewSettings.DoesNotExist:
            pass
    
    # Get already scheduled interviews for the same recruiter
    now = timezone.now()
    scheduled_interviews = Interview.objects.filter(
        recruiter=recruiter,
        status='SCHEDULED',
        scheduled_datetime__isnull=False
    ).exclude(id=interview.id)
    
    # Get scheduled dates and times
    scheduled_datetimes = set()
    scheduled_dates_count = {}  # Count interviews per date
    
    for scheduled_interview in scheduled_interviews:
        if scheduled_interview.scheduled_datetime:
            scheduled_datetime = scheduled_interview.scheduled_datetime
            scheduled_datetimes.add(scheduled_datetime)
            scheduled_date = scheduled_datetime.date()
            scheduled_dates_count[scheduled_date] = scheduled_dates_count.get(scheduled_date, 0) + 1
    
    # Determine min and max dates
    min_date = schedule_from_date if schedule_from_date else now.date()
    if min_date < now.date():
        min_date = now.date()
    
    max_date = schedule_to_date if schedule_to_date else (now.date() + timedelta(days=60))
    
    return JsonResponse({
        "success": True,
        "constraints": {
            "min_date": min_date.isoformat(),
            "max_date": max_date.isoformat(),
            "start_time": start_time.strftime('%H:%M'),
            "end_time": end_time.strftime('%H:%M'),
            "interviews_per_day": interviews_per_day,
        },
        "scheduled_slots": [dt.isoformat() for dt in scheduled_datetimes],
        "scheduled_dates_count": {str(k): v for k, v in scheduled_dates_count.items()},
    })


@require_http_methods(["GET", "POST"])
def candidate_select_slot(request, token):
    """
    Public page for candidate to select interview slot using token.
    No authentication required - accessed via unique token from email.
    """
    from django.shortcuts import render
    from django.contrib import messages
    from recruitment_agent.models import Interview
    
    try:
        interview = Interview.objects.get(confirmation_token=token, status='PENDING')
    except Interview.DoesNotExist:
        return render(request, 'recruitment_agent/candidate_slot_selection.html', {
            'error': 'Invalid or expired interview link. Please contact the recruiter.',
            'invalid_token': True,
        })
    
    if request.method == 'POST':
        selected_slot_datetime = request.POST.get('selected_slot_datetime')
        if not selected_slot_datetime:
            messages.error(request, 'Please select a date and time.')
            return render(request, 'recruitment_agent/candidate_slot_selection.html', {
                'interview': interview,
                'token': token,
            })
        
        # Confirm the slot
        agents = get_agents()
        interview_agent = agents['interview_agent']
        
        result = interview_agent.confirm_slot(interview.id, selected_slot_datetime)
        
        if result.get('success'):
            # Refresh interview to get updated data
            interview.refresh_from_db()
            messages.success(request, 'Your interview slot has been confirmed! You will receive a confirmation email shortly.')
            return render(request, 'recruitment_agent/candidate_slot_confirmed.html', {
                'interview': interview,
                'scheduled_datetime': interview.scheduled_datetime,
                'selected_slot': interview.selected_slot,
            })
        else:
            messages.error(request, f"Error: {result.get('error', 'Failed to confirm slot')}")
            return render(request, 'recruitment_agent/candidate_slot_selection.html', {
                'interview': interview,
                'token': token,
            })
    
    # GET request - show slot selection page
    return render(request, 'recruitment_agent/candidate_slot_selection.html', {
        'interview': interview,
        'token': token,
    })


# Job Description CRUD views
@login_required
@require_http_methods(["GET"])
def list_job_descriptions(request):
    """List all job descriptions"""
    is_recruitment_agent = request.user.profile.is_recruitment_agent()
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'recruitment_agent':
            is_recruitment_agent = True
    
    if not is_recruitment_agent:
        return JsonResponse({"error": "Unauthorized. Recruitment Agent role required."}, status=403)
    
    job_descriptions = JobDescription.objects.all().order_by('-created_at')
    job_list = []
    for jd in job_descriptions:
        job_list.append({
            'id': jd.id,
            'title': jd.title,
            'description': jd.description,
            'is_active': jd.is_active,
            'created_by': jd.created_by.username if jd.created_by else None,
            'created_at': jd.created_at.isoformat(),
            'updated_at': jd.updated_at.isoformat(),
        })
    
    return JsonResponse({'job_descriptions': job_list}, safe=False)


@login_required
@require_http_methods(["POST"])
def create_job_description(request):
    """Create a new job description"""
    is_recruitment_agent = request.user.profile.is_recruitment_agent()
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'recruitment_agent':
            is_recruitment_agent = True
    
    if not is_recruitment_agent:
        return JsonResponse({"error": "Unauthorized. Recruitment Agent role required."}, status=403)
    
    agents = get_agents()
    job_desc_agent = agents['job_desc_agent']
    log_service = agents['log_service']
    
    try:
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        parse_keywords = request.POST.get('parse_keywords', 'true').lower() == 'true'
        
        if not title or not description:
            return JsonResponse({"error": "Missing required fields: title, description"}, status=400)
        
        # Parse keywords if requested
        keywords_json = None
        if parse_keywords:
            try:
                parsed = job_desc_agent.parse_text(description)
                import json
                keywords_json = json.dumps(parsed)
            except Exception as exc:
                log_service.log_error("job_description_keyword_parsing_failed", {"error": str(exc)})
                # Continue without keywords if parsing fails
        
        # Extract new fields from request
        location = request.POST.get('location', '').strip() or None
        department = request.POST.get('department', '').strip() or None
        job_type = request.POST.get('type', '').strip() or 'Full-time'
        requirements = request.POST.get('requirements', '').strip() or None
        company_id = request.POST.get('company_id', '').strip() or None
        
        job_desc = JobDescription.objects.create(
            title=title,
            description=description,
            keywords_json=keywords_json,
            created_by=request.user,
            is_active=True,
            location=location,
            department=department,
            type=job_type,
            requirements=requirements,
            company_id=company_id if company_id else None,
        )
        
        return JsonResponse({
            'success': True,
            'job_description': {
                'id': job_desc.id,
                'title': job_desc.title,
                'description': job_desc.description,
                'is_active': job_desc.is_active,
                'created_at': job_desc.created_at.isoformat(),
            }
        })
        
    except Exception as e:
        log_service.log_error("job_description_creation_error", {"error": str(e)})
        return JsonResponse({"error": f"Creation failed: {str(e)}"}, status=500)


@login_required
@require_http_methods(["POST"])
def update_job_description(request, job_description_id):
    """Update an existing job description"""
    is_recruitment_agent = request.user.profile.is_recruitment_agent()
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'recruitment_agent':
            is_recruitment_agent = True
    
    if not is_recruitment_agent:
        return JsonResponse({"error": "Unauthorized. Recruitment Agent role required."}, status=403)
    
    agents = get_agents()
    job_desc_agent = agents['job_desc_agent']
    log_service = agents['log_service']
    
    try:
        job_desc = JobDescription.objects.get(id=job_description_id)
        
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        is_active = request.POST.get('is_active', '').lower() == 'true'
        parse_keywords = request.POST.get('parse_keywords', 'false').lower() == 'true'
        
        if title:
            job_desc.title = title
        if description:
            job_desc.description = description
        
        job_desc.is_active = is_active
        
        # Parse keywords if requested
        if parse_keywords and description:
            try:
                parsed = job_desc_agent.parse_text(description)
                import json
                job_desc.keywords_json = json.dumps(parsed)
            except Exception as exc:
                log_service.log_error("job_description_keyword_parsing_failed", {"error": str(exc)})
        
        job_desc.save()
        
        return JsonResponse({
            'success': True,
            'job_description': {
                'id': job_desc.id,
                'title': job_desc.title,
                'description': job_desc.description,
                'is_active': job_desc.is_active,
                'updated_at': job_desc.updated_at.isoformat(),
            }
        })
        
    except JobDescription.DoesNotExist:
        return JsonResponse({"error": "Job description not found"}, status=404)
    except Exception as e:
        log_service.log_error("job_description_update_error", {"error": str(e)})
        return JsonResponse({"error": f"Update failed: {str(e)}"}, status=500)


@login_required
@require_http_methods(["DELETE", "POST"])
def delete_job_description(request, job_description_id):
    """Delete a job description"""
    is_recruitment_agent = request.user.profile.is_recruitment_agent()
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'recruitment_agent':
            is_recruitment_agent = True
    
    if not is_recruitment_agent:
        return JsonResponse({"error": "Unauthorized. Recruitment Agent role required."}, status=403)
    
    try:
        job_desc = JobDescription.objects.get(id=job_description_id)
        job_desc.delete()
        
        return JsonResponse({'success': True})
        
    except JobDescription.DoesNotExist:
        return JsonResponse({"error": "Job description not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": f"Delete failed: {str(e)}"}, status=500)


@login_required
def view_parsed_cv(request, cv_id):
    """Debug view to see parsed CV data in formatted JSON"""
    try:
        cv_record = CVRecord.objects.get(id=cv_id)
        parsed_data = json.loads(cv_record.parsed_json) if cv_record.parsed_json else None
        
        # Return JSON response for easy viewing
        return JsonResponse({
            'cv_record_id': cv_record.id,
            'file_name': cv_record.file_name,
            'parsed_data': parsed_data,
            'created_at': cv_record.created_at.isoformat() if cv_record.created_at else None,
        }, json_dumps_params={'indent': 2, 'ensure_ascii': False})
    except CVRecord.DoesNotExist:
        return JsonResponse({"error": "CV record not found"}, status=404)