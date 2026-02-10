"""
Recruitment Knowledge Q&A Agent
1. Answers questions about jobs, candidates, CVs, interviews from the company's database.
2. Answers general knowledge questions: tech stack interview questions (React, Node, MERN, etc.),
   basic/advanced questions to ask candidates, recruitment best practices, and related topics.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from recruitment_agent.core import GroqClient, GroqClientError
from recruitment_agent.models import (
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
    "recruitment",
    "recruit",
    "position",
    "positions",
    "role",
    "roles",
    "application",
    "applications",
    "active",
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
    "kitne",
    "konsi",
    "list ",
    "overview",
    "summary",
)

# Keywords for stack / tech / interview questions (general knowledge, no DB needed)
# Excludes terms like "candidate" alone - use "questions for" or stack names to avoid DB questions
_STACK_AND_INTERVIEW_KEYWORDS = (
    "stack", "react", "angular", "vue", "node", "mern", "mean", "django", "flask", "python",
    "javascript", "typescript", "java", "spring", "sql", "mongodb", "database", "api",
    "frontend", "backend", "fullstack", "full stack", "basic question", "advanced question",
    "ask from", "ask to", "question for", "questions for", "interview question",
    "student", " fresher", "experienced", "junior", "senior",
    "technical question", "coding question", "screening question", "phone screen",
    "hire for", "assess", "evaluate", "skill", "skills", "proficiency",
    "best practice", "best practices", "recruitment tip", "recruitment advice",
    "how to interview", "what to ask", "questions to ask", "common question",
    "top question", "popular question", "must ask", "should ask",
    "html", "css", "redux", "graphql", "aws", "docker", "kubernetes", "devops",
    "machine learning", "data science", "ai ", " artificial intelligence",
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
    if any(kw in q for kw in _STACK_AND_INTERVIEW_KEYWORDS):
        return True
    # Longer substantive questions about hiring, interviewing, tech (even without keyword match)
    if len(q) > 30 and any(x in q for x in ("question", "ask", "hire", "interview", "recruit")):
        return True
    return False


def _is_simple_count_question(question: str) -> bool:
    """True if question is a simple count/list that direct_answer fully answers."""
    q = question.lower().strip()
    if "how many job" in q or "number of job" in q or "total job" in q or "kitne job" in q:
        return True
    if "active job" in q and ("how many" in q or "which" in q or "list" in q or "konsi" in q):
        return True
    if "how many candidate" in q or "how many cv" in q or "total candidate" in q or "kitne candidate" in q:
        return True
    if "how many interview" in q or "total interview" in q or "kitne interview" in q:
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
5. If the user asked only about jobs – answer only jobs. If only about candidates – answer only candidates. If only about settings – answer only settings."""

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
        try:
            if _is_greeting(question):
                return self._get_friendly_non_data_response()
            # General knowledge: stacks, interview questions, recruitment tips (no DB)
            if _is_general_knowledge_question(question):
                answer = self._generate_general_knowledge_answer(question)
                return {"answer": answer, "insights": []}
            # Recruitment data: jobs, candidates, CVs, settings (DB + LLM)
            if not _is_recruitment_data_question(question):
                return self._get_friendly_non_data_response()
            data = self._get_recruitment_data(company_user)
            direct = self._get_direct_answer(data, question)
            insights = self._extract_insights(data, question)
            # For simple count/list questions, direct answer is enough – no LLM, no extra sections
            if direct and _is_simple_count_question(question):
                return {"answer": direct, "insights": insights}
            context = self._build_context(data)
            answer = self._generate_answer(question, context, direct)
            return {
                "answer": answer,
                "insights": insights,
            }
        except GroqClientError as e:
            logger.exception("Recruitment QA Groq error")
            return {
                "answer": f"I couldn't complete the analysis due to an API error: {str(e)}. Please check your API key and try again.",
                "insights": [],
            }
        except Exception as e:
            logger.exception("Recruitment QA failed")
            return {
                "answer": f"An error occurred while processing your question: {str(e)}.",
                "insights": [],
            }

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
        return {"answer": answer, "insights": []}

    def _generate_general_knowledge_answer(self, question: str) -> str:
        """Answer stack/interview/recruitment knowledge questions using LLM (no DB)."""
        system = """You are a Recruitment & Technical Interview Expert. You help recruiters with:
- Tech stack interview questions (React, Node, MERN, Python, Django, Java, etc.)
- Basic and advanced questions to ask candidates/students
- Screening questions for freshers vs experienced developers
- Recruitment best practices, what to assess, how to evaluate skills
- Any recruitment or hiring-related knowledge

Format your answers in clear markdown: use ## for main sections, bullet points, and tables when helpful.
Be practical and specific. Give actionable lists of questions recruiters can use."""
        try:
            return self.groq_client.send_prompt_text(
                system_prompt=system,
                text=question,
            ) or "I couldn't generate an answer. Please try rephrasing your question."
        except GroqClientError:
            raise

    def _get_recruitment_data(self, company_user: Any) -> Dict[str, Any]:
        """Load jobs, CVs per job, interviews, and settings for this company user."""
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
                summary = ""
                if isinstance(insights_json, dict):
                    summary = insights_json.get("summary") or insights_json.get("executive_summary") or ""
                if isinstance(summary, dict):
                    summary = summary.get("text", "") if isinstance(summary.get("text"), str) else ""
                candidates.append({
                    "id": cv.id,
                    "name": name,
                    "file_name": cv.file_name,
                    "rank": cv.rank,
                    "role_fit_score": cv.role_fit_score,
                    "qualification_decision": cv.qualification_decision or "",
                    "qualification_confidence": cv.qualification_confidence,
                    "summary": (summary or "")[:500],
                })
            interview_count = Interview.objects.filter(
                company_user=company_user,
                cv_record__job_description_id=job.id,
            ).count()
            jobs_list.append({
                "id": job.id,
                "title": job.title,
                "description": (job.description or "")[:800],
                "is_active": job.is_active,
                "location": job.location,
                "department": job.department,
                "type": job.type,
                "candidates": candidates,
                "candidate_count": len(candidates),
                "interview_count": interview_count,
            })

        # Global CV count (all jobs)
        all_cvs = CVRecord.objects.filter(
            job_description__company_user=company_user
        )
        total_cvs = all_cvs.count()
        interview_total = Interview.objects.filter(company_user=company_user).count()

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
            "email_settings": email_settings,
            "interview_settings": interview_settings,
            "qualification_settings": qual_settings,
        }

    def _build_context(self, data: Dict[str, Any]) -> str:
        """Build a text context for the LLM from recruitment data. DIRECT FACTS first for exact answers."""
        jobs = data.get("jobs", [])
        total_jobs = len(jobs)
        active_jobs = sum(1 for j in jobs if j.get("is_active"))
        inactive_jobs = total_jobs - active_jobs
        total_cvs = data.get("total_cvs", 0)
        total_interviews = data.get("total_interviews", 0)

        lines = [
            "=== DIRECT FACTS (use these EXACT numbers in your first sentence) ===",
            f"TOTAL_JOBS: {total_jobs}",
            f"ACTIVE_JOBS: {active_jobs}",
            f"INACTIVE_JOBS: {inactive_jobs}",
            f"TOTAL_CANDIDATES_CVS: {total_cvs}",
            f"TOTAL_INTERVIEWS_SCHEDULED: {total_interviews}",
            "",
        ]
        for j in jobs:
            aid = j["id"]
            title = (j.get("title") or "").replace("\n", " ")
            active = "yes" if j.get("is_active") else "no"
            cand = j.get("candidate_count", 0)
            interv = j.get("interview_count", 0)
            lines.append(f"JOB_ID_{aid}: title=\"{title}\" active={active} candidates={cand} interviews={interv}")
        lines.append("")
        lines.append("=== DETAILED DATA (for lists and tables) ===\n")

        lines.append("OVERVIEW:")
        lines.append(f"- Total jobs: {total_jobs} (active: {active_jobs}, inactive: {inactive_jobs})")
        lines.append(f"- Total CVs/candidates across all jobs: {total_cvs}")
        lines.append(f"- Total interviews scheduled: {total_interviews}\n")

        for j in jobs:
            lines.append(f"--- JOB ID {j['id']}: {j['title']} ---")
            lines.append(f"  Active: {j['is_active']}")
            if j.get("location"):
                lines.append(f"  Location: {j['location']}")
            if j.get("department"):
                lines.append(f"  Department: {j['department']}")
            lines.append(f"  Candidates who applied (CVs): {j['candidate_count']}")
            lines.append(f"  Interviews for this job: {j.get('interview_count', 0)}")
            if j.get("candidates"):
                lines.append("  Top candidates (by rank / role_fit_score):")
                for i, c in enumerate(j["candidates"][:15], 1):
                    score = c.get("role_fit_score")
                    score_str = f", role_fit_score={score}" if score is not None else ""
                    lines.append(
                        f"    {i}. {c['name']} (ID={c['id']}, rank={c.get('rank')}{score_str}, "
                        f"decision={c.get('qualification_decision', 'N/A')})"
                    )
                    if c.get("summary"):
                        lines.append(f"       Summary: {c['summary'][:200]}...")
            lines.append("")

        # Settings summary
        es = data.get("email_settings")
        if es:
            lines.append("EMAIL SETTINGS (recruiter):")
            lines.append(f"  From email: {getattr(es, 'from_email', 'N/A')}")
            lines.append("")
        iss = data.get("interview_settings") or []
        if iss:
            lines.append("INTERVIEW SETTINGS (per job or default):")
            for s in iss[:10]:
                job_title = s.job.title if s.job else "Default (all jobs)"
                lines.append(
                    f"  {job_title}: gap={getattr(s, 'interview_time_gap', 'N/A')} min, "
                    f"start={getattr(s, 'start_time', 'N/A')}, end={getattr(s, 'end_time', 'N/A')}"
                )
            lines.append("")
        qs = data.get("qualification_settings")
        if qs:
            lines.append("QUALIFICATION SETTINGS:")
            lines.append(
                f"  Interview threshold: {getattr(qs, 'interview_threshold', 'N/A')}, "
                f"Hold threshold: {getattr(qs, 'hold_threshold', 'N/A')}"
            )
            lines.append("")

        return "\n".join(lines)

    def _get_direct_answer(self, data: Dict[str, Any], question: str) -> str:
        """Build a one-sentence direct answer from DB for count-style questions."""
        q = question.lower().strip()
        jobs = data.get("jobs", [])
        total_jobs = len(jobs)
        active = sum(1 for j in jobs if j.get("is_active"))
        inactive = total_jobs - active
        total_cvs = data.get("total_cvs", 0)
        total_interviews = data.get("total_interviews", 0)

        if "how many job" in q or "number of job" in q or "total job" in q or "kitne job" in q:
            if total_jobs == 0:
                return "You have **0 jobs** in the database."
            return f"You have **{total_jobs}** job(s) in total: **{active}** active and **{inactive}** inactive."
        if "active job" in q and ("how many" in q or "which" in q or "list" in q or "konsi" in q):
            if active == 0:
                return "You have **0 active jobs**."
            titles = [j["title"] for j in jobs if j.get("is_active")]
            return f"You have **{active}** active job(s): " + ", ".join(f"**{t}**" for t in titles[:10]) + ("." if len(titles) <= 10 else f" (and {len(titles) - 10} more).")
        if "how many candidate" in q or "how many cv" in q or "total candidate" in q or "kitne candidate" in q:
            return f"You have **{total_cvs}** candidate(s) / CV(s) in total across all jobs."
        if "how many interview" in q or "total interview" in q or "kitne interview" in q:
            return f"You have **{total_interviews}** scheduled interview(s)."
        return ""

    def _generate_answer(self, question: str, context: str, direct_answer: str = "") -> str:
        """Generate markdown answer using Groq. Answer ONLY what was asked."""
        if direct_answer:
            prompt = f"""Question: "{question}"

{context}

The user must see this EXACT first line (from database): "{direct_answer}"

Your job: Answer ONLY what was asked. If the first line above fully answers the question, add NOTHING or at most one short relevant sentence. Do NOT add Overview, Qualification Settings, Job Details, or any other section. No extra lists or tables unless the user asked for them."""
        else:
            prompt = f"""Question: "{question}"

{context}

INSTRUCTIONS: Answer ONLY this question. Use exact numbers from DIRECT FACTS in your first sentence. Do NOT add Overview, Qualification Settings, Job Details, or "No jobs/candidates" unless the user explicitly asked for that. If they asked "how many jobs" – give only the number and maybe job titles. If they asked "which jobs are active" – list only those. Nothing extra."""

        try:
            llm_answer = self.groq_client.send_prompt_text(
                system_prompt=self.SYSTEM_PROMPT,
                text=prompt,
            )
            if direct_answer and llm_answer:
                extra = llm_answer.strip()
                if extra and not _is_boilerplate(extra):
                    return direct_answer + "\n\n" + extra
                return direct_answer
            if direct_answer:
                return direct_answer
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
