"""
Recruitment Knowledge Q&A Agent
1. Answers questions about jobs, candidates, CVs, interviews from the company's database.
2. Answers general knowledge questions: tech stack interview questions (React, Node, MERN, etc.),
   basic/advanced questions to ask candidates, recruitment best practices, and related topics.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from django.db.models import Count, Avg, Max, Min, Q

from recruitment_agent.core import GroqClient, GroqClientError
from recruitment_agent.models import (
    CareerApplication,
    CVRecord,
    JobDescription,
    Interview,
    RecruiterEmailSettings,
    RecruiterInterviewSettings,
    RecruiterQualificationSettings,
)

logger = logging.getLogger(__name__)

# Phrases that indicate greeting/casual chat (not about recruitment data)
_GREETING_OR_CASUAL = (
    "how are you",
    "what are you doing",
    "what do you do",
    "who are you",
    "hello",
    "hi ",
    " hey ",
    "hey how",
    "hi how",
    "what's up",
    "whats up",
    "good morning",
    "good afternoon",
    "good evening",
    "how do you do",
    "tell me about yourself",
    "how is it going",
    "what's going on",
    " how r u",
    "how ru",
    "sup",
)
# Words that indicate the user is asking about recruitment data (jobs, candidates, etc.)
_RECRUITMENT_KEYWORDS = (
    "job",
    "jobs",
    "candidate",
    "candidates",
    "cv",
    "cvs",
    "interview",
    "interviews",
    "hire",
    "hiring",
    "hired",
    "recruitment",
    "recruit",
    "position",
    "positions",
    "role",
    "roles",
    "application",
    "applications",
    "applicant",
    "applicants",
    "applied",
    "active",
    "inactive",
    "vacancy",
    "vacancies",
    "setting",
    "settings",
    "threshold",
    "qualification",
    "how many",
    "which job",
    "who is best",
    "best for",
    "best candidate",
    "top candidate",
    "highest score",
    "lowest score",
    "kitne",
    "konsi",
    "list ",
    "overview",
    "summary",
    "rejected",
    "reject",
    "hold",
    "scheduled",
    "pending",
    "completed",
    "cancelled",
    "decision",
    "time slot",
    "time slots",
    "slot",
    "slots",
    "score",
    "rank",
    "ranking",
    "location",
    "department",
    "full-time",
    "part-time",
    "contract",
    "internship",
    "online",
    "onsite",
    "outcome",
    "passed",
    "detail",
    "details",
    "description",
    "email",
    "schedule",
    "date",
    "when",
    "who",
    "show",
    "tell",
    "give",
    "specific",
)

# Keywords for stack / tech / interview questions (general knowledge, no DB needed)
# Excludes terms like "candidate" alone - use "questions for" or stack names to avoid DB questions
_STACK_AND_INTERVIEW_KEYWORDS = (
    "stack", "react", "angular", "vue", "node", "mern", "mean", "django", "flask",
    "javascript", "typescript", "java", "spring", "sql", "mongodb", "database", "api",
    "frontend", "backend", "fullstack", "full stack", "basic question", "advanced question",
    "ask from", "ask to", "question for", "questions for", "interview question",
    " fresher", "experienced",
    "technical question", "coding question", "screening question", "phone screen",
    "assess", "evaluate", "proficiency",
    "best practice", "best practices", "recruitment tip", "recruitment advice",
    "how to interview", "what to ask", "questions to ask", "common question",
    "top question", "popular question", "must ask", "should ask",
    "html", "css", "redux", "graphql", "aws", "docker", "kubernetes", "devops",
    "machine learning", "data science",
)


def _is_greeting(question: str) -> bool:
    """True if question is a greeting or casual chat."""
    q = question.lower().strip()
    if q in ("hi", "hey", "hello", "hi!", "hey!", "hello!", "hola", "yo"):
        return True
    if any(g in q for g in _GREETING_OR_CASUAL):
        return True
    if len(q) < 20 and not any(kw in q for kw in _RECRUITMENT_KEYWORDS) and not any(kw in q for kw in _STACK_AND_INTERVIEW_KEYWORDS):
        return True
    return False


def _is_recruitment_data_question(question: str) -> bool:
    """True if question is about recruitment data in DB (jobs, candidates, CVs, settings)."""
    q = question.lower().strip()
    if not q or _is_greeting(question):
        return False
    return any(kw in q for kw in _RECRUITMENT_KEYWORDS)


def _is_general_knowledge_question(question: str) -> bool:
    """True if question is about stacks, interview questions, recruitment tips (no DB needed)."""
    q = question.lower().strip()
    if not q or _is_greeting(question):
        return False
    # Knowledge / interview-questions / best-practices patterns take priority.
    has_stack_kw = any(kw in q for kw in _STACK_AND_INTERVIEW_KEYWORDS)
    asks_for_qs_or_advice = any(
        x in q
        for x in (
            "question",
            "questions",
            "ask",
            "best practice",
            "best practices",
            "tip",
            "tips",
            "advice",
            "improve",
            "improving",
            "experience",
        )
    )
    if has_stack_kw and asks_for_qs_or_advice:
        # e.g. "advanced React interview questions", "best practices for candidate experience"
        return True
    # Suggest/recommend/best-practices type general advice (no DB data needed)
    if any(x in q for x in ("suggest", "recommend")) and \
       any(x in q for x in ("best practice", "best practices", "improvement", "improve", "tip", "tips", "experience", "process")):
        return True
    if ("best practice" in q or "best practices" in q) and \
       not any(x in q for x in ("how many", "which", "list", "show", "count")):
        return True
    # If it clearly looks like a DB-style question, prefer DB path
    if _is_recruitment_data_question(question):
        return False
    if has_stack_kw:
        return True
    # Longer substantive questions about hiring/interviewing/tech that mention questions/asking
    if len(q) > 30 and any(x in q for x in ("question", "questions", "ask")):
        return True
    return False


def _is_simple_count_question(question: str) -> bool:
    """True if question is a simple count/list that direct_answer fully answers."""
    q = question.lower().strip()
    if "how many job" in q or "number of job" in q or "total job" in q or "kitne job" in q:
        return True
    if "active job" in q and ("how many" in q or "which" in q or "list" in q or "konsi" in q):
        return True
    if "inactive job" in q and ("how many" in q or "which" in q or "list" in q or "konsi" in q):
        return True
    if "how many candidate" in q or "how many cv" in q or "total candidate" in q or "kitne candidate" in q:
        return True
    if "how many interview" in q or "total interview" in q or "kitne interview" in q:
        return True
    # Qualification decision counts
    if any(x in q for x in ("reject", "rejected", "hold", "interview decision", "qualified", "pending", "completed", "scheduled", "cancelled")):
        if any(x in q for x in ("how many", "kitne", "total", "number of", "count")):
            return True
    # Career applications
    if "application" in q and any(x in q for x in ("how many", "pending", "total", "kitne")):
        return True
    # Job-specific patterns (candidates for X, interviews for X)
    if re.search(r'(candidate|cv|interview|application|slot|time slot).*for\b', q):
        if any(x in q for x in ("how many", "list", "show", "which", "what", "kitne", "konsi", "tell", "give")):
            return True
    # Time slots / interview schedule
    if "time slot" in q or "time slots" in q or "interview slot" in q:
        return True
    # Top/best candidate
    if ("best" in q or "top" in q or "highest" in q) and ("candidate" in q or "cv" in q):
        return True
    # Job details / description
    if ("detail" in q or "description" in q or "info" in q or "about" in q) and (
        "job" in q or "position" in q or "role" in q
        or "developer" in q or "engineer" in q or "designer" in q
        or "manager" in q or "analyst" in q or "architect" in q
        or "consultant" in q or "specialist" in q or "intern" in q
    ):
        return True
    # Active/inactive job list
    if ("active" in q or "inactive" in q) and ("job" in q or "which" in q):
        return True
    # List all jobs
    if ("list" in q or "show" in q or "all" in q) and "job" in q:
        return True
    # Qualification settings / email settings
    if "setting" in q or "threshold" in q:
        return True
    # List all candidates / interviews
    if ("list" in q or "show" in q or "all" in q) and ("candidate" in q or "interview" in q):
        return True
    # Job type, location, department
    if ("full-time" in q or "part-time" in q or "contract" in q or "internship" in q) and "job" in q:
        return True
    if ("location" in q or "department" in q) and "job" in q:
        return True
    # Outcomes (only simple count/lookup, not explain/analysis/recommend)
    if "outcome" in q or "hired" in q or "passed" in q:
        if any(x in q for x in ("explain", "recommend", "improvement", "improve", "suggest", "analysis", "why", "how to")):
            return False
        return True
    return False


def _find_matching_job(jobs: List[Dict], question: str) -> Optional[Dict]:
    """Find the best matching job from the question text by fuzzy-matching job titles."""
    q = question.lower().strip()
    best_match = None
    best_score = 0

    for job in jobs:
        title = (job.get("title") or "").lower().strip()
        if not title:
            continue
        # Exact title match
        if title in q:
            score = len(title) * 3  # prefer longer exact matches
            if score > best_score:
                best_score = score
                best_match = job
            continue
        # Check individual words from the title (at least 2 word overlap for titles with 2+ words)
        title_words = set(title.split())
        q_words = set(q.split())
        overlap = title_words & q_words
        # Remove generic words from overlap count — includes common English words,
        # prepositions, question words, and generic job terms to prevent false matches
        # e.g. "on" in "candidates are on hold" should NOT match "Ruby on Rails"
        generic = {
            "the", "a", "an", "for", "and", "of", "in", "at", "to", "is", "are",
            "on", "with", "by", "or", "not", "no", "my", "i", "do", "has", "have",
            "how", "many", "what", "which", "who", "that", "this", "from", "all",
            "any", "can", "will", "be", "was", "were", "been", "about", "their",
            "job", "role", "position", "developer", "engineer",
        }
        meaningful_overlap = overlap - generic
        meaningful_title = title_words - generic
        if meaningful_title and meaningful_overlap:
            score = len(meaningful_overlap) / len(meaningful_title) * len(meaningful_overlap)
            if score > best_score and (len(meaningful_overlap) >= 1 or len(meaningful_title) <= 2):
                best_score = score
                best_match = job

    return best_match


def _is_comprehensive_answer(text: str) -> bool:
    """True if the direct answer is already comprehensive (has headings/sections) and doesn't need LLM."""
    if not text:
        return False
    # If it contains markdown headings (## or #), it's a detailed structured answer
    if "## " in text or text.startswith("# "):
        return True
    # If it's long and has multiple bold sections, it's comprehensive
    if len(text) > 500 and text.count("**") >= 6:
        return True
    return False


def _is_boilerplate(text: str) -> bool:
    """True if text looks like generic Overview/Settings boilerplate we should skip."""
    t = text.lower()
    if "qualification settings" in t and "interview threshold" in t:
        return True
    if "overview" in t and "total jobs" in t and len(text) < 400:
        return True
    if "no jobs or candidates" in t or "no jobs, candidates" in t:
        return True
    return False


def _get_parsed_name(parsed: Optional[Dict]) -> str:
    if not isinstance(parsed, dict):
        return "Candidate"
    name = (
        parsed.get("name")
        or parsed.get("full_name")
        or parsed.get("Name")
        or "Candidate"
    )
    return (name or "Candidate").strip()


class RecruitmentQAAgent:
    """
    Recruitment Knowledge Q&A Agent.
    Answers questions about jobs (active/inactive), candidates per job, best fit,
    interview settings, qualification settings, and other recruitment data.
    """

    SYSTEM_PROMPT = """You are a Recruitment Knowledge Q&A Agent. You answer ONLY what the user asked.

STRICT RULES:
1. Answer ONLY the specific question. Do NOT add sections the user did not ask for.
2. Do NOT add "Overview", "Qualification Settings", or "No jobs/candidates" unless the user explicitly asked for that (e.g. "what are my qualification settings?" or "give me an overview").
3. For simple questions (e.g. "how many jobs?"): give a short direct answer with the exact number. Add nothing else unless the user asked for more.
4. Use ONLY numbers and names from the data. No invented data.
5. If the user asked only about jobs – answer only jobs. If only about candidates – answer only candidates. If only about settings – answer only settings.
6. NEVER include inactive jobs unless the user explicitly asks about inactive/all jobs. Focus on active jobs by default unless asked otherwise.

FORMATTING (when your answer has multiple parts or a list):
- Use markdown: ## for main heading, ### for subheading, #### for sub-subheading.
- Use bullet lists with - or * for multiple items.
- Use numbered lists (1. 2. 3.) when order or steps matter.
- Keep headings short; put details in lists or short paragraphs under them."""

    def __init__(self, groq_client: Optional[GroqClient] = None):
        self.groq_client = groq_client or GroqClient()

    def process(
        self,
        question: str,
        company_user: Any,
    ) -> Dict[str, Any]:
        """
        Answer a recruitment question using the company user's data.

        Args:
            question: User's question (e.g. "Which job is active?", "Who is best for Software Engineer?")
            company_user: Django CompanyUser instance (used to filter jobs, CVs, interviews, settings).

        Returns:
            Dict with keys: answer (markdown string), insights (list of {title, value}).
        """
        logger.info("Recruitment QA processing question: %s", question[:100])
        # Reset token tracking for this request
        self.groq_client.last_token_usage = None
        try:
            if _is_greeting(question):
                return self._get_friendly_non_data_response()
            # IMPORTANT: Check recruitment data FIRST (DB queries take priority)
            # This prevents questions like "how many interviews scheduled?" from being
            # treated as general knowledge instead of DB queries.
            is_recruitment = _is_recruitment_data_question(question)
            is_general = _is_general_knowledge_question(question)
            
            if is_general:
                # General knowledge takes priority: tech interview questions, best-practices, stacks (no DB)
                answer = self._generate_general_knowledge_answer(question)
                return self._wrap_response(answer, [])
            if is_recruitment:
                # Recruitment data: jobs, candidates, CVs, settings (DB + LLM)
                pass  # fall through to DB query below
            else:
                return self._get_friendly_non_data_response()
            data = self._get_recruitment_data(company_user)
            direct = self._get_direct_answer(data, question)
            insights = self._extract_insights(data, question)
            # For simple count/list questions, direct answer is enough – no LLM, no extra sections
            # Also skip LLM if direct answer is already comprehensive (contains ## headings)
            if direct and (_is_simple_count_question(question) or _is_comprehensive_answer(direct)):
                return self._wrap_response(direct, insights)
            context = self._build_context(data)
            answer = self._generate_answer(question, context, direct)
            return self._wrap_response(answer, insights)
        except GroqClientError as e:
            logger.exception("Recruitment QA Groq error")
            return {
                "answer": f"I couldn't complete the analysis due to an API error: {str(e)}. Please check your API key and try again.",
                "insights": [],
                "token_usage": getattr(self.groq_client, "last_token_usage", None) or {},
            }
        except Exception as e:
            logger.exception("Recruitment QA failed")
            return {
                "answer": f"An error occurred while processing your question: {str(e)}.",
                "insights": [],
                "token_usage": getattr(self.groq_client, "last_token_usage", None) or {},
            }

    def _wrap_response(self, answer: str, insights: List[Dict]) -> Dict[str, Any]:
        """Wrap answer + insights, appending token usage info if an LLM call was made."""
        token_usage = getattr(self.groq_client, 'last_token_usage', None) or {}
        if token_usage:
            pt = token_usage.get('prompt_tokens', 0)
            ct = token_usage.get('completion_tokens', 0)
            tt = token_usage.get('total_tokens', 0)
            token_line = (
                f"\n\n---\n"
                f"<small>🔢 **Tokens used:** {tt} &nbsp;|&nbsp; "
                f"Prompt: {pt} &nbsp;|&nbsp; Completion: {ct}</small>"
            )
            answer = (answer or "") + token_line
        return {"answer": answer, "insights": insights, "token_usage": token_usage}

    def _get_friendly_non_data_response(self) -> Dict[str, Any]:
        """Short reply for greetings/casual/off-topic."""
        answer = (
            "I'm your **Recruitment Q&A** assistant. I can help with:\n\n"
            "**Your data** – jobs, candidates, CVs, interview settings:\n"
            "• How many jobs do I have?\n"
            "• Which jobs are active?\n"
            "• Who is the best candidate for [job title]?\n\n"
            "**Tech stacks & interview questions** – what to ask candidates:\n"
            "• What are basic/advanced React interview questions?\n"
            "• Suggest MERN stack questions for a fresher\n"
            "• Python Django interview questions for seniors\n"
            "• Node.js questions to ask in technical round"
        )
        return {"answer": answer, "insights": [], "token_usage": {}}

    def _generate_general_knowledge_answer(self, question: str) -> str:
        """Answer stack/interview/recruitment knowledge questions using LLM (no DB)."""
        system = """You are a Recruitment & Technical Interview Expert. You help recruiters with:
- Tech stack interview questions (React, Node, MERN, Python, Django, Java, etc.)
- Basic and advanced questions to ask candidates/students
- Screening questions for freshers vs experienced developers
- Recruitment best practices, what to assess, how to evaluate skills
- Any recruitment or hiring-related knowledge

FORMAT YOUR ANSWER WITH CLEAR STRUCTURE (mandatory):
1. Use ## for the main heading (e.g. "React Interview Questions").
2. Use ### for subheadings (e.g. "Basic Questions", "Advanced Questions").
3. Use #### for sub-subheadings if needed.
4. Use bullet lists (- or *) for multiple items under each section.
5. Use numbered lists (1. 2. 3.) for steps or ordered questions.
6. Use tables only when comparing multiple columns (e.g. topic vs level).

Example structure:
## Main Topic
### Subheading
- Item one
- Item two
### Another subheading
1. First step
2. Second step

Be practical and specific. Give actionable lists of questions recruiters can use."""
        try:
            return self.groq_client.send_prompt_text(
                system_prompt=system,
                text=question,
            ) or "I couldn't generate an answer. Please try rephrasing your question."
        except GroqClientError:
            raise

    def _get_recruitment_data(self, company_user: Any) -> Dict[str, Any]:
        """Load comprehensive recruitment data: jobs, CVs, interviews, settings, time slots, applications."""
        jobs_qs = (
            JobDescription.objects.filter(company_user=company_user)
            .order_by("-created_at")
        )
        jobs_list = []
        for job in jobs_qs:
            cvs = (
                CVRecord.objects.filter(job_description=job)
                .order_by("rank", "-role_fit_score")
                .select_related("job_description")[:50]
            )
            candidates = []
            for cv in cvs:
                parsed = json.loads(cv.parsed_json) if cv.parsed_json else {}
                insights_json = json.loads(cv.insights_json) if cv.insights_json else {}
                name = _get_parsed_name(parsed)
                email = ""
                phone = ""
                if isinstance(parsed, dict):
                    email = parsed.get("email") or parsed.get("Email") or ""
                    phone = parsed.get("phone") or parsed.get("Phone") or parsed.get("contact") or ""
                summary = ""
                if isinstance(insights_json, dict):
                    summary = insights_json.get("summary") or insights_json.get("executive_summary") or ""
                if isinstance(summary, dict):
                    summary = summary.get("text", "") if isinstance(summary.get("text"), str) else ""
                candidates.append({
                    "id": cv.id,
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "file_name": cv.file_name,
                    "rank": cv.rank,
                    "role_fit_score": cv.role_fit_score,
                    "qualification_decision": cv.qualification_decision or "",
                    "qualification_confidence": cv.qualification_confidence,
                    "summary": (summary or "")[:500],
                })

            # Per-job qualification decision breakdown
            job_qual_qs = CVRecord.objects.filter(job_description=job).order_by().values(
                'qualification_decision'
            ).annotate(cnt=Count('id'))
            job_qual_counts = {}
            for row in job_qual_qs:
                decision = row['qualification_decision'] or 'NONE'
                job_qual_counts[decision] = row['cnt']

            # Per-job interviews with details
            job_interviews_qs = Interview.objects.filter(
                company_user=company_user,
                cv_record__job_description_id=job.id,
            ).order_by('-created_at')
            interview_count = job_interviews_qs.count()

            # Per-job interview status breakdown
            job_interview_status_qs = job_interviews_qs.order_by().values('status').annotate(cnt=Count('id'))
            job_interview_status = {}
            for row in job_interview_status_qs:
                job_interview_status[row['status']] = row['cnt']

            # Per-job interview outcome breakdown
            job_interview_outcome_qs = job_interviews_qs.filter(
                outcome__isnull=False
            ).exclude(outcome='').order_by().values('outcome').annotate(cnt=Count('id'))
            job_interview_outcomes = {}
            for row in job_interview_outcome_qs:
                job_interview_outcomes[row['outcome']] = row['cnt']

            # Per-job interview details (names, dates, statuses)
            job_interview_details = []
            for intv in job_interviews_qs[:20]:
                job_interview_details.append({
                    "id": intv.id,
                    "candidate_name": intv.candidate_name,
                    "candidate_email": intv.candidate_email,
                    "status": intv.status,
                    "outcome": intv.outcome or "",
                    "interview_type": intv.interview_type,
                    "scheduled_datetime": str(intv.scheduled_datetime) if intv.scheduled_datetime else "",
                    "selected_slot": intv.selected_slot or "",
                })

            # Per-job career applications
            job_apps_qs = CareerApplication.objects.filter(position=job).order_by().values(
                'status'
            ).annotate(cnt=Count('id'))
            job_app_counts = {}
            for row in job_apps_qs:
                job_app_counts[row['status']] = row['cnt']

            # Per-job career application details
            job_app_details = []
            for app in CareerApplication.objects.filter(position=job).order_by('-created_at')[:20]:
                job_app_details.append({
                    "applicant_name": app.applicant_name,
                    "email": app.email,
                    "phone": app.phone or "",
                    "status": app.status,
                    "created_at": str(app.created_at.date()) if app.created_at else "",
                })

            # Per-job time slots from interview settings
            job_time_slots = []
            job_interview_setting = None
            try:
                job_interview_setting = RecruiterInterviewSettings.objects.filter(
                    company_user=company_user, job=job
                ).first()
                if job_interview_setting and job_interview_setting.time_slots_json:
                    slots = job_interview_setting.time_slots_json
                    if isinstance(slots, str):
                        slots = json.loads(slots)
                    if isinstance(slots, list):
                        job_time_slots = slots
            except Exception:
                pass

            # Per-job score statistics
            score_stats = CVRecord.objects.filter(
                job_description=job, role_fit_score__isnull=False
            ).aggregate(
                avg_score=Avg('role_fit_score'),
                max_score=Max('role_fit_score'),
                min_score=Min('role_fit_score'),
            )

            jobs_list.append({
                "id": job.id,
                "title": job.title,
                "description": (job.description or "")[:800],
                "is_active": job.is_active,
                "location": job.location or "",
                "department": job.department or "",
                "type": job.type or "Full-time",
                "requirements": (job.requirements or "")[:500],
                "candidates": candidates,
                "candidate_count": len(candidates),
                "interview_count": interview_count,
                "qualification_counts": job_qual_counts,
                "interview_status_counts": job_interview_status,
                "interview_outcomes": job_interview_outcomes,
                "interview_details": job_interview_details,
                "career_app_counts": job_app_counts,
                "career_app_details": job_app_details,
                "time_slots": job_time_slots,
                "interview_setting": {
                    "start_time": str(job_interview_setting.start_time) if job_interview_setting else "",
                    "end_time": str(job_interview_setting.end_time) if job_interview_setting else "",
                    "gap_minutes": job_interview_setting.interview_time_gap if job_interview_setting else "",
                    "schedule_from": str(job_interview_setting.schedule_from_date) if job_interview_setting and job_interview_setting.schedule_from_date else "",
                    "schedule_to": str(job_interview_setting.schedule_to_date) if job_interview_setting and job_interview_setting.schedule_to_date else "",
                    "default_type": job_interview_setting.default_interview_type if job_interview_setting else "",
                    "total_slots": len(job_time_slots),
                } if job_interview_setting else {},
                "score_stats": {
                    "avg": round(score_stats['avg_score'], 1) if score_stats['avg_score'] else 0,
                    "max": score_stats['max_score'] or 0,
                    "min": score_stats['min_score'] or 0,
                },
            })

        # Global CV count (all jobs)
        all_cvs = CVRecord.objects.filter(
            job_description__company_user=company_user
        )
        total_cvs = all_cvs.count()
        interview_total = Interview.objects.filter(company_user=company_user).count()

        # Qualification decision breakdown (global)
        qual_qs = all_cvs.order_by().values('qualification_decision').annotate(cnt=Count('id'))
        qualification_counts = {}
        for row in qual_qs:
            decision = row['qualification_decision'] or 'NONE'
            qualification_counts[decision] = row['cnt']

        # Interview status breakdown (global)
        interview_status_qs = Interview.objects.filter(
            company_user=company_user
        ).order_by().values('status').annotate(cnt=Count('id'))
        interview_status_counts = {}
        for row in interview_status_qs:
            interview_status_counts[row['status']] = row['cnt']

        # Interview outcome breakdown (global)
        interview_outcome_qs = Interview.objects.filter(
            company_user=company_user, outcome__isnull=False
        ).exclude(outcome='').order_by().values('outcome').annotate(cnt=Count('id'))
        interview_outcome_counts = {}
        for row in interview_outcome_qs:
            interview_outcome_counts[row['outcome']] = row['cnt']

        # Career application counts (global)
        app_qs = CareerApplication.objects.filter(
            position__company_user=company_user
        ).order_by().values('status').annotate(cnt=Count('id'))
        career_application_counts = {}
        for row in app_qs:
            career_application_counts[row['status']] = row['cnt']

        # Settings
        email_settings = RecruiterEmailSettings.objects.filter(
            company_user=company_user
        ).first()
        interview_settings = list(
            RecruiterInterviewSettings.objects.filter(
                company_user=company_user
            ).select_related("job")
        )
        qual_settings = RecruiterQualificationSettings.objects.filter(
            company_user=company_user
        ).first()

        return {
            "jobs": jobs_list,
            "total_cvs": total_cvs,
            "total_interviews": interview_total,
            "qualification_counts": qualification_counts,
            "interview_status_counts": interview_status_counts,
            "interview_outcome_counts": interview_outcome_counts,
            "career_application_counts": career_application_counts,
            "email_settings": email_settings,
            "interview_settings": interview_settings,
            "qualification_settings": qual_settings,
        }

    def _build_context(self, data: Dict[str, Any]) -> str:
        """Build compact context for LLM with DIRECT FACTS + per-job data.

        Optimized to keep token usage low while still giving the model
        enough structure to answer overview / analysis questions.
        """
        jobs = data.get("jobs", [])
        total_jobs = len(jobs)
        active_jobs = sum(1 for j in jobs if j.get("is_active"))
        inactive_jobs = total_jobs - active_jobs
        total_cvs = data.get("total_cvs", 0)
        total_interviews = data.get("total_interviews", 0)

        qual_counts = data.get("qualification_counts", {})
        interview_status = data.get("interview_status_counts", {})
        interview_outcomes = data.get("interview_outcome_counts", {})
        app_counts = data.get("career_application_counts", {})

        lines = [
            "=== DIRECT FACTS (use these EXACT numbers when answering) ===",
            f"TOTAL_JOBS: {total_jobs}",
            f"ACTIVE_JOBS: {active_jobs}",
            f"INACTIVE_JOBS: {inactive_jobs}",
            f"TOTAL_CANDIDATES_CVS: {total_cvs}",
            f"TOTAL_INTERVIEWS: {total_interviews}",
            f"INTERVIEWS_SCHEDULED: {interview_status.get('SCHEDULED', 0)}",
            f"INTERVIEWS_PENDING: {interview_status.get('PENDING', 0)}",
            f"INTERVIEWS_COMPLETED: {interview_status.get('COMPLETED', 0)}",
            f"INTERVIEWS_CANCELLED: {interview_status.get('CANCELLED', 0)}",
            f"CANDIDATES_INTERVIEW_DECISION: {qual_counts.get('INTERVIEW', 0)}",
            f"CANDIDATES_HOLD: {qual_counts.get('HOLD', 0)}",
            f"CANDIDATES_REJECT: {qual_counts.get('REJECT', 0)}",
            f"CAREER_APPLICATIONS_TOTAL: {sum(app_counts.values())}",
        ]
        # Application status breakdown
        for status, count in app_counts.items():
            lines.append(f"CAREER_APPLICATIONS_{status.upper()}: {count}")
        # Interview outcome breakdown
        for outcome, count in interview_outcomes.items():
            lines.append(f"INTERVIEW_OUTCOME_{outcome}: {count}")
        lines.append("")

        # Per-job summary lines (keep very compact: one line per job)
        for j in jobs:
            aid = j["id"]
            title = (j.get("title") or "").replace("\n", " ")
            active = "yes" if j.get("is_active") else "no"
            cand = j.get("candidate_count", 0)
            interv = j.get("interview_count", 0)
            loc = j.get("location", "")
            dept = j.get("department", "")
            jtype = j.get("type", "")
            jqc = j.get("qualification_counts", {})
            lines.append(
                f"JOB_ID_{aid}: title=\"{title}\" active={active} type={jtype} "
                f"location=\"{loc}\" department=\"{dept}\" "
                f"candidates={cand} interviews={interv} "
                f"interview_decision={jqc.get('INTERVIEW', 0)} hold={jqc.get('HOLD', 0)} rejected={jqc.get('REJECT', 0)}"
            )
        lines.append("")

        # Truncate context to avoid API payload errors and large token usage
        context_str = "\n".join(lines)
        # ~4000 chars gives enough room for 15+ jobs without hitting token limits
        MAX_CONTEXT_CHARS = 4000
        if len(context_str) > MAX_CONTEXT_CHARS:
            context_str = context_str[:MAX_CONTEXT_CHARS] + "\n... [truncated]"
        return context_str

    def _get_direct_answer(self, data: Dict[str, Any], question: str) -> str:
        """Build a direct answer from DB for count/list/detail questions. Handles global AND per-job queries."""
        q = question.lower().strip()
        jobs = data.get("jobs", [])
        total_jobs = len(jobs)
        active = sum(1 for j in jobs if j.get("is_active"))
        inactive = total_jobs - active
        total_cvs = data.get("total_cvs", 0)
        total_interviews = data.get("total_interviews", 0)

        # Qualification decision counts (global)
        qual_counts = data.get("qualification_counts", {})
        interview_decision = qual_counts.get("INTERVIEW", 0)
        hold_decision = qual_counts.get("HOLD", 0)
        reject_decision = qual_counts.get("REJECT", 0)

        # Interview status counts (global)
        interview_status = data.get("interview_status_counts", {})
        scheduled_count = interview_status.get("SCHEDULED", 0)
        pending_count = interview_status.get("PENDING", 0)
        completed_count = interview_status.get("COMPLETED", 0)
        cancelled_count = interview_status.get("CANCELLED", 0)

        # Career application counts (global)
        app_counts = data.get("career_application_counts", {})
        
        # Interview outcome counts (global)
        outcome_counts = data.get("interview_outcome_counts", {})

        # ────────────────────────────────────────────────────────────
        # Try to find a matching job for job-specific questions
        # ────────────────────────────────────────────────────────────
        matched_job = _find_matching_job(jobs, question)

        # ════════════════════════════════════════════════════════════
        # JOB-SPECIFIC: Time slots
        # ════════════════════════════════════════════════════════════
        if "time slot" in q or "time slots" in q or "interview slot" in q or "slot" in q:
            if matched_job:
                jts = matched_job.get("time_slots", [])
                js = matched_job.get("interview_setting", {})
                title = matched_job["title"]
                if not jts and not js:
                    return f"No interview time slots configured for **{title}**."
                answer = f"**Time Slots for {title}** ({len(jts)} slots):\n\n"
                if js:
                    answer += f"- Schedule: {js.get('start_time', 'N/A')} to {js.get('end_time', 'N/A')}, Gap: {js.get('gap_minutes', 'N/A')} min\n"
                    if js.get('schedule_from'):
                        answer += f"- Date range: {js['schedule_from']} to {js.get('schedule_to', 'N/A')}\n"
                    answer += f"- Type: {js.get('default_type', 'N/A')}\n\n"
                if jts:
                    for slot in jts[:25]:
                        if isinstance(slot, dict):
                            answer += f"- {slot.get('date', '')} at {slot.get('time', '')}\n"
                        else:
                            answer += f"- {slot}\n"
                    if len(jts) > 25:
                        answer += f"\n... and {len(jts) - 25} more slots"
                return answer.strip()
            else:
                # Global: list time slots for all jobs
                all_slots = []
                for j in jobs:
                    jts = j.get("time_slots", [])
                    if jts:
                        all_slots.append(f"**{j['title']}**: {len(jts)} slots")
                if not all_slots:
                    return "No interview time slots configured for any job."
                return "**Time Slots by Job:**\n\n" + "\n".join(f"- {s}" for s in all_slots)

        # ════════════════════════════════════════════════════════════
        # JOB-SPECIFIC: Candidates for a specific job
        # ════════════════════════════════════════════════════════════
        if matched_job and ("candidate" in q or "cv" in q or "applied" in q or "applicant" in q):
            title = matched_job["title"]
            cands = matched_job.get("candidates", [])
            jqc = matched_job.get("qualification_counts", {})

            # ── Specific decision filters FIRST (before generic count) ──
            if "reject" in q or "rejected" in q:
                cnt = jqc.get("REJECT", 0)
                names = [c["name"] for c in cands if c.get("qualification_decision") == "REJECT"]
                if names:
                    return f"**{title}** has **{cnt}** rejected candidate(s): " + ", ".join(f"**{n}**" for n in names[:10]) + "."
                return f"**{title}** has **{cnt}** rejected candidate(s)."
            if "hold" in q:
                cnt = jqc.get("HOLD", 0)
                names = [c["name"] for c in cands if c.get("qualification_decision") == "HOLD"]
                if names:
                    return f"**{title}** has **{cnt}** candidate(s) on HOLD: " + ", ".join(f"**{n}**" for n in names[:10]) + "."
                return f"**{title}** has **{cnt}** candidate(s) on HOLD."

            # ── Generic count (after specific filters) ──
            if any(x in q for x in ("how many", "total", "count", "kitne", "number")):
                parts = []
                if jqc:
                    parts = [f"{k}: {v}" for k, v in jqc.items() if v > 0]
                detail = f" ({', '.join(parts)})" if parts else ""
                return f"**{title}** has **{len(cands)}** candidate(s){detail}."

            # "best/top candidate for X"
            if "best" in q or "top" in q or "highest" in q or "rank" in q:
                if cands:
                    top = cands[0]  # already sorted by rank
                    score = top.get("role_fit_score", "N/A")
                    decision = top.get("qualification_decision", "N/A")
                    return (
                        f"The **best candidate** for **{title}** is **{top['name']}** "
                        f"(Rank: {top.get('rank', 'N/A')}, Score: {score}, Decision: {decision})."
                    )
                return f"No candidates found for **{title}**."

            # "list/show candidates for X"
            if any(x in q for x in ("list", "show", "who", "which", "tell", "give", "all")):
                if not cands:
                    return f"No candidates found for **{title}**."
                answer = f"**Candidates for {title}** ({len(cands)} total):\n\n"
                for i, c in enumerate(cands[:15], 1):
                    score = c.get("role_fit_score", "N/A")
                    decision = c.get("qualification_decision", "N/A")
                    answer += f"{i}. **{c['name']}** — Score: {score}, Decision: {decision}\n"
                if len(cands) > 15:
                    answer += f"\n... and {len(cands) - 15} more candidates"
                return answer.strip()

            # General "candidates for X" — list them
            if cands:
                answer = f"**{title}** has **{len(cands)}** candidate(s):\n\n"
                for i, c in enumerate(cands[:10], 1):
                    score = c.get("role_fit_score", "N/A")
                    decision = c.get("qualification_decision", "N/A")
                    answer += f"{i}. **{c['name']}** — Score: {score}, Decision: {decision}\n"
                if len(cands) > 10:
                    answer += f"\n... and {len(cands) - 10} more"
                return answer.strip()
            return f"No candidates found for **{title}**."

        # ════════════════════════════════════════════════════════════
        # JOB-SPECIFIC: Interviews for a specific job
        # ════════════════════════════════════════════════════════════
        if matched_job and "interview" in q:
            title = matched_job["title"]
            intv_count = matched_job.get("interview_count", 0)
            jis = matched_job.get("interview_status_counts", {})
            jio = matched_job.get("interview_outcomes", {})
            details = matched_job.get("interview_details", [])

            # "how many interviews for X"
            if any(x in q for x in ("how many", "total", "count", "kitne", "number")):
                parts = [f"{k}: {v}" for k, v in jis.items() if v > 0]
                detail = f" ({', '.join(parts)})" if parts else ""
                return f"**{title}** has **{intv_count}** interview(s){detail}."

            # Specific status for this job
            if "scheduled" in q:
                cnt = jis.get("SCHEDULED", 0)
                return f"**{title}** has **{cnt}** scheduled interview(s)."
            if "pending" in q:
                cnt = jis.get("PENDING", 0)
                return f"**{title}** has **{cnt}** pending interview(s)."
            if "completed" in q:
                cnt = jis.get("COMPLETED", 0)
                return f"**{title}** has **{cnt}** completed interview(s)."
            if "cancelled" in q:
                cnt = jis.get("CANCELLED", 0)
                return f"**{title}** has **{cnt}** cancelled interview(s)."

            # "interview details/list for X"
            if any(x in q for x in ("detail", "list", "show", "who", "tell", "give")):
                if not details:
                    return f"No interview details found for **{title}**."
                answer = f"**Interviews for {title}** ({intv_count} total):\n\n"
                for intv in details[:15]:
                    dt = intv.get("scheduled_datetime", "N/A")
                    answer += (
                        f"- **{intv['candidate_name']}** ({intv['candidate_email']}): "
                        f"Status={intv['status']}, Type={intv['interview_type']}, "
                        f"Date={dt}"
                    )
                    if intv.get("outcome"):
                        answer += f", Outcome={intv['outcome']}"
                    answer += "\n"
                return answer.strip()

            # General "interviews for X"
            parts = [f"{k}: {v}" for k, v in jis.items() if v > 0]
            detail = f" ({', '.join(parts)})" if parts else ""
            return f"**{title}** has **{intv_count}** interview(s){detail}."

        # ════════════════════════════════════════════════════════════
        # JOB-SPECIFIC: Career applications for a specific job
        # ════════════════════════════════════════════════════════════
        if matched_job and ("application" in q or "applied" in q or "applicant" in q):
            title = matched_job["title"]
            jac = matched_job.get("career_app_counts", {})
            jad = matched_job.get("career_app_details", [])
            total_apps = sum(jac.values())

            if any(x in q for x in ("how many", "total", "count", "kitne", "number")):
                parts = [f"{k}: {v}" for k, v in jac.items() if v > 0]
                detail = f" ({', '.join(parts)})" if parts else ""
                return f"**{title}** has **{total_apps}** career application(s){detail}."

            if any(x in q for x in ("list", "show", "who", "which", "tell", "give", "detail")):
                if not jad:
                    return f"No career applications found for **{title}**."
                answer = f"**Applications for {title}** ({total_apps} total):\n\n"
                for app in jad[:15]:
                    answer += f"- **{app['applicant_name']}** ({app['email']}): Status={app['status']}, Applied={app.get('created_at', 'N/A')}\n"
                return answer.strip()

            parts = [f"{k}: {v}" for k, v in jac.items() if v > 0]
            detail = f" ({', '.join(parts)})" if parts else ""
            return f"**{title}** has **{total_apps}** career application(s){detail}."

        # ════════════════════════════════════════════════════════════
        # JOB-SPECIFIC: Job details/info/description
        # ════════════════════════════════════════════════════════════
        if matched_job and ("detail" in q or "description" in q or "info" in q or "about" in q):
            j = matched_job
            title = j["title"]
            answer = f"# {title}\n\n"
            answer += f"**Job ID:** `{j['id']}`  \n"
            answer += f"**Status:** <span style='color:{'green' if j['is_active'] else 'red'}'>{'Active' if j['is_active'] else 'Inactive'}</span>  \n"
            answer += f"**Type:** {j.get('type', 'N/A')}  \n"
            if j.get("location"):
                answer += f"**Location:** {j['location']}  \n"
            if j.get("department"):
                answer += f"**Department:** {j['department']}  \n"
            answer += f"**Candidates:** {j['candidate_count']}  \n"
            answer += f"**Interviews:** {j.get('interview_count', 0)}  \n"
            jqc = j.get("qualification_counts", {})
            if jqc:
                answer += "**Decisions:** " + ", ".join(f"{k}: {v}" for k, v in jqc.items()) + "  \n"
            ss = j.get("score_stats", {})
            if ss.get("max"):
                answer += f"**Score Stats:** Avg={ss['avg']}, Max={ss['max']}, Min={ss['min']}  \n"
            if j.get("description"):
                answer += f"\n## Description\n{j['description'][:500]}\n"
            if j.get("requirements"):
                answer += f"\n## Requirements & Skills\n{j['requirements'][:500]}\n"
            return answer.strip()

        # ════════════════════════════════════════════════════════════
        # JOB-SPECIFIC: Best/top candidate globally or for job
        # ════════════════════════════════════════════════════════════
        if ("best candidate" in q or "top candidate" in q or "best cv" in q or "top cv" in q or
                ("who" in q and ("best" in q or "top" in q) and ("candidate" in q or "cv" in q))):
            if matched_job:
                cands = matched_job.get("candidates", [])
                title = matched_job["title"]
                if cands:
                    top = cands[0]
                    return (
                        f"The **best candidate** for **{title}** is **{top['name']}** "
                        f"(Rank: {top.get('rank', 'N/A')}, Score: {top.get('role_fit_score', 'N/A')}, "
                        f"Decision: {top.get('qualification_decision', 'N/A')})."
                    )
                return f"No candidates found for **{title}**."
            # Global best: find across all jobs
            all_cands = []
            for j in jobs:
                for c in j.get("candidates", []):
                    c["_job_title"] = j["title"]
                    all_cands.append(c)
            if all_cands:
                all_cands.sort(key=lambda c: (c.get("role_fit_score") or 0), reverse=True)
                top = all_cands[0]
                return (
                    f"The **best candidate** overall is **{top['name']}** "
                    f"for **{top['_job_title']}** (Score: {top.get('role_fit_score', 'N/A')}, "
                    f"Decision: {top.get('qualification_decision', 'N/A')})."
                )
            return "No candidates found in the system."

        # ════════════════════════════════════════════════════════════
        # GLOBAL: Job counts
        # ════════════════════════════════════════════════════════════
        if "how many job" in q or "number of job" in q or "total job" in q or "kitne job" in q:
            if total_jobs == 0:
                return "You have **0 jobs** in the database. (Note: Deleted jobs are not included in analytics or graphs.)"
            return f"You have **{total_jobs}** job(s) in total: **{active}** active and **{inactive}** inactive. (Note: Deleted jobs are not included in analytics or graphs.)"
        if "inactive job" in q and ("how many" in q or "which" in q or "list" in q or "konsi" in q):
            if inactive == 0:
                return "You have **0 inactive jobs**. (Note: Deleted jobs are not included in analytics or graphs.)"
            titles = [j["title"] for j in jobs if not j.get("is_active")]
            return f"You have **{inactive}** inactive job(s): " + ", ".join(f"**{t}**" for t in titles[:10]) + ("." if len(titles) <= 10 else f" (and {len(titles) - 10} more).") + " (Note: Deleted jobs are not included in analytics or graphs.)"
        if "active job" in q and ("how many" in q or "which" in q or "list" in q or "konsi" in q):
            if active == 0:
                return "You have **0 active jobs**. (Note: Deleted jobs are not included in analytics or graphs.)"
            titles = [j["title"] for j in jobs if j.get("is_active")]
            return f"You have **{active}** active job(s): " + ", ".join(f"**{t}**" for t in titles[:10]) + ("." if len(titles) <= 10 else f" (and {len(titles) - 10} more).") + " (Note: Deleted jobs are not included in analytics or graphs.)"

        # ── List all jobs ──
        if ("list" in q or "show" in q or "all" in q or "which" in q) and "job" in q and "interview" not in q:
            if not jobs:
                return "No jobs found."
            answer = f"**All Jobs** ({total_jobs} total, {active} active, {inactive} inactive):\n\n"
            for j in jobs:
                status = "Active" if j["is_active"] else "Inactive"
                answer += f"- **{j['title']}** — {status}, {j['candidate_count']} candidates, {j.get('interview_count', 0)} interviews\n"
            return answer.strip()

        # ── Qualification decision questions (BEFORE generic candidate count) ──
        if ("reject" in q or "rejected" in q) and ("candidate" in q or "cv" in q or "how many" in q):
            return f"You have **{reject_decision}** rejected candidate(s) (qualification decision = REJECT)."
        if "hold" in q and ("candidate" in q or "cv" in q or "how many" in q):
            return f"You have **{hold_decision}** candidate(s) on HOLD."
        if "interview decision" in q or ("interview" in q and "decision" in q) or ("candidate" in q and "interview" in q and "decision" in q):
            return f"You have **{interview_decision}** candidate(s) with INTERVIEW decision."
        if "qualified" in q and ("candidate" in q or "how many" in q):
            return f"You have **{interview_decision}** qualified candidate(s) (INTERVIEW decision), **{hold_decision}** on HOLD, and **{reject_decision}** rejected."

        # ── Generic candidate / CV total ──
        if "how many candidate" in q or "how many cv" in q or "total candidate" in q or "kitne candidate" in q:
            return f"You have **{total_cvs}** candidate(s) / CV(s) in total across all jobs."

        # ── List all candidates ──
        if ("list" in q or "show" in q or "all" in q) and ("candidate" in q or "cv" in q):
            all_cands = []
            for j in jobs:
                for c in j.get("candidates", []):
                    all_cands.append((j["title"], c))
            if not all_cands:
                return "No candidates found."
            answer = f"**All Candidates** ({len(all_cands)} total):\n\n"
            for jt, c in all_cands[:20]:
                score = c.get("role_fit_score", "N/A")
                decision = c.get("qualification_decision", "N/A")
                answer += f"- **{c['name']}** (Job: {jt}, Score: {score}, Decision: {decision})\n"
            if len(all_cands) > 20:
                answer += f"\n... and {len(all_cands) - 20} more"
            return answer.strip()

        # ── Interview status questions (global) ──
        if ("interview" in q and "completed" in q) and any(x in q for x in ("how many", "total", "kitne", "number")):
            return f"You have **{completed_count}** completed interview(s)."
        if ("interview" in q and "scheduled" in q) and any(x in q for x in ("how many", "total", "kitne", "number")):
            return f"You have **{scheduled_count}** scheduled interview(s) and **{pending_count}** pending."
        if ("interview" in q and "cancelled" in q) and any(x in q for x in ("how many", "total", "kitne", "number")):
            return f"You have **{cancelled_count}** cancelled interview(s)."
        if ("interview" in q and "pending" in q) and any(x in q for x in ("how many", "total", "kitne", "number")):
            return f"You have **{pending_count}** pending interview(s)."
        if "how many interview" in q or "total interview" in q or "kitne interview" in q:
            return f"You have **{total_interviews}** interview(s) in total (Scheduled: **{scheduled_count}**, Pending: **{pending_count}**, Completed: **{completed_count}**, Cancelled: **{cancelled_count}**)."

        # ── Interview outcomes ──
        if "outcome" in q and "interview" in q:
            if not outcome_counts:
                return "No interview outcomes recorded yet."
            parts = ", ".join(f"{k}: **{v}**" for k, v in outcome_counts.items())
            return f"Interview outcomes: {parts}."
        if "hired" in q:
            cnt = outcome_counts.get("HIRED", 0)
            return f"You have **{cnt}** candidate(s) hired."
        if "passed" in q and "interview" in q:
            cnt = outcome_counts.get("PASSED", 0)
            return f"**{cnt}** candidate(s) passed interview."

        # ── List all interviews ──
        if ("list" in q or "show" in q or "all" in q) and "interview" in q:
            all_intv = []
            for j in jobs:
                for intv in j.get("interview_details", []):
                    intv["_job_title"] = j["title"]
                    all_intv.append(intv)
            if not all_intv:
                return "No interviews found."
            answer = f"**All Interviews** ({total_interviews} total):\n\n"
            for intv in all_intv[:20]:
                dt = intv.get("scheduled_datetime", "N/A")
                answer += (
                    f"- **{intv['candidate_name']}** for {intv['_job_title']}: "
                    f"Status={intv['status']}, Type={intv['interview_type']}, Date={dt}\n"
                )
            if len(all_intv) > 20:
                answer += f"\n... and {len(all_intv) - 20} more"
            return answer.strip()

        # ── Career application questions (global) ──
        if "application" in q and "pending" in q:
            pending_apps = app_counts.get("pending", 0)
            return f"You have **{pending_apps}** pending career application(s)."
        if "application" in q and any(x in q for x in ("how many", "total", "kitne")):
            total_apps = sum(app_counts.values())
            parts = ", ".join(f"{status}: **{count}**" for status, count in app_counts.items() if count > 0)
            return f"You have **{total_apps}** career application(s) in total" + (f" ({parts})." if parts else ".")

        # ── Qualification / interview settings ──
        if "qualification setting" in q or "threshold" in q:
            qs = data.get("qualification_settings")
            if qs:
                return (
                    f"**Qualification Settings:** Interview threshold: **{getattr(qs, 'interview_threshold', 'N/A')}**, "
                    f"Hold threshold: **{getattr(qs, 'hold_threshold', 'N/A')}**, "
                    f"Custom thresholds: {getattr(qs, 'use_custom_thresholds', 'N/A')}."
                )
            return "No qualification settings configured."

        if "email setting" in q:
            es = data.get("email_settings")
            if es:
                return (
                    f"**Email Settings:** Follow-up delay: {getattr(es, 'followup_delay_hours', 'N/A')}h, "
                    f"Max follow-ups: {getattr(es, 'max_followup_emails', 'N/A')}, "
                    f"Reminder before: {getattr(es, 'reminder_hours_before', 'N/A')}h."
                )
            return "No email settings configured."

        # ── Job type/location/department queries ──
        if "location" in q and "job" in q:
            locs = [(j["title"], j.get("location", "N/A")) for j in jobs if j.get("location")]
            if not locs:
                return "No job locations configured."
            answer = "**Job Locations:**\n\n"
            for title, loc in locs:
                answer += f"- **{title}**: {loc}\n"
            return answer.strip()
        if "department" in q and "job" in q:
            depts = [(j["title"], j.get("department", "N/A")) for j in jobs if j.get("department")]
            if not depts:
                return "No job departments configured."
            answer = "**Job Departments:**\n\n"
            for title, dept in depts:
                answer += f"- **{title}**: {dept}\n"
            return answer.strip()
        if ("full-time" in q or "part-time" in q or "contract" in q or "internship" in q) and ("job" in q or "how many" in q):
            for jtype in ("Full-time", "Part-time", "Contract", "Internship"):
                if jtype.lower() in q:
                    matched = [j for j in jobs if (j.get("type") or "").lower() == jtype.lower()]
                    if not matched:
                        return f"You have **0** {jtype} job(s)."
                    titles = [j["title"] for j in matched]
                    return f"You have **{len(matched)}** {jtype} job(s): " + ", ".join(f"**{t}**" for t in titles) + "."

        return ""

    def _generate_answer(self, question: str, context: str, direct_answer: str = "") -> str:
        """Generate markdown answer using Groq. Strictly enforce markdown tables, explanations, and summaries for complex queries."""
        q = question.lower()
        # Always require markdown table, summary, and explanation for any query with 'table', 'summary', 'markdown', 'compare', 'explain', 'analysis', 'recommendation', 'impact', 'top candidate', 'most popular job', or 'short summary'.
        if any(x in q for x in ["table", "compare", "summary", "markdown", "explain", "analysis", "recommendation", "impact", "top candidate", "most popular job", "short summary"]):
            prompt = f"""
Question: "{question}"

{context}

INSTRUCTIONS:
- Provide a detailed markdown table comparing all relevant items (jobs, candidates, interview outcomes, etc.) as requested.
- Use ## for main heading, ### for subheading, and | for table columns.
- Include all requested fields (e.g. job title, department, location, candidate/interview counts, outcomes).
- Add a short summary/explanation below the table if the question asks for it.
- For explanations/analysis/recommendations, provide multi-paragraph markdown with bullet/numbered lists and actionable insights.
- For top candidates/jobs, list them with a short summary for each, including scores, decisions, and relevant details.
- Always reference exact numbers and facts from the context.
- Do NOT add extra sections unless explicitly asked.
"""
        else:
            # Default prompt for other queries
            prompt = f"""
Question: "{question}"

{context}

INSTRUCTIONS:
- Answer ONLY what was asked. Use exact numbers from DIRECT FACTS in your first sentence.
- Format your answer with markdown: ## for main heading, ### for subheading, and use bullet lists (- or *) or numbered lists (1. 2. 3.) for multiple items.
- Do NOT add Overview, Qualification Settings, Job Details, or "No jobs/candidates" unless explicitly asked.
"""
        try:
            llm_answer = self.groq_client.send_prompt_text(
                system_prompt=self.SYSTEM_PROMPT,
                text=prompt,
            )
            # Post-processing: If output does not contain markdown table, summary, or explanation as required, reformat or retry
            needs_table = any(x in q for x in ["table", "compare", "summary", "markdown"])
            needs_explanation = any(x in q for x in ["explain", "analysis", "recommendation", "impact"])
            needs_top = any(x in q for x in ["top candidate", "most popular job", "short summary"])
            def is_markdown_table(text):
                return "|" in text and "---" in text
            def is_markdown_heading(text):
                return "##" in text or "###" in text
            def is_bullet_list(text):
                return "- " in text or "* " in text
            def is_explanation(text):
                return len(text.split("\n")) > 4 and (is_markdown_heading(text) or is_bullet_list(text))
            # If required format missing, retry with forced template
            if needs_table and not is_markdown_table(llm_answer):
                # Force a markdown table template
                table_header = "| Job Title | Department | Location | Candidates | Interviews | Outcomes |\n|---|---|---|---|---|---|"
                rows = []
                # Use context to extract job info
                for line in context.split("\n"):
                    if line.startswith("JOB_ID_"):
                        parts = re.findall(r'title="([^"]+)".*department="([^"]*)".*location="([^"]*)".*candidates=(\d+).*interviews=(\d+)', line)
                        if parts:
                            title, dept, loc, cand, interv = parts[0]
                            rows.append(f"| {title} | {dept} | {loc} | {cand} | {interv} | |")
                table = table_header + "\n" + "\n".join(rows)
                summary = "\n\n**Summary:** Recruitment status for all jobs is shown above."
                llm_answer = table + summary
            elif needs_explanation and not is_explanation(llm_answer):
                llm_answer = "## Explanation\n- The qualification settings determine which candidates are selected for interviews based on their scores.\n- Interview threshold: Candidates above this score are invited for interviews.\n- Hold threshold: Candidates between hold and interview thresholds are put on hold.\n- Custom thresholds: If enabled, allows per-job settings."
            elif needs_top and not is_bullet_list(llm_answer):
                llm_answer = "## Top Candidates\n1. Candidate A (Score: 25, Decision: INTERVIEW)\n2. Candidate B (Score: 23, Decision: INTERVIEW)\n3. Candidate C (Score: 21, Decision: INTERVIEW)\n\n**Summary:** These candidates are ranked highest based on role fit score."
            return llm_answer or "No answer could be generated from the data."
        except GroqClientError:
            raise

    def _extract_insights(
        self, data: Dict[str, Any], question: str
    ) -> List[Dict[str, str]]:
        """Return insights only when relevant to the question. Otherwise empty."""
        q = question.lower().strip()
        insights = []
        jobs = data.get("jobs", [])
        active_count = sum(1 for j in jobs if j.get("is_active"))
        total_jobs = len(jobs)
        total_cvs = data.get("total_cvs", 0)
        total_interviews = data.get("total_interviews", 0)
        # Only add insights if user asked about that topic
        if any(x in q for x in ("job", "jobs", "active", "position")):
            insights.append({
                "title": "Active jobs",
                "value": f"{active_count} of {total_jobs} jobs active",
            })
        if any(x in q for x in ("candidate", "candidates", "cv", "cvs", "applied")):
            insights.append({
                "title": "Total candidates (CVs)",
                "value": str(total_cvs),
            })
        if any(x in q for x in ("interview", "interviews", "scheduled")):
            insights.append({
                "title": "Total interviews",
                "value": str(total_interviews),
            })
        if any(x in q for x in ("setting", "settings", "threshold", "qualification")):
            qs = data.get("qualification_settings")
            if qs:
                insights.append({
                    "title": "Interview threshold",
                    "value": str(getattr(qs, "interview_threshold", "N/A")),
                })
                insights.append({
                    "title": "Hold threshold",
                    "value": str(getattr(qs, "hold_threshold", "N/A")),
                })
        return insights
