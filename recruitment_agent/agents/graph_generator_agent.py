"""
AI Graph Generator Agent for Recruitment Dashboard
Uses LLM to interpret natural language prompts and generate appropriate visualizations
"""
import json
import re
import logging
from typing import Any, Dict, List, Optional
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek

from core.api_key_service import KeyServiceError

logger = logging.getLogger(__name__)

# Words that point the AI to a data set, given to it only: the list of charts a refusal shows people is the plain one.
CHOICE_HINTS = {
    'interviews_by_date': 'use it for "interviews per day", "this week\'s interviews", "upcoming interviews"',
}


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
        
        from recruitment_agent import sharing

        # The company's jobs, candidates and interviews, whoever posted them
        jobs = sharing.jobs(self.company_user)
        cv_records = sharing.cvs(self.company_user).select_related('job_description')
        interviews = sharing.interviews(self.company_user)

        # Interview settings for the company's jobs
        interview_settings = RecruiterInterviewSettings.objects.filter(
            job__in=jobs
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
        
        # Candidates by job, and by job and decision
        data["candidates"]["by_job_and_decision"] = {}
        for job in jobs[:20]:
            count = cv_records.filter(job_description=job).count()
            if count > 0:
                data["candidates"]["by_job"][job.title[:40]] = count
                decisions = dict(cv_records.filter(job_description=job).exclude(qualification_decision__isnull=True)
                                 .exclude(qualification_decision='').order_by()
                                 .values_list('qualification_decision').annotate(n=Count('id')))
                if decisions:
                    data["candidates"]["by_job_and_decision"][job.title[:40]] = decisions
        
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

        # Booked interviews by the day they take place, on the company's clock (two weeks back, a month ahead).
        # "Interviews per day" could only count the day an interview was made, so three interviews booked today for
        # the coming days showed as three today.
        from recruitment_agent.interview_time import local, stored_zone
        by_day = {}
        for iv in interviews_unordered.filter(scheduled_datetime__gte=now - timedelta(days=14),
                                              scheduled_datetime__lte=now + timedelta(days=31)):
            day = local(iv.scheduled_datetime, stored_zone(iv)).date()
            by_day[day] = by_day.get(day, 0) + 1
        data["interviews"]["by_interview_date"] = [
            {"label": day.strftime('%a %d %b'), "value": count, "date": day.isoformat()}
            for day, count in sorted(by_day.items())
        ]

        return data
    
    def generate_graph(self, prompt: str) -> Dict[str, Any]:
        """
        Generate a graph configuration based on natural language prompt.
        Uses AI to interpret the prompt and select appropriate data/chart type.
        """
        # Fetch current data
        recruitment_data = self._fetch_recruitment_data()
        per_job = self._decisions_per_job_chart(prompt, recruitment_data)
        if per_job:
            return per_job

        # The AI chooses; the server counts (CO-184). It used to type the chart's numbers itself from a text summary,
        # nothing compared them with the data, and asked for something the summary did not hold it still drew one.
        datasets = self._datasets(recruitment_data)
        system_prompt = (
            "You choose a chart for a recruitment dashboard. You never give numbers: the server fills them in.\n"
            "Reply with ONLY a JSON object: {\"dataset\": one of the names below or \"none\", \"chart_type\": "
            "\"bar\" | \"pie\" | \"line\" | \"area\", \"title\": a short title, \"top_n\": a number or null, "
            "\"order\": \"desc\" | \"asc\" | \"none\", \"orientation\": \"horizontal\" | \"vertical\" | null}.\n"
            "Use \"none\" when no data set below answers the request. Use the chart type the request names; with none "
            "named, trends over time are line charts. Give an orientation only when the request names one (vertical "
            "bars, columns or a histogram: vertical; sideways bars: horizontal), else null. A time series keeps "
            "\"order\": \"none\".\n\nData sets:\n"
            + "\n".join(f"- {name}: {about}{' (' + CHOICE_HINTS[name] + ')' if name in CHOICE_HINTS else ''}"
                        for name, (about, _) in datasets.items()))
        try:
            response_text = self.groq_client.send_prompt_text(system_prompt, f"Chart request: {prompt}")
            choice = json.loads(self._strip_fences(response_text))
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logger.error(f"Graph choice was not JSON: {e}")
            return self._generate_fallback_chart(prompt, recruitment_data)
        except KeyServiceError:
            raise
        except Exception as e:
            logger.error(f"Error generating graph: {e}")
            return self._generate_fallback_chart(prompt, recruitment_data)
        return self._fill(choice if isinstance(choice, dict) else {}, datasets, prompt)

    @staticmethod
    def _strip_fences(text):
        text = (text or '').strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1] if '\n' in text else ''
            text = text.rsplit('```', 1)[0]
        if text.startswith('json'):
            text = text[4:]
        return text.strip()

    @staticmethod
    def _datasets(d: Dict) -> Dict[str, Any]:
        """Each named data set the AI may choose: (what it holds, its values from the database)."""
        jobs, cands, ivs = d['jobs'], d['candidates'], d['interviews']
        sched = ivs.get('scheduling', {}) or {}
        slots = d.get('interview_settings', {}) or {}
        return {
            'jobs_active_inactive': ('active and inactive jobs', {'Active': jobs['active'], 'Inactive': jobs['inactive']}),
            'jobs_by_type': ('jobs by employment type', jobs['by_type']),
            'jobs_by_department': ('jobs by department', jobs['by_department']),
            'jobs_by_location': ('jobs by location', jobs['by_location']),
            'candidates_by_decision': ('candidates by screening decision', cands['by_decision']),
            'candidates_by_priority': ('candidates by priority', cands['by_priority']),
            'candidates_by_job': ('candidates (applicants) per job', cands['by_job']),
            'candidates_daily': ('candidates processed per day, last 30 days (trend)', cands['over_time_daily']),
            'candidates_weekly': ('candidates processed per week (trend)', cands.get('over_time_weekly') or []),
            'candidates_monthly': ('candidates processed per month (trend)', cands['over_time_monthly']),
            'interviews_by_status': ('interviews by status', ivs['by_status']),
            'interviews_by_outcome': ('interviews by outcome or decision (hired, rejected...)', ivs['by_outcome']),
            'interviews_by_type': ('online and onsite interviews', ivs['by_type']),
            'interviews_by_job': ('interviews per job role', ivs.get('by_job_role', {})),
            'interviews_by_date': ('interviews by the day they take place (two weeks back to a month ahead)',
                                   ivs.get('by_interview_date') or []),
            'interviews_daily': ('interviews made (candidates invited) per day, last 30 days (trend)',
                                 ivs['over_time_daily']),
            'interviews_monthly': ('interviews made per month (trend)', ivs['over_time_monthly']),
            'interviews_by_hour': ('interviews by hour of the day', sched.get('by_hour_of_day', {})),
            'interviews_by_weekday': ('interviews by day of the week', sched.get('by_day_of_week', {})),
            'slots_by_job': ('interview slots set up per job', slots.get('slots_by_job', {})),
            'slot_lengths': ('interview slot lengths in use', slots.get('time_gaps_distribution', {})),
        }

    def _fill(self, choice: Dict, datasets: Dict, prompt: str) -> Dict[str, Any]:
        name = str(choice.get('dataset') or 'none')
        if name not in datasets:
            return {'chart': None, 'insights': '', 'error': (
                "That chart can't be made from Recruitment's data. Charts can show: "
                + ', '.join(about for about, _ in datasets.values()) + '.')}
        about, values = datasets[name]
        chart_type = choice.get('chart_type') if choice.get('chart_type') in ('bar', 'pie', 'line', 'area') else 'bar'
        if isinstance(values, dict):
            items = [(str(k), v) for k, v in values.items() if isinstance(v, (int, float)) and v > 0]
            if choice.get('order') != 'none':
                items.sort(key=lambda kv: kv[1], reverse=choice.get('order') != 'asc')
            top_n = choice.get('top_n')
            if isinstance(top_n, int) and top_n > 0:
                items = items[:top_n]
            if chart_type in ('line', 'area'):
                data = [{'label': k, 'value': v} for k, v in items]
            else:
                data = dict(items)
            total = sum(v for _, v in items)
            highest = max(items, key=lambda kv: kv[1]) if items else None
            insights = (f"{total} in all; the most is {highest[0]} with {highest[1]}." if highest
                        else f"No {about} yet.")
        else:
            data = [row for row in values if isinstance(row, dict)]
            total = sum((row.get('value') or 0) for row in data)
            insights = f"{total} over the period shown." if data else f"No {about} yet."
            if chart_type in ('bar', 'pie'):
                # Asked for bars (or a pie): drawn so, one per day or month, in time order. It was always a line.
                data = {str(row.get('label')): row.get('value') or 0 for row in data}
        colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']
        chart = {'type': chart_type, 'title': str(choice.get('title') or about.capitalize())[:120], 'data': data,
                 'colors': colors, 'color': colors[0]}
        if chart_type == 'bar':
            # Days and months read left to right: a time series is upright unless asked otherwise.
            upright = choice.get('orientation') == 'vertical' or (isinstance(values, list) and choice.get('orientation') != 'horizontal')
            chart['orientation'] = 'vertical' if upright else 'horizontal'
        return {'chart': chart, 'insights': insights, 'dataset': name}

    def _decisions_per_job_chart(self, prompt: str, data: Dict) -> Optional[Dict[str, Any]]:
        """"Candidates per job by decision": one bar per job and decision, built here rather than by the AI.

        A chart holds one series, and the AI was given decision totals and job totals apart, so it drew three
        bars (Interview, Hold, Reject) for all jobs together. Bars are labelled "<job> · <decision>", a job's
        bars side by side.
        """
        p = prompt.lower()
        if not (re.search(r'\b(per|by|for each|each)\s+job', p) and re.search(r'decision|interview.*hold|hold.*reject', p)):
            return None
        per_job = data["candidates"].get("by_job_and_decision") or {}
        if not per_job:
            return None
        order = ['INTERVIEW', 'HOLD', 'REJECT']
        chart_data = {}
        for job, decisions in sorted(per_job.items(), key=lambda kv: -sum(kv[1].values())):
            for decision in sorted(decisions, key=lambda d: order.index(d) if d in order else len(order)):
                if decisions[decision]:
                    chart_data[f'{job} · {decision.title()}'] = decisions[decision]
        busiest = max(per_job.items(), key=lambda kv: sum(kv[1].values()))
        chart_type = 'pie' if 'pie' in p else 'bar'
        chart = {'type': chart_type, 'title': 'Candidates per job by decision', 'data': chart_data,
                 'colors': ['#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6', '#ec4899'], 'color': '#10b981'}
        if chart_type == 'bar':
            chart['orientation'] = 'vertical' if re.search(r'vertical|column|histogram', p) else 'horizontal'
        return {
            'chart': chart,
            'insights': (f'{busiest[0]} has the most candidates ({sum(busiest[1].values())}): '
                         + ', '.join(f'{n} {d.title()}' for d, n in busiest[1].items()) + '.'),
            'raw_data': data,
        }

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
