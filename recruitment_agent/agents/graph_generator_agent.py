"""
AI Graph Generator Agent for Recruitment Dashboard
Uses LLM to interpret natural language prompts and generate appropriate visualizations
"""
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Q
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek

logger = logging.getLogger(__name__)


class GraphGeneratorAgent:
    """
    AI-powered agent that interprets natural language prompts and generates
    appropriate chart configurations based on recruitment data.
    """
    
    def __init__(self, groq_client, company_user):
        self.groq_client = groq_client
        self.company_user = company_user
    
    def _get_available_data_sources(self) -> Dict[str, Any]:
        """Get metadata about available data sources for the LLM context."""
        return {
            "cv_records": {
                "description": "Candidate CV records with parsing, qualification decisions",
                "fields": [
                    "id", "file_name", "qualification_decision (INTERVIEW/HOLD/REJECT)",
                    "qualification_confidence (0-100)", "qualification_priority (HIGH/MEDIUM/LOW)",
                    "role_fit_score (0-100)", "rank", "job_description_id", "created_at"
                ],
                "aggregations": ["count", "average_confidence", "by_decision", "by_job", "over_time"]
            },
            "interviews": {
                "description": "Interview scheduling and tracking",
                "fields": [
                    "id", "candidate_name", "candidate_email", "job_role",
                    "status (PENDING/SCHEDULED/COMPLETED/CANCELLED/RESCHEDULED)",
                    "outcome (ONSITE_INTERVIEW/HIRED/PASSED/REJECTED)",
                    "interview_type (ONLINE/ONSITE)", "scheduled_datetime", "created_at"
                ],
                "aggregations": ["count", "by_status", "by_outcome", "by_type", "over_time"]
            },
            "job_descriptions": {
                "description": "Job positions/openings",
                "fields": [
                    "id", "title", "department", "location", "type (Full-time/Part-time/Contract/Internship)",
                    "is_active (true/false)", "created_at"
                ],
                "aggregations": ["count", "by_type", "by_department", "active_vs_inactive", "by_location"]
            }
        }
    
    def _fetch_recruitment_data(self) -> Dict[str, Any]:
        """Fetch all relevant recruitment data for the company user."""
        from recruitment_agent.models import CVRecord, Interview, JobDescription, RecruiterInterviewSettings
        
        # Get jobs for this company
        jobs = JobDescription.objects.filter(
            Q(company_user=self.company_user) |
            Q(company=self.company_user.company)
        )
        
        # Get CV records
        cv_records = CVRecord.objects.filter(
            Q(job_description__company_user=self.company_user) |
            Q(job_description__company=self.company_user.company)
        ).select_related('job_description')
        
        # Get interviews
        interviews = Interview.objects.filter(
            Q(company_user=self.company_user) |
            Q(recruiter=self.company_user.user if hasattr(self.company_user, 'user') else None)
        )
        
        # Get interview settings for jobs
        interview_settings = RecruiterInterviewSettings.objects.filter(
            Q(company_user=self.company_user) |
            Q(recruiter=self.company_user.user if hasattr(self.company_user, 'user') else None)
        ).select_related('job')
        
        # Time ranges
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        ninety_days_ago = now - timedelta(days=90)
        
        # Aggregate data - with SQL Server compatible queries
        # Clear default ordering to avoid SQL Server GROUP BY issues
        jobs_unordered = jobs.order_by()
        cv_records_unordered = cv_records.order_by()
        interviews_unordered = interviews.order_by()
        
        # Jobs by type
        jobs_by_type = {}
        try:
            for item in jobs_unordered.values('type').annotate(count=Count('id')):
                if item['type']:
                    jobs_by_type[item['type']] = item['count']
        except Exception as e:
            logger.warning(f"Error fetching jobs by type: {e}")
        
        # Jobs by department
        jobs_by_dept = {}
        try:
            for item in jobs_unordered.exclude(department__isnull=True).exclude(department='').values('department').annotate(count=Count('id')):
                if item['department']:
                    jobs_by_dept[item['department']] = item['count']
        except Exception as e:
            logger.warning(f"Error fetching jobs by department: {e}")
        
        # Jobs by location
        jobs_by_loc = {}
        try:
            for item in jobs_unordered.exclude(location__isnull=True).exclude(location='').values('location').annotate(count=Count('id')):
                if item['location']:
                    jobs_by_loc[item['location']] = item['count']
        except Exception as e:
            logger.warning(f"Error fetching jobs by location: {e}")
        
        data = {
            # Job statistics
            "jobs": {
                "total": jobs.count(),
                "active": jobs.filter(is_active=True).count(),
                "inactive": jobs.filter(is_active=False).count(),
                "by_type": jobs_by_type,
                "by_department": jobs_by_dept,
                "by_location": jobs_by_loc,
                "list": list(jobs.order_by('-created_at').values('id', 'title', 'is_active', 'type', 'department', 'location')[:50]),
            },
            
            # CV/Candidate statistics
            "candidates": {
                "total": cv_records.count(),
                "by_decision": {
                    "INTERVIEW": cv_records.filter(qualification_decision='INTERVIEW').count(),
                    "HOLD": cv_records.filter(qualification_decision='HOLD').count(),
                    "REJECT": cv_records.filter(qualification_decision='REJECT').count(),
                },
                "by_priority": {
                    "HIGH": cv_records.filter(qualification_priority='HIGH').count(),
                    "MEDIUM": cv_records.filter(qualification_priority='MEDIUM').count(),
                    "LOW": cv_records.filter(qualification_priority='LOW').count(),
                },
                "avg_confidence": cv_records.filter(qualification_confidence__isnull=False).aggregate(avg=Avg('qualification_confidence'))['avg'] or 0,
                "avg_role_fit": cv_records.filter(role_fit_score__isnull=False).aggregate(avg=Avg('role_fit_score'))['avg'] or 0,
                "by_job": {},
                "over_time_daily": [],
                "over_time_weekly": [],
                "over_time_monthly": [],
            },
            
            # Interview statistics
            "interviews": {
                "total": interviews.count(),
                "by_status": {
                    "PENDING": interviews.filter(status='PENDING').count(),
                    "SCHEDULED": interviews.filter(status='SCHEDULED').count(),
                    "COMPLETED": interviews.filter(status='COMPLETED').count(),
                    "CANCELLED": interviews.filter(status='CANCELLED').count(),
                    "RESCHEDULED": interviews.filter(status='RESCHEDULED').count(),
                },
                "by_outcome": {
                    "ONSITE_INTERVIEW": interviews.filter(outcome='ONSITE_INTERVIEW').count(),
                    "HIRED": interviews.filter(outcome='HIRED').count(),
                    "PASSED": interviews.filter(outcome='PASSED').count(),
                    "REJECTED": interviews.filter(outcome='REJECTED').count(),
                },
                "by_type": {
                    "ONLINE": interviews.filter(interview_type='ONLINE').count(),
                    "ONSITE": interviews.filter(interview_type='ONSITE').count(),
                },
                "by_job_role": {},
                "over_time_daily": [],
                "over_time_weekly": [],
                "over_time_monthly": [],
                "scheduling": {
                    "scheduled_today": 0,
                    "scheduled_this_week": 0,
                    "scheduled_this_month": 0,
                    "upcoming": [],
                    "by_hour_of_day": {},
                    "by_day_of_week": {},
                    "avg_time_to_schedule_days": 0,
                    "confirmation_rate": 0,
                },
            },
            
            # Interview Settings / Time Slots
            "interview_settings": {
                "total_jobs_with_settings": 0,
                "jobs_settings": [],
                "time_gaps_distribution": {},
                "interview_types_default": {},
                "total_available_slots": 0,
                "slots_by_job": {},
            },
        }
        
        # Interview by job role
        try:
            for item in interviews_unordered.exclude(job_role__isnull=True).exclude(job_role='').values('job_role').annotate(count=Count('id')):
                if item['job_role']:
                    data["interviews"]["by_job_role"][item['job_role'][:40]] = item['count']
        except Exception as e:
            logger.warning(f"Error fetching interviews by job role: {e}")
        
        # Interview scheduling analysis
        try:
            today = now.date()
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)
            month_start = today.replace(day=1)
            
            # Scheduled interviews counts
            data["interviews"]["scheduling"]["scheduled_today"] = interviews.filter(
                scheduled_datetime__date=today
            ).count()
            
            data["interviews"]["scheduling"]["scheduled_this_week"] = interviews.filter(
                scheduled_datetime__date__gte=week_start,
                scheduled_datetime__date__lte=week_end
            ).count()
            
            data["interviews"]["scheduling"]["scheduled_this_month"] = interviews.filter(
                scheduled_datetime__date__gte=month_start
            ).count()
            
            # Upcoming interviews (next 7 days)
            upcoming = interviews.filter(
                scheduled_datetime__gte=now,
                scheduled_datetime__lte=now + timedelta(days=7),
                status__in=['SCHEDULED', 'PENDING']
            ).order_by('scheduled_datetime')[:10]
            
            data["interviews"]["scheduling"]["upcoming"] = [
                {
                    "candidate": i.candidate_name,
                    "job_role": i.job_role,
                    "datetime": i.scheduled_datetime.isoformat() if i.scheduled_datetime else None,
                    "type": i.interview_type,
                    "status": i.status,
                }
                for i in upcoming
            ]
            
            # Interviews by hour of day
            for hour in range(9, 19):  # 9 AM to 6 PM
                count = interviews.filter(scheduled_datetime__hour=hour).count()
                if count > 0:
                    hour_label = f"{hour}:00" if hour < 12 else f"{hour-12 if hour > 12 else 12}:00 PM"
                    if hour < 12:
                        hour_label = f"{hour}:00 AM"
                    data["interviews"]["scheduling"]["by_hour_of_day"][hour_label] = count
            
            # Interviews by day of week
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            for day_num, day_name in enumerate(day_names):
                count = interviews.filter(scheduled_datetime__week_day=day_num + 2).count()  # Django week_day: Sunday=1
                if count > 0:
                    data["interviews"]["scheduling"]["by_day_of_week"][day_name] = count
            
            # Average time to schedule (from creation to scheduled datetime)
            scheduled_interviews = interviews.filter(
                scheduled_datetime__isnull=False,
                created_at__isnull=False
            )
            if scheduled_interviews.exists():
                total_days = 0
                count = 0
                for interview in scheduled_interviews[:100]:  # Sample
                    if interview.scheduled_datetime and interview.created_at:
                        diff = (interview.scheduled_datetime - interview.created_at).days
                        if diff >= 0:
                            total_days += diff
                            count += 1
                if count > 0:
                    data["interviews"]["scheduling"]["avg_time_to_schedule_days"] = round(total_days / count, 1)
            
            # Confirmation rate
            total_with_slots = interviews.exclude(selected_slot__isnull=True).exclude(selected_slot='').count()
            if interviews.count() > 0:
                data["interviews"]["scheduling"]["confirmation_rate"] = round(
                    (total_with_slots / interviews.count()) * 100, 1
                )
        except Exception as e:
            logger.warning(f"Error fetching interview scheduling data: {e}")
        
        # Interview Settings Analysis
        try:
            settings_list = list(interview_settings)
            data["interview_settings"]["total_jobs_with_settings"] = len(settings_list)
            
            for setting in settings_list[:20]:
                job_title = setting.job.title if setting.job else "Default Settings"
                slots_count = len(setting.time_slots_json) if setting.time_slots_json else 0
                
                data["interview_settings"]["jobs_settings"].append({
                    "job": job_title[:40],
                    "start_time": str(setting.start_time),
                    "end_time": str(setting.end_time),
                    "time_gap_minutes": setting.interview_time_gap,
                    "interview_type": setting.default_interview_type,
                    "available_slots": slots_count,
                    "schedule_from": setting.schedule_from_date.isoformat() if setting.schedule_from_date else None,
                    "schedule_to": setting.schedule_to_date.isoformat() if setting.schedule_to_date else None,
                })
                
                # Aggregate time gaps
                gap = f"{setting.interview_time_gap} min"
                data["interview_settings"]["time_gaps_distribution"][gap] = \
                    data["interview_settings"]["time_gaps_distribution"].get(gap, 0) + 1
                
                # Aggregate interview types
                data["interview_settings"]["interview_types_default"][setting.default_interview_type] = \
                    data["interview_settings"]["interview_types_default"].get(setting.default_interview_type, 0) + 1
                
                # Total slots
                data["interview_settings"]["total_available_slots"] += slots_count
                if slots_count > 0:
                    data["interview_settings"]["slots_by_job"][job_title[:40]] = slots_count
        except Exception as e:
            logger.warning(f"Error fetching interview settings: {e}")
        
        # Candidates by job
        for job in jobs[:20]:
            count = cv_records.filter(job_description=job).count()
            if count > 0:
                data["candidates"]["by_job"][job.title[:40]] = count
        
        # Time series data - Daily (last 30 days)
        # For SQL Server compatibility, we clear ordering and use values() before annotate()
        try:
            cv_daily = list(
                cv_records_unordered.filter(created_at__gte=thirty_days_ago)
                .annotate(date=TruncDate('created_at'))
                .values('date')
                .annotate(count=Count('id'))
                .order_by('date')
            )
            data["candidates"]["over_time_daily"] = [
                {"label": d['date'].strftime('%m/%d'), "value": d['count'], "date": d['date'].isoformat()}
                for d in cv_daily if d.get('date')
            ]
        except Exception as e:
            logger.warning(f"Error fetching CV daily data: {e}")
            data["candidates"]["over_time_daily"] = []
        
        try:
            interview_daily = list(
                interviews_unordered.filter(created_at__gte=thirty_days_ago)
                .annotate(date=TruncDate('created_at'))
                .values('date')
                .annotate(count=Count('id'))
                .order_by('date')
            )
            data["interviews"]["over_time_daily"] = [
                {"label": d['date'].strftime('%m/%d'), "value": d['count'], "date": d['date'].isoformat()}
                for d in interview_daily if d.get('date')
            ]
        except Exception as e:
            logger.warning(f"Error fetching interview daily data: {e}")
            data["interviews"]["over_time_daily"] = []
        
        # Time series data - Weekly (last 90 days)
        try:
            cv_weekly = list(
                cv_records_unordered.filter(created_at__gte=ninety_days_ago)
                .annotate(week=TruncWeek('created_at'))
                .values('week')
                .annotate(count=Count('id'))
                .order_by('week')
            )
            data["candidates"]["over_time_weekly"] = [
                {"label": f"Week {d['week'].strftime('%m/%d')}", "value": d['count'], "date": d['week'].isoformat()}
                for d in cv_weekly if d.get('week')
            ]
        except Exception as e:
            logger.warning(f"Error fetching CV weekly data: {e}")
            data["candidates"]["over_time_weekly"] = []
        
        try:
            interview_weekly = list(
                interviews_unordered.filter(created_at__gte=ninety_days_ago)
                .annotate(week=TruncWeek('created_at'))
                .values('week')
                .annotate(count=Count('id'))
                .order_by('week')
            )
            data["interviews"]["over_time_weekly"] = [
                {"label": f"Week {d['week'].strftime('%m/%d')}", "value": d['count'], "date": d['week'].isoformat()}
                for d in interview_weekly if d.get('week')
            ]
        except Exception as e:
            logger.warning(f"Error fetching interview weekly data: {e}")
            data["interviews"]["over_time_weekly"] = []
        
        # Time series data - Monthly (last 6 months)
        six_months_ago = now - timedelta(days=180)
        try:
            cv_monthly = list(
                cv_records_unordered.filter(created_at__gte=six_months_ago)
                .annotate(month=TruncMonth('created_at'))
                .values('month')
                .annotate(count=Count('id'))
                .order_by('month')
            )
            data["candidates"]["over_time_monthly"] = [
                {"label": d['month'].strftime('%b %Y'), "value": d['count'], "date": d['month'].isoformat()}
                for d in cv_monthly if d.get('month')
            ]
        except Exception as e:
            logger.warning(f"Error fetching CV monthly data: {e}")
            data["candidates"]["over_time_monthly"] = []
        
        try:
            interview_monthly = list(
                interviews_unordered.filter(created_at__gte=six_months_ago)
                .annotate(month=TruncMonth('created_at'))
                .values('month')
                .annotate(count=Count('id'))
                .order_by('month')
            )
            data["interviews"]["over_time_monthly"] = [
                {"label": d['month'].strftime('%b %Y'), "value": d['count'], "date": d['month'].isoformat()}
                for d in interview_monthly if d.get('month')
            ]
        except Exception as e:
            logger.warning(f"Error fetching interview monthly data: {e}")
            data["interviews"]["over_time_monthly"] = []
        
        return data
    
    def generate_graph(self, prompt: str) -> Dict[str, Any]:
        """
        Generate a graph configuration based on natural language prompt.
        Uses AI to interpret the prompt and select appropriate data/chart type.
        """
        # Fetch current data
        recruitment_data = self._fetch_recruitment_data()
        
        # Build system prompt for LLM
        system_prompt = """You are an AI assistant that generates chart configurations for a recruitment dashboard.
Your task is to interpret the user's natural language request and return a JSON configuration for a chart.

Available data from the database:
{data_summary}

You must respond with ONLY a valid JSON object (no markdown, no explanation) with this structure:
{{
    "chart_type": "bar" | "pie" | "line" | "area",
    "title": "Chart title",
    "data": {{ "label1": value1, "label2": value2 }} for bar/pie OR [{{ "label": "x", "value": y }}] for line/area,
    "insights": "Brief insight about the data (1-2 sentences)",
    "colors": ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"],
    "orientation": "horizontal" | "vertical"  (only for bar charts; omit for other types)
}}

Rules:
1. For pie charts: use object format {{ "Category": count }}
2. For bar charts: use object format {{ "Category": count }}
2a. For bar chart orientation: use "vertical" when user asks for "vertical bar", "vertical histogram", "column chart", or "histogram" (without "horizontal"); use "horizontal" when user asks for "horizontal bar" or for generic "bar chart" without specifying vertical
3. For line/area charts: use array format [{{ "label": "date/period", "value": count }}]
4. Only include categories with count > 0
5. Use the actual data values from the database
6. Choose the most appropriate chart type for the request
7. If user asks for "active vs inactive jobs", use the jobs.active and jobs.inactive values
8. If user asks for "applicants per job", use candidates.by_job data
9. If user asks for trends/over time, use the over_time_daily/weekly/monthly arrays
10. If user asks for "top N" (e.g., "top 5", "top 3"), only include the N items with highest values, sorted descending
11. If user asks for "bottom N" or "lowest N", only include the N items with lowest values
12. Always sort bar chart data by value (highest first) unless user asks for alphabetical or chronological order
13. For "top applicants" or "most applicants", sort candidates.by_job by count descending and take top N
14. For "interview times" or "interview hours", use scheduling.by_hour_of_day data - bar chart is best
15. For "interview days" or "busiest days", use scheduling.by_day_of_week data
16. For "interview time gaps" or "slot duration", use interview_settings.time_gaps_distribution
17. For "interview slots by job" or "available slots", use interview_settings.slots_by_job
18. For "online vs onsite" interviews, use interviews.by_type data
19. For "interview outcomes" or "hiring results", use interviews.by_outcome data
20. For "upcoming interviews", list the scheduling.upcoming data
21. For "interview confirmation rate" or "response rate", show the confirmation_rate percentage
22. For "time to schedule" or "scheduling efficiency", show avg_time_to_schedule_days
"""
        
        # Create data summary for LLM
        data_summary = f"""
JOBS DATA:
- Total jobs: {recruitment_data['jobs']['total']}
- Active jobs: {recruitment_data['jobs']['active']}
- Inactive jobs: {recruitment_data['jobs']['inactive']}
- Jobs by type: {json.dumps(recruitment_data['jobs']['by_type'])}
- Jobs by department: {json.dumps(recruitment_data['jobs']['by_department'])}
- Jobs by location: {json.dumps(recruitment_data['jobs']['by_location'])}

CANDIDATES DATA:
- Total candidates: {recruitment_data['candidates']['total']}
- By decision: {json.dumps(recruitment_data['candidates']['by_decision'])}
- By priority: {json.dumps(recruitment_data['candidates']['by_priority'])}
- Average confidence: {recruitment_data['candidates']['avg_confidence']:.1f}%
- Average role fit: {recruitment_data['candidates']['avg_role_fit']:.1f}%
- Candidates per job: {json.dumps(recruitment_data['candidates']['by_job'])}
- Daily trend (last 30 days): {json.dumps(recruitment_data['candidates']['over_time_daily'][-10:] if recruitment_data['candidates']['over_time_daily'] else [])}
- Monthly trend: {json.dumps(recruitment_data['candidates']['over_time_monthly'])}

INTERVIEWS DATA:
- Total interviews: {recruitment_data['interviews']['total']}
- By status: {json.dumps(recruitment_data['interviews']['by_status'])}
- By outcome: {json.dumps(recruitment_data['interviews']['by_outcome'])}
- By type (Online/Onsite): {json.dumps(recruitment_data['interviews']['by_type'])}
- By job role: {json.dumps(recruitment_data['interviews'].get('by_job_role', {}))}
- Daily trend (last 30 days): {json.dumps(recruitment_data['interviews']['over_time_daily'][-10:] if recruitment_data['interviews']['over_time_daily'] else [])}
- Monthly trend: {json.dumps(recruitment_data['interviews']['over_time_monthly'])}

INTERVIEW SCHEDULING DATA:
- Scheduled today: {recruitment_data['interviews'].get('scheduling', {}).get('scheduled_today', 0)}
- Scheduled this week: {recruitment_data['interviews'].get('scheduling', {}).get('scheduled_this_week', 0)}
- Scheduled this month: {recruitment_data['interviews'].get('scheduling', {}).get('scheduled_this_month', 0)}
- Interviews by hour of day: {json.dumps(recruitment_data['interviews'].get('scheduling', {}).get('by_hour_of_day', {}))}
- Interviews by day of week: {json.dumps(recruitment_data['interviews'].get('scheduling', {}).get('by_day_of_week', {}))}
- Average days to schedule: {recruitment_data['interviews'].get('scheduling', {}).get('avg_time_to_schedule_days', 0)}
- Confirmation rate: {recruitment_data['interviews'].get('scheduling', {}).get('confirmation_rate', 0)}%
- Upcoming interviews (next 7 days): {json.dumps(recruitment_data['interviews'].get('scheduling', {}).get('upcoming', [])[:5])}

INTERVIEW SETTINGS (Time Slots Configuration):
- Jobs with interview settings: {recruitment_data.get('interview_settings', {}).get('total_jobs_with_settings', 0)}
- Time gap distribution: {json.dumps(recruitment_data.get('interview_settings', {}).get('time_gaps_distribution', {}))}
- Default interview types: {json.dumps(recruitment_data.get('interview_settings', {}).get('interview_types_default', {}))}
- Total available slots: {recruitment_data.get('interview_settings', {}).get('total_available_slots', 0)}
- Slots by job: {json.dumps(recruitment_data.get('interview_settings', {}).get('slots_by_job', {}))}
- Job settings details: {json.dumps(recruitment_data.get('interview_settings', {}).get('jobs_settings', [])[:5])}
"""
        
        try:
            # Call LLM to interpret prompt and generate chart config
            # Use send_prompt_text which returns raw text response
            response_text = self.groq_client.send_prompt_text(
                system_prompt.format(data_summary=data_summary),
                f"Generate a chart for: {prompt}"
            )
            logger.info(f"LLM Response for graph generation: {response_text[:500]}")
            
            # Clean up response - remove markdown code blocks if present
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                # Find the closing ```
                end_idx = -1
                for i, line in enumerate(lines):
                    if i > 0 and line.strip() == '```':
                        end_idx = i
                        break
                if end_idx > 0:
                    response_text = '\n'.join(lines[1:end_idx])
                else:
                    response_text = '\n'.join(lines[1:])
            
            # Also handle ```json prefix
            if response_text.startswith('json'):
                response_text = response_text[4:].strip()
            
            # Parse JSON
            chart_config = json.loads(response_text)
            
            # Validate and set defaults
            if 'chart_type' not in chart_config:
                chart_config['chart_type'] = 'bar'
            if 'title' not in chart_config:
                chart_config['title'] = 'Generated Chart'
            if 'data' not in chart_config:
                chart_config['data'] = {}
            if 'colors' not in chart_config:
                chart_config['colors'] = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']
            # Bar orientation: respect user request (vertical/horizontal)
            chart_out = {
                'type': chart_config['chart_type'],
                'title': chart_config['title'],
                'data': chart_config['data'],
                'colors': chart_config.get('colors', ['#3b82f6', '#10b981', '#f59e0b', '#ef4444']),
                'color': chart_config.get('colors', ['#3b82f6'])[0],
            }
            if chart_config['chart_type'] == 'bar':
                chart_out['orientation'] = chart_config.get('orientation', 'horizontal')
            return {
                'chart': chart_out,
                'insights': chart_config.get('insights', ''),
                'raw_data': recruitment_data,  # Include raw data for debugging
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            # Fallback to a default chart
            return self._generate_fallback_chart(prompt, recruitment_data)
        except Exception as e:
            logger.error(f"Error generating graph: {e}")
            return self._generate_fallback_chart(prompt, recruitment_data)
    
    def _generate_fallback_chart(self, prompt: str, data: Dict) -> Dict[str, Any]:
        """Generate a fallback chart when LLM fails."""
        prompt_lower = prompt.lower()
        
        # Check for line chart / trends requests FIRST
        is_line_chart = any(word in prompt_lower for word in ['line', 'trend', 'over time', 'monthly', 'daily', 'weekly', 'time series'])
        is_cv_related = any(word in prompt_lower for word in ['cv', 'candidate', 'applicant', 'processing'])
        is_interview_related = any(word in prompt_lower for word in ['interview'])
        
        # Monthly/Daily/Weekly CV trends
        if is_line_chart and is_cv_related:
            if 'monthly' in prompt_lower:
                chart_data = data['candidates']['over_time_monthly']
            elif 'weekly' in prompt_lower:
                chart_data = data['candidates']['over_time_weekly']
            else:
                chart_data = data['candidates']['over_time_daily']
            
            return {
                'chart': {
                    'type': 'line',
                    'title': 'CV Processing Trends',
                    'data': chart_data if chart_data else [{"label": "No Data", "value": 0}],
                    'colors': ['#3b82f6'],
                    'color': '#3b82f6',
                },
                'insights': f"CV processing activity over time. Total {data['candidates']['total']} candidates processed.",
            }
        
        # Monthly/Daily/Weekly Interview trends
        if is_line_chart and is_interview_related:
            if 'monthly' in prompt_lower:
                chart_data = data['interviews']['over_time_monthly']
            elif 'weekly' in prompt_lower:
                chart_data = data['interviews']['over_time_weekly']
            else:
                chart_data = data['interviews']['over_time_daily']
            
            return {
                'chart': {
                    'type': 'line',
                    'title': 'Interview Scheduling Trends',
                    'data': chart_data if chart_data else [{"label": "No Data", "value": 0}],
                    'colors': ['#10b981'],
                    'color': '#10b981',
                },
                'insights': f"Interview scheduling activity over time. Total {data['interviews']['total']} interviews.",
            }
        
        # Active vs Inactive jobs
        if 'active' in prompt_lower and 'inactive' in prompt_lower and 'job' in prompt_lower:
            # Use vertical bar when user asks for vertical/histogram/column
            want_vertical = any(w in prompt_lower for w in ['vertical', 'histogram', 'column chart', 'column'])
            return {
                'chart': {
                    'type': 'bar',
                    'title': 'Active vs Inactive Jobs',
                    'data': {
                        'Active': data['jobs']['active'],
                        'Inactive': data['jobs']['inactive'],
                    },
                    'colors': ['#10b981', '#ef4444'],
                    'color': '#10b981',
                    'orientation': 'vertical' if want_vertical else 'horizontal',
                },
                'insights': f"You have {data['jobs']['active']} active and {data['jobs']['inactive']} inactive job positions.",
            }
        
        # Applicants per job
        elif 'applicant' in prompt_lower or ('candidate' in prompt_lower and 'job' in prompt_lower):
            job_data = data['candidates']['by_job'] or {'No Data': 0}
            # Sort by value descending
            sorted_data = dict(sorted(job_data.items(), key=lambda x: x[1], reverse=True))
            
            # Check for top N
            import re
            top_match = re.search(r'top\s*(\d+)', prompt_lower)
            if top_match:
                n = int(top_match.group(1))
                sorted_data = dict(list(sorted_data.items())[:n])
            
            return {
                'chart': {
                    'type': 'bar',
                    'title': 'Applicants per Job',
                    'data': sorted_data,
                    'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
                    'color': '#3b82f6',
                },
                'insights': f"Distribution of {data['candidates']['total']} candidates across job positions.",
            }
        
        # Candidate decisions
        elif 'decision' in prompt_lower or ('interview' in prompt_lower and 'hold' in prompt_lower):
            return {
                'chart': {
                    'type': 'pie',
                    'title': 'Candidates by Decision',
                    'data': {k: v for k, v in data['candidates']['by_decision'].items() if v > 0},
                    'colors': ['#10b981', '#f59e0b', '#ef4444'],
                    'color': '#10b981',
                },
                'insights': f"Qualification decisions for {data['candidates']['total']} candidates.",
            }
        
        # Interview status
        elif 'interview' in prompt_lower and 'status' in prompt_lower:
            return {
                'chart': {
                    'type': 'bar',
                    'title': 'Interviews by Status',
                    'data': {k: v for k, v in data['interviews']['by_status'].items() if v > 0},
                    'colors': ['#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#8b5cf6'],
                    'color': '#f59e0b',
                },
                'insights': f"Status distribution of {data['interviews']['total']} interviews.",
            }
        
        # Interview outcomes
        elif 'interview' in prompt_lower and ('outcome' in prompt_lower or 'result' in prompt_lower):
            return {
                'chart': {
                    'type': 'pie',
                    'title': 'Interview Outcomes',
                    'data': {k: v for k, v in data['interviews']['by_outcome'].items() if v > 0},
                    'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444'],
                    'color': '#3b82f6',
                },
                'insights': f"Outcome distribution of completed interviews.",
            }
        
        # Interview times / hours of day
        elif 'interview' in prompt_lower and ('time' in prompt_lower or 'hour' in prompt_lower or 'schedule' in prompt_lower):
            scheduling = data['interviews'].get('scheduling', {})
            by_hour = scheduling.get('by_hour_of_day', {})
            if by_hour:
                return {
                    'chart': {
                        'type': 'bar',
                        'title': 'Interviews by Hour of Day',
                        'data': by_hour,
                        'colors': ['#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#ef4444'],
                        'color': '#8b5cf6',
                    },
                    'insights': f"Most interviews are scheduled during peak business hours. {scheduling.get('scheduled_today', 0)} interviews scheduled today.",
                }
            else:
                return {
                    'chart': {
                        'type': 'bar',
                        'title': 'Interview Scheduling Summary',
                        'data': {
                            'Today': scheduling.get('scheduled_today', 0),
                            'This Week': scheduling.get('scheduled_this_week', 0),
                            'This Month': scheduling.get('scheduled_this_month', 0),
                        },
                        'colors': ['#3b82f6', '#10b981', '#f59e0b'],
                        'color': '#3b82f6',
                    },
                    'insights': f"Interview scheduling overview. Confirmation rate: {scheduling.get('confirmation_rate', 0)}%",
                }
        
        # Interview days of week
        elif 'interview' in prompt_lower and ('day' in prompt_lower or 'week' in prompt_lower):
            scheduling = data['interviews'].get('scheduling', {})
            by_day = scheduling.get('by_day_of_week', {})
            if by_day:
                return {
                    'chart': {
                        'type': 'bar',
                        'title': 'Interviews by Day of Week',
                        'data': by_day,
                        'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#6366f1'],
                        'color': '#3b82f6',
                    },
                    'insights': f"Distribution of interviews across weekdays.",
                }
        
        # Interview type (Online vs Onsite)
        elif 'interview' in prompt_lower and ('online' in prompt_lower or 'onsite' in prompt_lower or 'type' in prompt_lower):
            return {
                'chart': {
                    'type': 'pie',
                    'title': 'Interview Types',
                    'data': {k: v for k, v in data['interviews']['by_type'].items() if v > 0},
                    'colors': ['#3b82f6', '#10b981'],
                    'color': '#3b82f6',
                },
                'insights': f"Distribution between online and onsite interviews.",
            }
        
        # Interview by job role
        elif 'interview' in prompt_lower and ('job' in prompt_lower or 'role' in prompt_lower or 'position' in prompt_lower):
            by_role = data['interviews'].get('by_job_role', {})
            if by_role:
                sorted_data = dict(sorted(by_role.items(), key=lambda x: x[1], reverse=True))
                # Check for top N
                import re
                top_match = re.search(r'top\s*(\d+)', prompt_lower)
                if top_match:
                    n = int(top_match.group(1))
                    sorted_data = dict(list(sorted_data.items())[:n])
                return {
                    'chart': {
                        'type': 'bar',
                        'title': 'Interviews by Job Role',
                        'data': sorted_data,
                        'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
                        'color': '#3b82f6',
                    },
                    'insights': f"Distribution of interviews across different job roles.",
                }
        
        # Interview time gaps / slot duration
        elif ('gap' in prompt_lower or 'slot' in prompt_lower or 'duration' in prompt_lower):
            settings = data.get('interview_settings', {})
            time_gaps = settings.get('time_gaps_distribution', {})
            if time_gaps:
                return {
                    'chart': {
                        'type': 'pie',
                        'title': 'Interview Time Gap Distribution',
                        'data': time_gaps,
                        'colors': ['#3b82f6', '#10b981', '#f59e0b', '#ef4444'],
                        'color': '#3b82f6',
                    },
                    'insights': f"Distribution of interview slot durations across jobs. Total {settings.get('total_available_slots', 0)} slots available.",
                }
            slots_by_job = settings.get('slots_by_job', {})
            if slots_by_job:
                return {
                    'chart': {
                        'type': 'bar',
                        'title': 'Available Interview Slots by Job',
                        'data': slots_by_job,
                        'colors': ['#10b981', '#3b82f6', '#f59e0b', '#ef4444'],
                        'color': '#10b981',
                    },
                    'insights': f"Total {settings.get('total_available_slots', 0)} interview slots available across all jobs.",
                }
        
        # Interview settings overview
        elif 'setting' in prompt_lower or 'configuration' in prompt_lower:
            settings = data.get('interview_settings', {})
            return {
                'chart': {
                    'type': 'bar',
                    'title': 'Interview Settings Overview',
                    'data': {
                        'Jobs with Settings': settings.get('total_jobs_with_settings', 0),
                        'Total Slots': settings.get('total_available_slots', 0),
                    },
                    'colors': ['#3b82f6', '#10b981'],
                    'color': '#3b82f6',
                },
                'insights': f"Interview configuration summary. {settings.get('total_jobs_with_settings', 0)} jobs have custom interview settings.",
            }
        
        # Default: show candidate decisions
        else:
            return {
                'chart': {
                    'type': 'pie',
                    'title': 'Recruitment Overview',
                    'data': {k: v for k, v in data['candidates']['by_decision'].items() if v > 0} or {'No Data': 0},
                    'colors': ['#10b981', '#f59e0b', '#ef4444'],
                    'color': '#10b981',
                },
                'insights': f"Overview of {data['candidates']['total']} candidates processed.",
            }
