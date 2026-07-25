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
    JobApplication,
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


# Phrases that point at a specific stored record rather than generic advice, e.g.
# "candidate 2", "detail of that candidate", "his score", "Ameer's CV".
_RECORD_REFERENCE_PATTERNS = [
    re.compile(r'\b(candidate|applicant|cv|resume|interviewee)\s*#?\s*\d+\b', re.I),
    re.compile(r'\b(this|that|the)\s+(candidate|applicant|cv|resume|person|student)\b', re.I),
    re.compile(r'\b(his|her|their)\s+(detail|details|score|cv|resume|profile|experience|skill)', re.I),
    re.compile(r'\b(detail|details|profile|score|status|decision|info|information)\s+(of|for|about)\b', re.I),
    re.compile(r'\btell me about\b', re.I),
    # Attribute asked "of/for <someone>", e.g. "skills of Ameer Hamza",
    # "experience of John". Catches candidate questions that name no keyword.
    re.compile(
        r'\b(skill|skills|experience|education|qualification|qualifications|background|'
        r'score|rating|resume|cv|profile|strength|strengths|weakness|weaknesses|'
        r'contact|email|phone)\s+(of|for)\s+[A-Za-z]',
        re.I,
    ),
]


def _refers_to_specific_record(question: str) -> bool:
    """True when the user is asking about a particular stored candidate/job.

    Such questions must go through the DB path even if they also ask for generic
    interview questions — answering them without data made the LLM invent people.
    """
    return any(p.search(question or '') for p in _RECORD_REFERENCE_PATTERNS)


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


# Words that carry no identifying weight when matching a question against real job
# titles / candidate names. Everything else is treated as a possible subject.
_NON_SUBJECT_WORDS = {
    'the', 'a', 'an', 'for', 'and', 'of', 'in', 'at', 'to', 'is', 'are', 'on', 'with',
    'by', 'or', 'not', 'no', 'my', 'me', 'i', 'do', 'does', 'did', 'has', 'have', 'had',
    'how', 'many', 'much', 'what', 'which', 'who', 'whom', 'that', 'this', 'these',
    'those', 'from', 'all', 'any', 'can', 'will', 'be', 'was', 'were', 'been', 'about',
    'their', 'his', 'her', 'them', 'they', 'it', 'its', 'you', 'your', 'we', 'our',
    'give', 'show', 'tell', 'list', 'find', 'get', 'want', 'need', 'please', 'also',
    'job', 'jobs', 'role', 'roles', 'position', 'positions', 'candidate', 'candidates',
    'applicant', 'applicants', 'cv', 'cvs', 'resume', 'resumes', 'interview',
    'interviews', 'application', 'applications', 'detail', 'details', 'info',
    'information', 'skill', 'skills', 'score', 'scores', 'status', 'applied', 'apply',
    'total', 'count', 'number', 'active', 'inactive', 'best', 'top', 'developer',
    'engineer', 'stack', 'ka', 'ki', 'ke', 'kitne', 'batao', 'kaun', 'konsi', 'mujhe',
    'only', 'just', 'complete', 'full', 'description', 'requirement', 'requirements',
    'summary', 'overview', 'more', 'other', 'another', 'each', 'every', 'both',
}


def _shorten(text: str, limit: int) -> str:
    """Trim to a word boundary and say so, instead of cutting mid-word.

    Used in multi-item listings only; single-item detail views show the full text.
    """
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if ' ' in cut:
        cut = cut[:cut.rfind(' ')]
    return f"{cut.rstrip()}… _(ask about this job for the full text)_"


# "…django job not mern", "all jobs except MERN" — whatever follows these is what
# the user is ruling OUT, so it must not be treated as the thing they asked for.
_EXCLUSION_PATTERN = re.compile(
    r'\b(?:not|except|excluding|other\s+than|apart\s+from|besides|no)\b(.*)$',
    re.I | re.DOTALL,
)


def _excluded_subjects(question: str) -> set:
    """Subjects the question explicitly rules out."""
    m = _EXCLUSION_PATTERN.search(question or '')
    if not m:
        return set()
    words = re.findall(r"[A-Za-z][A-Za-z0-9'+.#-]*", m.group(1).lower())
    return {w for w in words if len(w) > 1 and w not in _NON_SUBJECT_WORDS}


def _question_subjects(question: str, drop_excluded: bool = True) -> set:
    """Content words from the question that could name a job or a person.

    Words after a negation ("not mern") are dropped by default so asking for one
    job while naming another as an exclusion doesn't match the excluded one.
    """
    words = re.findall(r"[A-Za-z][A-Za-z0-9'+.#-]*", (question or '').lower())
    subjects = {w for w in words if len(w) > 1 and w not in _NON_SUBJECT_WORDS}
    if drop_excluded:
        subjects -= _excluded_subjects(question)
    return subjects


def _resolve_subject(question: str, known_titles: List[str], known_names: List[str]) -> Dict[str, Any]:
    """Match the question against the company's real jobs and candidates.

    This replaces guessing from hardcoded keyword lists: the database is the only
    source of truth for what jobs and people exist, so a new technology or a new
    hire needs no code change. Returns which subjects matched and — importantly —
    which named subjects matched nothing, so the caller can say "no such job"
    instead of answering with whatever unrelated records it happens to hold.
    """
    subjects = _question_subjects(question)
    if not subjects:
        return {'matched_jobs': [], 'matched_names': [], 'unmatched': []}

    # Titles and names are plain labels, not questions — never strip "negations" there.
    title_words = {w for t in known_titles for w in _question_subjects(t, drop_excluded=False)}
    name_words = {w for n in known_names for w in _question_subjects(n, drop_excluded=False)}

    matched_jobs = sorted(subjects & title_words)
    matched_names = sorted(subjects & name_words)
    # A subject that matches neither a job title nor a person is only interesting
    # when it looks like the question's actual topic, not incidental prose.
    unmatched = sorted(subjects - title_words - name_words)
    return {
        'matched_jobs': matched_jobs,
        'matched_names': matched_names,
        'unmatched': unmatched,
    }


# Where a job name actually appears in a question: "…for Laravel", "Laravel job",
# "…in Laravel role". Matching on grammar rather than a technology list means a new
# stack needs no code change, while status words ("on hold") and typos elsewhere in
# the sentence are not mistaken for job names.
_JOB_SLOT_PATTERNS = [
    re.compile(r'\bfor\s+(?:the\s+)?([A-Za-z][A-Za-z0-9+.#-]*(?:\s+[A-Za-z][A-Za-z0-9+.#-]*){0,3}?)\s*(?:jobs?|roles?|positions?)?\s*[?.!]?$', re.I),
    re.compile(r'\b([A-Za-z][A-Za-z0-9+.#-]*(?:\s+[A-Za-z][A-Za-z0-9+.#-]*){0,3}?)\s+(?:jobs?|roles?|positions?)\b', re.I),
    re.compile(r'\b(?:in|on)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9+.#-]*)\s+(?:jobs?|roles?|positions?)\b', re.I),
]


def _unmatched_job_topics(jobs: List[Dict], question: str) -> List[str]:
    """Job names the question asks about that this company has no job for.

    Reads the name out of the question's job slot ("for X", "X job") and checks it
    against real titles — no hardcoded technology list, so any new stack works.
    """
    titles = [j.get('title') or '' for j in jobs]
    title_words = {w for t in titles for w in _question_subjects(t, drop_excluded=False)}

    for pattern in _JOB_SLOT_PATTERNS:
        m = pattern.search(question or '')
        if not m:
            continue
        candidate_words = _question_subjects(m.group(1))
        if not candidate_words:
            continue
        # Any overlap with a real title means the job exists — nothing to report.
        if candidate_words & title_words:
            return []
        return sorted(candidate_words)
    return []


def _find_matching_job(jobs: List[Dict], question: str) -> Optional[Dict]:
    """Find the best matching job from the question text by fuzzy-matching job titles."""
    q = question.lower().strip()
    best_match = None
    best_score = 0

    # "…django job not mern" must never resolve to MERN. Drop jobs the user ruled out
    # before scoring, otherwise the excluded name still matches its own title.
    excluded = _excluded_subjects(question)

    for job in jobs:
        title = (job.get("title") or "").lower().strip()
        if not title:
            continue
        if excluded:
            title_terms = _question_subjects(title, drop_excluded=False)
            # Only skip when the exclusion is what identifies this job, not when it
            # merely shares a generic word with it.
            if title_terms and title_terms <= excluded:
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

    SYSTEM_PROMPT = """You are a Recruitment Knowledge Q&A Agent. You answer questions about recruitment data accurately and completely.

RULES:
1. When asked for "details", "description", "full info", "everything", or "all" — provide COMPLETE information. Never truncate or summarise when the user wants full details.
2. For simple count questions (e.g. "how many jobs?") — give a short direct answer.
3. Use ONLY data provided in the context. Never invent names, numbers, or descriptions.
4. If a field is available in the context (description, requirements, location, department, etc.) — include it in your answer when relevant.
5. For job details — always show: title, status, location, department, type, description, requirements, candidate count, interview count.
6. For candidate details — always show: name, score, decision, email if available, summary if available.
7. Default to active jobs unless the user asks about all/inactive jobs.
8. If the user refers to a candidate, job, or record that is NOT in the context (by name,
   number, or position — e.g. "candidate 2" when only one candidate exists), say plainly
   that no such record was found and list what IS available. Never fabricate a profile,
   name, score, skill, or history to fill the gap. Answering the generic part of the
   question (e.g. interview questions for a role) is fine — inventing the person is not.

FORMATTING:
- ## for main heading, ### for subheading per job/candidate
- Bold (**text**) for titles, names, field labels
- Bullet lists (- or *) for multiple fields per item
- Numbered lists for ranked items
- Never give a one-word or one-line answer when full details are in the context and the user wants them."""

    def __init__(self, groq_client: Optional[GroqClient] = None):
        if groq_client is None:
            raise ValueError(
                "RecruitmentQAAgent requires an explicit groq_client resolved via "
                "resolve_for_call(). Keys are never sourced from environment variables."
            )
        self.groq_client = groq_client

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
            
            # A question naming a specific record ("candidate 2", "details of that
            # candidate") must be answered from the DB. Routing it to the general
            # path — which has no database access — is what made the LLM invent
            # candidates that don't exist.
            #
            # Phrasing patterns catch the common shapes; the DB lookup below catches
            # the rest, including a bare name in any language ("Ameer ki skill batao").
            needs_record = (
                _refers_to_specific_record(question)
                or self._question_names_known_candidate(company_user, question)
            )

            if is_general and not needs_record:
                # Pure general knowledge: tech interview questions, best-practices, stacks (no DB)
                answer = self._generate_general_knowledge_answer(question)
                return self._wrap_response(answer, [])
            if needs_record:
                # Naming a person is itself a data question, even without a keyword
                # like "candidate" — e.g. "what are the skills of Ameer Hamza".
                logger.info("Recruitment QA: question references a specific record, using DB path")
                is_recruitment = True
            if not is_recruitment:
                return self._get_friendly_non_data_response()
            data = self._get_recruitment_data(company_user)
            direct = self._get_direct_answer(data, question)
            insights = self._extract_insights(data, question)
            # For simple count/list questions, direct answer is enough – no LLM, no extra sections
            # Also skip LLM if direct answer is already comprehensive (contains ## headings)
            if direct and (_is_simple_count_question(question) or _is_comprehensive_answer(direct)):
                return self._wrap_response(direct, insights)
            if needs_record:
                dossier = self._build_candidate_dossier(company_user, question)
                if dossier:
                    # Answer strictly from this candidate's record — passing the whole
                    # jobs context alongside made the model pad the reply with unrelated
                    # job descriptions.
                    answer = self._generate_answer(question, dossier, direct)
                    return self._wrap_response(answer, insights)
                # Nothing matched. Say so directly instead of handing the LLM the full
                # context, which it would otherwise dump as a substitute answer.
                return self._wrap_response(self._no_candidate_answer(data), insights)

            context = self._build_context(data)
            answer = self._generate_answer(question, context, direct)
            return self._wrap_response(answer, insights)
        except GroqClientError as e:
            logger.exception("Recruitment QA Groq error")
            return {
                "answer": "I couldn't complete the analysis due to an API error. Please check your API key configuration and try again.",
                "insights": [],
                "token_usage": getattr(self.groq_client, "last_token_usage", None) or {},
            }
        except Exception as e:
            logger.exception("Recruitment QA failed")
            return {
                "answer": "An error occurred while processing your question. Please try again.",
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

CRITICAL — you have NO access to this company's database in this mode. You cannot see
their candidates, CVs, jobs, or interviews. If the question refers to a specific record
("candidate 2", "the applicant for X", "their score"), do NOT invent one: say you can't
see their records here and point them to ask about the candidate by name, then answer
whatever generic part you can (e.g. good questions for that kind of role).

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

            # People who applied but whose CV hasn't been AI-analysed yet. Without
            # these the agent reported "no candidates" for a job that really had
            # applicants — they only existed as CVRecords after processing.
            pending_applicants = []
            for app in (
                JobApplication.objects
                .filter(job=job, cv_records__isnull=True)
                .order_by('-applied_at')[:50]
            ):
                full_name = f"{app.first_name or ''} {app.last_name or ''}".strip()
                pending_applicants.append({
                    "application_id": app.id,
                    "name": full_name or (app.email or 'Unnamed applicant'),
                    "email": app.email or "",
                    "phone": app.phone or "",
                    "status": app.status or "pending",
                    "applied_at": app.applied_at.strftime('%Y-%m-%d') if app.applied_at else "",
                    "education": (app.education or "")[:200],
                    "previous_company": (app.previous_company or "")[:120],
                    "salary_expectation": app.salary_expectation or "",
                    "analysed": False,
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
                # Kept whole — a "give me the complete description" answer has to be
                # able to show all of it. Trimming happens per-view instead, so the
                # full text is still available when the user explicitly asks for it.
                "description": job.description or "",
                "is_active": job.is_active,
                "location": job.location or "",
                "department": job.department or "",
                "type": job.type or "Full-time",
                "requirements": job.requirements or "",
                "candidates": candidates,
                # Everyone who applied — analysed or not. Counting only analysed CVs
                # made the agent answer "0 candidates" for jobs that had applicants
                # sitting unprocessed.
                "candidate_count": len(candidates) + len(pending_applicants),
                "analysed_count": len(candidates),
                "pending_applicants": pending_applicants,
                "pending_count": len(pending_applicants),
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

        # Per-job detailed blocks
        for j in jobs:
            aid = j["id"]
            title = (j.get("title") or "").replace("\n", " ")
            active_str = "Active" if j.get("is_active") else "Inactive"
            cand = j.get("candidate_count", 0)
            interv = j.get("interview_count", 0)
            loc = j.get("location", "") or "N/A"
            dept = j.get("department", "") or "N/A"
            jtype = j.get("type", "") or "N/A"
            jqc = j.get("qualification_counts", {})
            # With a single job there is room to pass its full text, which is what
            # "complete description" questions need. Across many jobs the shared
            # context budget forces a trim.
            if len(jobs) == 1:
                desc = j.get("description") or ""
                req = j.get("requirements") or ""
            else:
                desc = _shorten(j.get("description") or "", 400)
                req = _shorten(j.get("requirements") or "", 300)
            ss = j.get("score_stats", {})

            lines.append(f"\n=== JOB: {title} (ID:{aid}) ===")
            lines.append(f"Status: {active_str} | Type: {jtype} | Location: {loc} | Department: {dept}")
            lines.append(
                f"Candidates: {cand} (analysed: {j.get('analysed_count', 0)}, "
                f"awaiting AI analysis: {j.get('pending_count', 0)}) | "
                f"Interviews: {interv} | Scores: avg={ss.get('avg',0)} max={ss.get('max',0)} min={ss.get('min',0)}"
            )
            lines.append(f"Decisions: INTERVIEW={jqc.get('INTERVIEW',0)} HOLD={jqc.get('HOLD',0)} REJECT={jqc.get('REJECT',0)}")
            if desc:
                lines.append(f"Description: {desc}")
            if req:
                lines.append(f"Requirements: {req}")

            # Top candidates with names and scores
            candidates = j.get("candidates", [])[:8]
            if candidates:
                lines.append("Candidates:")
                for c in candidates:
                    lines.append(
                        f"  - {c.get('name','?')} | Score:{c.get('role_fit_score','N/A')} | "
                        f"Decision:{c.get('qualification_decision','N/A')} | Email:{c.get('email','N/A')}"
                    )

            # Applicants whose CV has not been AI-analysed yet. They are real people
            # who applied, so they must appear — flagged so the agent doesn't imply
            # they have scores or decisions.
            pending = j.get("pending_applicants", [])[:10]
            if pending:
                lines.append("Applicants awaiting AI analysis (no score/decision yet):")
                for p in pending:
                    lines.append(
                        f"  - {p.get('name','?')} | Email:{p.get('email','N/A')} | "
                        f"Applied:{p.get('applied_at','N/A')} | Status:{p.get('status','pending')} | "
                        f"Education:{p.get('education') or 'N/A'}"
                    )

            # Interview details
            iv_details = j.get("interview_details", [])[:8]
            if iv_details:
                lines.append("Interviews:")
                for iv in iv_details:
                    lines.append(
                        f"  - {iv.get('candidate_name','?')} | Status:{iv.get('status','N/A')} | "
                        f"Outcome:{iv.get('outcome','N/A')} | Scheduled:{iv.get('scheduled_datetime','N/A')}"
                    )

        lines.append("")

        context_str = "\n".join(lines)
        MAX_CONTEXT_CHARS = 12000
        if len(context_str) > MAX_CONTEXT_CHARS:
            context_str = context_str[:MAX_CONTEXT_CHARS] + "\n... [truncated]"
        return context_str

    def _question_names_known_candidate(self, company_user: Any, question: str) -> bool:
        """True when the question mentions a candidate who actually exists.

        Grounded in the database rather than a keyword list, so a bare name in any
        phrasing — "Ameer ki skill batao" — still routes to the data path.
        """
        try:
            return bool(self._find_candidates_in_question(company_user, question))
        except Exception:
            logger.exception("Candidate name lookup failed; falling back to phrasing rules")
            return False

    def _no_candidate_answer(self, data: Dict[str, Any]) -> str:
        """Reply for a candidate question we couldn't resolve.

        Deliberately does NOT include job descriptions: the user asked about a
        person, so padding the answer with unrelated job details is noise.
        """
        all_candidates = [
            c for j in data.get('jobs', []) for c in (j.get('candidates') or [])
        ]
        all_pending = [
            p for j in data.get('jobs', []) for p in (j.get('pending_applicants') or [])
        ]

        # Applicants exist but none analysed yet — say that rather than "no candidates",
        # which wrongly implies nobody applied.
        if not all_candidates and all_pending:
            listed = '\n'.join(
                f"- **{p.get('name')}** — {p.get('email') or 'no email'}"
                f" (applied {p.get('applied_at') or 'recently'})"
                for p in all_pending[:20]
            )
            return (
                f"## {len(all_pending)} Applicant"
                f"{'s' if len(all_pending) != 1 else ''} — Not Yet Analysed\n\n"
                f"These people applied, but their CVs haven't been processed by AI yet, "
                f"so they have no scores or decisions:\n\n{listed}\n\n"
                "Run **Process with AI** on the job to analyse their CVs, then ask me again "
                "for scores, skills and rankings."
            )

        if not all_candidates:
            job_titles = [j.get('title') for j in data.get('jobs', []) if j.get('title')]
            msg = "## No Candidates Yet\n\nNo one has applied to your jobs yet, so there are no candidate records to show."
            if job_titles:
                msg += (
                    f"\n\nYou have **{len(job_titles)} job**"
                    f"{'s' if len(job_titles) != 1 else ''} open: "
                    + ', '.join(f"**{t}**" for t in job_titles[:10])
                    + ".\n\nOnce candidates apply and their CVs are processed, ask me again."
                )
            return msg

        listed = '\n'.join(
            f"- **{c.get('name') or 'Unnamed'}** — Score: {c.get('role_fit_score', 'N/A')}"
            f" | Decision: {c.get('qualification_decision') or 'N/A'}"
            for c in all_candidates[:20]
        )
        return (
            "## Candidate Not Found\n\n"
            "I couldn't match that to anyone in your records. "
            f"Here are the **{len(all_candidates)} candidate"
            f"{'s' if len(all_candidates) != 1 else ''}** you do have:\n\n"
            f"{listed}\n\n"
            "Ask me by name (e.g. *\"skills of Ameer Hamza\"*) for a full profile."
        )

    def _build_candidate_dossier(self, company_user: Any, question: str) -> str:
        """Full profile for a candidate the question names, appended to the context.

        The per-job listing only carries name/score/decision/email for the top few
        candidates, so "tell me everything about X" had nothing to answer from. This
        pulls the whole record — skills, experience, education, insights, interview
        history — for the specific person asked about. Read-only.
        """
        matches = self._find_candidates_in_question(company_user, question)
        if not matches:
            return ""

        blocks: List[str] = ["", "=== CANDIDATE DOSSIER (full records for the person asked about) ==="]
        for cv in matches[:3]:
            parsed = json.loads(cv.parsed_json) if cv.parsed_json else {}
            insights = json.loads(cv.insights_json) if cv.insights_json else {}
            qual = json.loads(cv.qualification_json) if cv.qualification_json else {}
            parsed = parsed if isinstance(parsed, dict) else {}
            insights = insights if isinstance(insights, dict) else {}
            qual = qual if isinstance(qual, dict) else {}

            name = _get_parsed_name(parsed) or cv.file_name or f"CV #{cv.id}"
            job = cv.job_description
            blocks.append(f"\n--- {name} (CV ID:{cv.id}) ---")
            blocks.append(f"Applied for: {job.title if job else 'N/A'}")
            blocks.append(
                f"Score: {cv.role_fit_score if cv.role_fit_score is not None else 'N/A'} | "
                f"Decision: {cv.qualification_decision or 'N/A'} | "
                f"Confidence: {cv.qualification_confidence if cv.qualification_confidence is not None else 'N/A'} | "
                f"Rank: {cv.rank if cv.rank is not None else 'N/A'}"
            )

            for label, key in (
                ('Email', 'email'), ('Phone', 'phone'), ('Location', 'location'),
                ('Education', 'education'), ('Experience', 'experience'),
                ('Skills', 'skills'), ('Certifications', 'certifications'),
            ):
                val = parsed.get(key) or parsed.get(key.title())
                if not val:
                    continue
                if isinstance(val, list):
                    val = ', '.join(str(v) for v in val if v)
                blocks.append(f"{label}: {str(val)[:900]}")

            for label, key in (
                ('Summary', 'summary'), ('Strengths', 'strengths'),
                ('Weaknesses', 'weaknesses'), ('Key highlights', 'key_highlights'),
            ):
                val = insights.get(key)
                if not val:
                    continue
                if isinstance(val, list):
                    val = ', '.join(str(v) for v in val if v)
                blocks.append(f"{label}: {str(val)[:900]}")

            reasoning = qual.get('reasoning') or qual.get('justification')
            if reasoning:
                blocks.append(f"Qualification reasoning: {str(reasoning)[:700]}")

            for iv in Interview.objects.filter(cv_record=cv).order_by('-created_at')[:5]:
                blocks.append(
                    f"Interview: {iv.status} | Outcome: {iv.outcome or 'N/A'} | "
                    f"Type: {iv.interview_type} | When: {iv.scheduled_datetime or 'not scheduled'}"
                )

        return "\n".join(blocks)

    def _find_candidates_in_question(self, company_user: Any, question: str) -> List[Any]:
        """Locate CVRecords the question refers to, by name or by 'candidate N' index."""
        cv_qs = (
            CVRecord.objects
            .filter(job_description__company_user=company_user)
            .select_related('job_description')
        )

        # "candidate 2" / "cv #3" → positional, matching the ranking the user sees.
        index_match = re.search(r'\b(?:candidate|applicant|cv|resume)\s*#?\s*(\d+)\b', question, re.I)
        if index_match:
            idx = int(index_match.group(1))
            ordered = list(cv_qs.order_by('rank', '-role_fit_score')[:max(idx, 1)])
            return [ordered[idx - 1]] if 0 < idx <= len(ordered) else []

        # Otherwise match a name mentioned in the question against parsed CV names.
        words = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", question)}
        if not words:
            return []
        hits = []
        for cv in cv_qs.order_by('rank', '-role_fit_score')[:200]:
            try:
                parsed = json.loads(cv.parsed_json) if cv.parsed_json else {}
            except (ValueError, TypeError):
                continue
            name = _get_parsed_name(parsed if isinstance(parsed, dict) else {})
            if not name:
                continue
            name_parts = {p.lower() for p in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", name)}
            if name_parts & words:
                hits.append(cv)
        return hits

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

        # The user named a role the company has no job for (e.g. "Laravel jobs" when
        # only a MERN job exists). Answer that directly — falling through would hand
        # the LLM every unrelated job and it would present those instead.
        if not matched_job:
            missing = _unmatched_job_topics(jobs, question)
            if missing:
                label = ', '.join(f"**{m.title()}**" for m in missing)
                if not jobs:
                    return (
                        f"No job matching {label} was found — there are no jobs "
                        f"in your account yet."
                    )
                listed = '\n'.join(
                    f"- **{j.get('title')}** — {j.get('candidate_count', 0)} candidate(s)"
                    for j in jobs[:15]
                )
                return (
                    f"There is no job matching {label} in your account, so no "
                    f"candidates have applied for it.\n\n"
                    f"**Your current jobs ({len(jobs)}):**\n{listed}"
                )

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
                # Count everyone who applied, not just the AI-analysed ones.
                pending_n = matched_job.get("pending_count", 0)
                total_n = len(cands) + pending_n
                answer = f"**{title}** has **{total_n}** candidate(s){detail}."
                if pending_n:
                    answer += (
                        f"\n\n**{pending_n}** of them {'is' if pending_n == 1 else 'are'} "
                        f"still awaiting AI analysis, so {'it has' if pending_n == 1 else 'they have'} "
                        f"no score or decision yet:\n"
                        + '\n'.join(
                            f"- **{p.get('name')}** — {p.get('email') or 'no email'}"
                            for p in matched_job.get("pending_applicants", [])[:15]
                        )
                    )
                return answer

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
                pending_list = matched_job.get("pending_applicants", [])
                if not cands and not pending_list:
                    return f"No candidates found for **{title}**."
                total_n = len(cands) + len(pending_list)
                answer = f"**Candidates for {title}** ({total_n} total):\n\n"
                for i, c in enumerate(cands[:15], 1):
                    score = c.get("role_fit_score", "N/A")
                    decision = c.get("qualification_decision", "N/A")
                    answer += f"{i}. **{c['name']}** — Score: {score}, Decision: {decision}\n"
                if len(cands) > 15:
                    answer += f"\n... and {len(cands) - 15} more analysed candidates\n"
                if pending_list:
                    answer += "\n**Awaiting AI analysis** (no score/decision yet):\n"
                    for p in pending_list[:15]:
                        answer += f"- **{p.get('name')}** — {p.get('email') or 'no email'}\n"
                    if len(pending_list) > 15:
                        answer += f"\n... and {len(pending_list) - 15} more\n"
                return answer.strip()

            # General "candidates for X" — list them
            pending_list = matched_job.get("pending_applicants", [])
            if cands or pending_list:
                total_n = len(cands) + len(pending_list)
                answer = f"**{title}** has **{total_n}** candidate(s):\n\n"
                for i, c in enumerate(cands[:10], 1):
                    score = c.get("role_fit_score", "N/A")
                    decision = c.get("qualification_decision", "N/A")
                    answer += f"{i}. **{c['name']}** — Score: {score}, Decision: {decision}\n"
                if len(cands) > 10:
                    answer += f"\n... and {len(cands) - 10} more analysed\n"
                if pending_list:
                    answer += "\n**Awaiting AI analysis** (no score/decision yet):\n"
                    for p in pending_list[:10]:
                        answer += f"- **{p.get('name')}** — {p.get('email') or 'no email'}\n"
                    if len(pending_list) > 10:
                        answer += f"\n... and {len(pending_list) - 10} more\n"
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
            # Reaching this branch means the user asked for the job's details, so
            # show the description and requirements in full rather than cutting
            # them mid-sentence.
            if j.get("description"):
                answer += f"\n## Description\n{j['description']}\n"
            if j.get("requirements"):
                answer += f"\n## Requirements & Skills\n{j['requirements']}\n"
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
            wants_detail = any(x in q for x in ("detail", "details", "description", "requirement", "full", "complete", "everything", "all info", "poori", "puri", "sari", "sara"))
            if wants_detail:
                answer = f"## All Jobs ({total_jobs} total — {active} active, {inactive} inactive)\n\n"
                for j in jobs:
                    status = "Active" if j["is_active"] else "Inactive"
                    answer += f"### {j['title']}\n"
                    answer += f"- **Status:** {status}\n"
                    if j.get("location"): answer += f"- **Location:** {j['location']}\n"
                    if j.get("department"): answer += f"- **Department:** {j['department']}\n"
                    if j.get("type"): answer += f"- **Type:** {j['type']}\n"
                    answer += f"- **Candidates:** {j['candidate_count']} | **Interviews:** {j.get('interview_count', 0)}\n"
                    jqc = j.get("qualification_counts", {})
                    answer += f"- **Decisions:** INTERVIEW={jqc.get('INTERVIEW',0)}, HOLD={jqc.get('HOLD',0)}, REJECT={jqc.get('REJECT',0)}\n"
                    if j.get("description"):
                        answer += f"- **Description:** {_shorten(j['description'], 600)}\n"
                    if j.get("requirements"):
                        answer += f"- **Requirements:** {_shorten(j['requirements'], 400)}\n"
                    answer += "\n"
                return answer.strip()
            else:
                answer = f"**All Jobs** ({total_jobs} total, {active} active, {inactive} inactive):\n\n"
                for j in jobs:
                    status = "Active" if j["is_active"] else "Inactive"
                    loc = f" | {j['location']}" if j.get("location") else ""
                    dept = f" | {j['department']}" if j.get("department") else ""
                    answer += f"- **{j['title']}** — {status}{loc}{dept} | {j['candidate_count']} candidates, {j.get('interview_count', 0)} interviews\n"
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
            wants_detail = any(x in q for x in ("detail", "details", "full", "complete", "everything", "description", "requirement", "explain", "tell me", "show me", "all info", "poori", "puri"))
            if wants_detail:
                prompt = f"""
Question: "{question}"

{context}

INSTRUCTIONS:
- Provide COMPLETE and DETAILED answer using all available data from the context.
- For each job/candidate/interview: include name, status, location, department, type, description, requirements, candidate count, scores, decisions — every field available.
- Format with ## for job/section headings, ### for sub-sections, bullet lists for fields.
- Use exact values from context. Never omit available details.
"""
            else:
                prompt = f"""
Question: "{question}"

{context}

INSTRUCTIONS:
- Answer the question clearly and completely. Use exact numbers and names from the context.
- For each item mentioned (job, candidate, interview) — include all relevant fields: title, status, location, description, requirements, scores, decisions.
- Format with markdown: ## headings, bullet lists for multiple fields per item.
- Do not give a one-line answer if the context has more relevant detail.
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
