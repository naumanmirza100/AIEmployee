"""
Marketing Knowledge Q&A + Analytics Agent
Foundation Agent - Provides data understanding and answers marketing questions

ROUTING ARCHITECTURE:
  EVERY question about the data is answered by the LLM, which receives the
  complete campaign list (metrics + targeting fields) plus the conversation
  history and reasons over it itself.

  Only four categories are answered without the LLM, and none of them read
  campaign data:
    - ACTION_REQUEST  → refuse: this agent is READ-ONLY and must never imply
                        it changed something (the LLM would claim it did)
    - GREETING        → short friendly reply
    - PLATFORM_INFO   → static platform description
    - META_HELP       → static "what can I ask?" reply

  WHY: the previous design keyword-matched data questions to hand-written
  handlers (DB_COUNT_STATUS, DB_TOTAL_LEADS, DB_ANALYTICS, DB_CAMPAIGN_DETAIL,
  DB_BEST_CHANNEL). Each answered ONE fixed question and silently ignored any
  qualifier the user added, so "show campaigns targeting young adults" matched
  on 'show campaigns' and returned every campaign, and "what is THEIR number of
  leads" matched on 'number of leads' and returned the account-wide total.
  Those handlers remain in the file but are no longer routed to; deleting them
  is safe once nothing else references them.
"""

from .marketing_base_agent import MarketingBaseAgent
from .platform_content import get_platform_response
from typing import Dict, Optional, List
from marketing_agent.models import Campaign, CampaignPerformance, MarketResearch, EmailSendHistory, Reply, CampaignLead
import json
import re
from enum import Enum
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from django.db.models import Sum, Avg, Count, Q


# ──────────────────────────────────────────────
#  Question Categories (Smart Enum Router)
# ──────────────────────────────────────────────
class QuestionCategory(Enum):
    GREETING            = "greeting"
    PLATFORM_INFO       = "platform_info"
    META_HELP           = "meta_help"
    DB_COUNT_STATUS     = "db_count_status"
    DB_TOTAL_LEADS      = "db_total_leads"
    DB_ANALYTICS        = "db_analytics"
    DB_CAMPAIGN_DETAIL  = "db_campaign_detail"
    DB_BEST_CHANNEL     = "db_best_channel"
    GENERAL_DEFINITION  = "general_definition"
    ACTION_REQUEST      = "action_request"   # user asked us to DO something
    LLM_REASONING       = "llm_reasoning"   # fallback — needs LLM


# ──────────────────────────────────────────────
#  Router Config — all keyword rules in ONE place
#  To add a new question type: just add a new entry here.
# ──────────────────────────────────────────────
ROUTER_CONFIG = {
    QuestionCategory.GREETING: {
        "exact": {
            'hi', 'hello', 'hey', 'yo', 'sup', 'howdy', 'greetings',
            'hi!', 'hello!', 'hey!', 'thanks', 'thank you', 'ok', 'okay',
            'bye', 'goodbye', 'good', 'great', 'nice', 'cool', 'alright',
            'fine', 'good to know', 'got it', 'understood', 'perfect',
            'sure', 'yeah', 'yep', 'nope', 'no',
        },
        "startswith": (
            'how are you', 'how are u', "how's it", 'hows it', 'how do you do',
            'how r u', 'how r you', 'good morning', 'good afternoon',
            'good evening', 'hi there', 'hello there', 'hey there',
        ),
        "max_len": 35,
    },

    QuestionCategory.PLATFORM_INFO: {
        "contains": (
            'what is this platform', 'what does this platform', 'how helpful is this platform',
            'what is this website', 'what is this site', 'what is this app', 'what is this system',
            'how to use this platform', 'how to run campaign', 'how to build campaign',
            'how to create campaign', 'how do i run a campaign', 'what are the agents',
            'tell me about this platform', 'explain this platform', 'describe this platform',
            'campaign agent', 'research agent', 'outreach agent', 'notification agent',
            'what is the campaign agent', 'how does this platform work', 'how this platform work',
            'how does this agent', 'how this agent work',
        ),
        "max_len": 120,
    },

    QuestionCategory.META_HELP: {
        "contains": (
            'what question', 'what questions', 'what can i ask', 'what can you answer',
            'how can you help', 'how can i use', 'what do you do', 'what do you know',
            'what can you tell', 'what can you do', 'what should i ask',
            'give me examples', 'example questions', 'what to ask', 'help me ask',
        ),
        "max_len": 80,
    },

    QuestionCategory.DB_COUNT_STATUS: {
        "contains": (
            'how many campaign', 'how many campaigns', 'campaigns are working',
            'campaigns working', 'how many are active', 'how many active',
            'number of campaign', 'total campaign', 'list my campaign', 'list campaigns',
            'campaign count', 'show my campaign', 'show campaigns',
            'campaign status', 'status of my campaigns', 'status of campaigns',
        ),
        "max_len": 120,
    },

    QuestionCategory.DB_TOTAL_LEADS: {
        "contains": (
            'total leads', 'total no of leads', 'total number of leads',
            'how many leads', 'no of leads', 'number of leads',
        ),
        "max_len": 100,
    },

    QuestionCategory.DB_ANALYTICS: {
        "contains": (
            'how are our campaigns performing', 'how are my campaigns performing',
            'campaigns performing', 'best performing campaign', 'top campaigns',
            'emails sent', 'open rate', 'click rate', 'reply rate',
            'leads per campaign', 'show leads', 'campaigns by status',
            # vague follow-ups
            'their performance', 'campaign performance', 'campaigns performance',
            'performance of campaigns', 'performance', 'stats', 'metrics',
            # "best campaign" / "which is best" variants
            'best campaign', 'which is best campaign', 'which campaign is best',
            'which is the best campaign', 'best camapgin', 'best compagin',
            # "low/worst campaign" variants
            'low performance campaign', 'poor performance campaign',
            'underperforming campaign', 'underperform campaign',
            'worst campaign', 'lowest campaign', 'least performing campaign',
            'which campaign is worst', 'which is the worst campaign',
            # average / total aggregates
            'average open rate', 'avg open rate', 'total open rate',
            'average click rate', 'avg click rate', 'total click rate',
            'average reply rate', 'avg reply rate', 'total reply rate',
            'average bounce rate', 'avg bounce rate',
            'total emails sent', 'total number of emails',
            'just tell average', 'average rate',
        ),
        "exact_also": {
            'performance', 'stats', 'metrics',
            'their performance', 'campaign performance', 'campaigns performance',
            'just tell average', 'average',
        },
        "exclude_if_contains": (
            'why', 'recommend', 'strategy', 'optimize', 'improve',
            'suggest', 'analyze', 'analysis', 'insights', 'plan',
        ),
        "max_len": 180,
    },

    QuestionCategory.DB_BEST_CHANNEL: {
        "requires_any": ('best', 'which'),
        "requires_channel": (
            'channel', 'platform', 'instagram', 'insta', 'facebook', 'tiktok',
            'linkedin', 'google', 'seo', 'ads', 'email', 'whatsapp',
            'sms', 'youtube', 'twitter',
        ),
        "contains": (
            'best channel', 'which channel', 'best platform', 'which platform',
            'email or instagram', 'email vs instagram', 'instagram or email',
            'where should i run', 'where to run',
        ),
        "max_len": 160,
    },

    QuestionCategory.GENERAL_DEFINITION: {
        # Strong definition signals — always treated as definition regardless of topic
        "contains_strong": (
            'full form of', 'full form', 'what is the full form', 'fullform of',
            'meaning of', 'what do you mean by', 'what is meant by',
            'what does it mean', 'what does that mean',
            'define ', 'definition of', 'abbreviation of', 'stand for',
            'explain what', 'explain the term', 'what do we mean by',
        ),
        # Weak signals — only match when no data-context words present
        "contains": (
            'meaning of', 'define ', 'definition of',
        ),
        # These prefixes only when question is short (no "our/my" data context)
        "startswith_short": ('what does ', 'what is '),
        "exclude_if_contains": (
            'our ', 'my ', 'this campaign', 'the campaign', 'the active',
            'lead conversion', 'our lead',
        ),
        "max_len": 100,
    },
}


class MarketingQAAgent(MarketingBaseAgent):
    """
    Foundation Agent - Marketing Knowledge Q&A + Analytics

    Uses Smart Enum Router to classify every question into one category,
    then routes to either a DB-only handler or the LLM.
    """

    def __init__(self):
        super().__init__()
        self.system_prompt = (
            "You are a Marketing Q&A agent. Answer directly using the provided data. "
            "Keep answers short. Do not include reasoning or filler like 'based on the data'. "
            "If listing campaigns, include status after each name."
        )

    # ══════════════════════════════════════════════════════════
    #  SMART ENUM ROUTER  ← THE BRAIN OF ROUTING
    # ══════════════════════════════════════════════════════════

    # This agent is READ-ONLY. It has no write path to the DB at all, so any
    # request to change something must be refused explicitly — otherwise the
    # question falls through to the LLM, which happily replies "Done, deleted!"
    # and the user believes a campaign was removed when it never was.
    ACTION_VERBS = (
        'delete', 'deletes', 'deleting', 'remove', 'removes', 'removing',
        'erase', 'destroy', 'pause', 'pauses', 'pausing', 'halt', 'suspend',
        'resume', 'restart', 'launch', 'launches', 'launching',
        'schedule', 'publish', 'create', 'creates', 'creating',
        'rename', 'renames', 'modify', 'archive', 'duplicate', 'clone',
        'upload', 'unsubscribe',
        # Ambiguous on their own — they read as commands only with an object,
        # handled by ACTION_PHRASES below: send, start, stop, update, edit,
        # change, add, make, set, export, import.
    )
    # Verb + object patterns. These are commands even though the verb alone is
    # too common to blocklist ("update" appears in "any update on X?").
    ACTION_PHRASES = (
        r'\bsend\s+(the|an|a|this|that|these|those|it|out|emails?|campaign)',
        r'\b(start|stop)\s+(the|this|that|it|all|campaign|sending)',
        r'\b(update|edit|change|modify)\s+(the|this|that|it|my|campaign|name|age|status)',
        r'\b(add|make|create)\s+(a|an|the|new)\b',
        r'\bset\s+(up|the|this|it)\b',
        r'\b(export|import)\s+(the|this|my|all|leads?|campaigns?|data|csv)',
        r'\bturn\s+(on|off)\b',
        r'\bmark\s+(as|it|this|the)\b',
    )
    # Phrases that look like verbs but are really questions about data.
    ACTION_EXCLUDE = (
        'how do i', 'how to', 'how can i', 'can you tell', 'what happens',
        'should i', 'when should', 'why do', 'what does', 'is it possible',
        'how would i', 'where do i', 'what is', "what's", 'what are',
        'which campaign', 'which campaigns', 'list ', 'show ', 'tell me',
        'how many', 'compare',
    )

    def _is_action_request(self, q: str) -> bool:
        """True when the user is asking us to CHANGE something, not answer.

        Word-boundary matching matters here: a plain substring test made
        'import' match inside 'important', so an ordinary listing question was
        refused as if it were a command.
        """
        if any(x in q for x in self.ACTION_EXCLUDE):
            return False

        # Shape-based checks, so a typo in the phrase doesn't turn a question
        # into a command ("what ahppen if i pause a campaign").
        # 1. Starts with a question word -> asking, not instructing.
        # Typo-tolerant: users routinely write "waht", "shud", "wud", and the
        # whole point of this check is that it must not be defeated by one.
        if re.match(r"^\s*(wh?at|waht|wat|why|whi|when|wen|where|which|wich|"
                    r"who|how|hwo|should|shoud|shud|shld|could|coud|cud|"
                    r"would|woud|wud|can|cn|do|does|did|is|are|was|were|"
                    r"will|shall|any|tell|explain|describe)\b", q):
            return False
        # 2. Contains a hypothetical/comparative frame.
        if re.search(r"\b(if i|if we|whether|instead of|difference between|"
                     r"better to|worth it|pros and cons)\b", q):
            return False
        # 3. Ends in a question mark.
        if q.rstrip().endswith('?'):
            return False

        words = set(re.findall(r"[a-z']+", q))
        if words & set(self.ACTION_VERBS):
            return True
        return any(re.search(pat, q) for pat in self.ACTION_PHRASES)


    def _classify_question(self, question: str, campaigns: Optional[List[Dict]] = None) -> QuestionCategory:
        """
        Single entry point for ALL routing decisions.
        Returns a QuestionCategory enum value.

        Order matters — more specific checks come first.
        To add a new route: add config to ROUTER_CONFIG and a case here.
        """
        if not question or not isinstance(question, str):
            return QuestionCategory.GREETING

        q = question.strip().lower().rstrip('?!.')

        # ── 0a. Action requests ───────────────────────────────
        #    Checked before everything else: this agent cannot write to the DB,
        #    so an action request must never reach the LLM (which would claim
        #    it did the work).
        if self._is_action_request(q):
            return QuestionCategory.ACTION_REQUEST

        # ── 0a2. Back-referencing questions ───────────────────

        # ── 1. Greeting / small talk ──────────────────────────
        cfg = ROUTER_CONFIG[QuestionCategory.GREETING]
        if len(q) <= cfg["max_len"]:
            if q in cfg["exact"]:
                return QuestionCategory.GREETING
            if any(q.startswith(p) for p in cfg["startswith"]):
                return QuestionCategory.GREETING

        # ── 2. Platform info ──────────────────────────────────
        cfg = ROUTER_CONFIG[QuestionCategory.PLATFORM_INFO]
        if len(q) <= cfg["max_len"] and any(p in q for p in cfg["contains"]):
            return QuestionCategory.PLATFORM_INFO

        # ── 3. Meta / help ────────────────────────────────────
        cfg = ROUTER_CONFIG[QuestionCategory.META_HELP]
        if len(q) <= cfg["max_len"] and any(p in q for p in cfg["contains"]):
            return QuestionCategory.META_HELP

        # ── 4. Everything else is a question about the DATA ───
        #    It goes to the LLM, which receives the complete campaign list
        #    (metrics + targeting) and the conversation history and answers
        #    for itself. The old keyword routes (DB_TOTAL_LEADS,
        #    DB_COUNT_STATUS, DB_CAMPAIGN_DETAIL, DB_ANALYTICS,
        #    DB_BEST_CHANNEL, GENERAL_DEFINITION) each answered ONE fixed
        #    question and ignored any qualifier the user added, so
        #    'show campaigns targeting young adults' returned every campaign
        #    and 'what is THEIR number of leads' returned the account total.
        #    Their handlers are kept below for reference but not routed to.
        # ── 10. Default: needs LLM reasoning ──────────────────
        return QuestionCategory.LLM_REASONING

    # ══════════════════════════════════════════════════════════
    #  MAIN ENTRY POINT
    # ══════════════════════════════════════════════════════════

    def process(self, question: str, context: Optional[Dict] = None, user_id: Optional[int] = None) -> Dict:
        """
        Main entry point.

        Every question ABOUT THE DATA goes to the LLM, which receives the full
        campaign list (metrics + targeting) and the conversation history and
        answers for itself.

        Only four things are still answered without the LLM, and none of them
        read campaign data:
          - ACTION_REQUEST : must be refused deterministically — the LLM would
                             cheerfully claim it deleted something.
          - GREETING       : "hi" needs no data and no tokens.
          - PLATFORM_INFO  : static description of this platform.
          - META_HELP      : static "what can I ask?" text.

        The old keyword router sent data questions to hand-written handlers
        (DB_COUNT_STATUS, DB_TOTAL_LEADS, DB_ANALYTICS, DB_CAMPAIGN_DETAIL).
        Those handlers answered ONE fixed question and silently ignored any
        qualifier the user added, so "show campaigns targeting young adults"
        returned every campaign and "what is THEIR number of leads" returned the
        account-wide total. They are no longer routed to.
        """
        self.log_action("Processing marketing question", {"question": (question or '')[:100]})

        question = self._normalize_question_typos(question)
        category = self._classify_question(question, campaigns=None)

        # Refuse writes before anything else — this agent is read-only.
        # The keyword filter flags candidates; the LLM confirms, because only it
        # reads typos ("what ahppen if i pause a comapgin" is a question, not a
        # command). Refuse only when both agree.
        if category == QuestionCategory.ACTION_REQUEST:
            if self._confirm_action_with_llm(question):
                return self._handle_action_request(question)
            category = QuestionCategory.LLM_REASONING

        # No-data replies: cheap, deterministic, and impossible to get wrong.
        if category == QuestionCategory.GREETING:
            return self._handle_greeting(question)

        if category == QuestionCategory.PLATFORM_INFO:
            return self._handle_platform_info(question)

        if category == QuestionCategory.META_HELP:
            return self._handle_meta_help(question)

        marketing_data = self._get_marketing_data(user_id)

        # Decline anything outside this account's marketing data. Answering
        # general knowledge is how the assistant ended up asserting an invented
        # OpenAI price as fact. Campaign names are passed in so a question that
        # names one is never mistaken for off-topic.
        campaign_names = [c.get('name') for c in (marketing_data.get('campaigns') or [])]
        has_history = bool((context or {}).get('conversation_history'))
        if self._is_out_of_scope(question, campaign_names, has_history):
            return self._ok(
                "That's outside what I can help with — I answer questions about "
                "your campaigns and marketing data.\n\nTry asking about campaign "
                "performance, leads, targeting, or what to do next.",
                question,
            )

        # Everything else is a question about the data → let the LLM answer it
        # with the full dataset in context.
        return self._handle_llm_reasoning(question, marketing_data, context)

    # ══════════════════════════════════════════════════════════
    #  HANDLERS — one per category
    # ══════════════════════════════════════════════════════════

    INTENT_SYSTEM = (
        "You decide whether a message to a READ-ONLY marketing assistant is a "
        "COMMAND or a QUESTION. Reply with exactly one word.\n\n"
        "command  - the user is telling the assistant to CHANGE something now: "
        "delete/pause/launch/create/rename/send/export a campaign or its data.\n"
        "question - anything else, including asking HOW to do those things, "
        "WHETHER they should, WHAT WOULD HAPPEN if they did, or any request for "
        "information.\n\n"
        "The user often misspells words - read through typos.\n\n"
        "Examples:\n"
        "'delete campaign cmp1' -> command\n"
        "'pause er5t6y7u89' -> command\n"
        "'how do i delet a campaign' -> question\n"
        "'what ahppen if i pause a comapgin' -> question\n"
        "'shud i delete a draf comapgin' -> question\n"
        "'which campaigns should i delete?' -> question\n"
        "'list all the caomapgin with important info' -> question\n"
    )

    def _confirm_action_with_llm(self, question: str) -> bool:
        """Second opinion before refusing.

        The keyword pre-filter cannot read typos, so it has repeatedly refused
        ordinary questions ('what ahppen if i pause a comapgin'). Ask the model,
        which handles misspellings natively. On any failure we keep the
        keyword verdict, so a refusal is never skipped by accident.
        """
        try:
            out = self._call_llm_for_reasoning(
                'Message: "%s"' % (question or '').strip()[:300],
                self.INTENT_SYSTEM, temperature=0.0, max_tokens=5,
            )
        except Exception as e:
            self.log_action("Intent confirmation failed", {"error": str(e)})
            return True
        if not out:
            return True
        return 'command' in out.strip().lower()

    def _handle_action_request(self, question: str) -> Dict:
        """Refuse, clearly. This agent has no write path — it must never imply
        that it changed anything. Points the user at the UI that can."""
        q = (question or '').lower()

        if any(v in q for v in ('delete', 'remove', 'erase', 'destroy', 'archive')):
            where = "Campaigns tab -> open the campaign -> Delete"
            what = "delete campaigns"
        elif any(v in q for v in ('pause', 'stop', 'halt', 'suspend', 'resume', 'restart')):
            where = "Campaigns tab -> open the campaign -> Pause/Resume"
            what = "pause or resume campaigns"
        elif any(v in q for v in ('launch', 'send', 'schedule', 'publish', 'start ')):
            where = "Campaigns tab -> open the campaign -> Launch"
            what = "launch campaigns or send emails"
        elif any(v in q for v in ('create', 'make a', 'add a', 'set up', 'setup')):
            where = "Outreach tab -> Create Campaign"
            what = "create campaigns"
        elif any(v in q for v in ('update', 'edit', 'change', 'rename', 'modify')):
            where = "Campaigns tab -> open the campaign -> Edit"
            what = "edit campaigns"
        else:
            where = "the Campaigns or Outreach tab"
            what = "make changes"

        answer = (
            "I can't %s — I'm a read-only assistant, so I can only answer "
            "questions about your marketing data. **Nothing has been changed.**\n\n"
            "To do this yourself: %s." % (what, where)
        )
        return {
            'success': True,
            'answer': answer,
            'insights': [],
            'data_summary': self._create_data_summary(None),
            'question': question,
            'action_refused': True,
        }

    def _handle_greeting(self, question: str) -> Dict:
        q = (question or '').strip().lower()
        if any(x in q for x in ('how are', "how's it", 'hows it', 'how r u', 'how do you do')):
            answer = "I'm doing well, thanks for asking! How can I help you with your marketing today?"
        elif q in ('good', 'great', 'nice', 'cool', 'alright', 'fine', 'got it', 'understood', 'perfect', 'sure', 'yeah', 'yep'):
            answer = "Got it. What would you like to ask about your marketing?"
        else:
            answer = "Hi! How can I help you with your marketing today? Ask me about campaigns, performance, or insights."
        return self._ok(answer, question)

    def _handle_platform_info(self, question: str) -> Dict:
        return self._ok(get_platform_response(question), question)

    def _handle_meta_help(self, question: str) -> Dict:
        answer = (
            "You can ask me about your **campaigns** (how many, status, list), **performance** (clicks, conversions, ROI), "
            "**leads**, and **marketing insights**. Examples: \"How many campaigns?\", \"What's performing best?\", \"List my campaigns.\" "
            "Ask for details or recommendations only when you want a longer analysis."
        )
        return self._ok(answer, question)

    def _handle_best_channel(self, question: str) -> Dict:
        q = (question or '').strip().lower()
        if any(x in q for x in ('b2b', 'saas', 'enterprise', 'lead', 'outreach', 'cold email')):
            answer = (
                "**Email** is usually the best channel for B2B/outreach — direct, measurable, great for follow-ups. "
                "If your audience is professional, **LinkedIn** is the next-best companion."
            )
        elif any(x in q for x in ('brand', 'awareness', 'followers', 'engagement', 'visual', 'b2c')):
            answer = (
                "For **brand awareness** and visual audiences, **Instagram** (and often **TikTok**) works best. "
                "Use **email** after capturing leads to convert and retain them."
            )
        else:
            answer = (
                "For **leads + conversions** → start with **email** (best ROI and tracking). "
                "For **awareness** → use **Instagram**. "
                "Best combo: Instagram/ads to attract → email to convert and nurture."
            )
        return self._ok(answer, question)

    def _handle_general_definition(self, question: str) -> Dict:
        prompt = (
            f'The user asked: "{question}"\n\n'
            "Give a brief, direct answer only (definition, full form, or general knowledge). "
            "Do NOT mention marketing data, campaigns, or trends. Keep it to 1–4 sentences."
        )
        try:
            answer = self._call_llm_for_reasoning(
                prompt,
                "You answer general knowledge and definition questions briefly.",
                temperature=0.2,
                max_tokens=300,
            )
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            answer = "I couldn't answer that right now. For definitions, try a search engine."
        return self._ok(answer, question)

    def _handle_total_leads(self, marketing_data: Dict, question: str) -> Dict:
        campaigns = marketing_data.get('campaigns', []) or []
        total = sum(int(c.get('leads_count') or 0) for c in campaigns)
        return self._ok(f"**{total}** lead(s) in total.", question, marketing_data)

    def _handle_count_status(self, marketing_data: Dict, question: str) -> Dict:
        stats = marketing_data.get('stats', {})
        campaigns = marketing_data.get('campaigns', []) or []
        total = stats.get('total_campaigns', len(campaigns))
        active_list = [c for c in campaigns if (c.get('status') or '').lower() == 'active']
        active = len(active_list)

        if total == 0:
            answer = "You have **0** campaigns. Create a campaign to get started."
        else:
            answer = f"You have **{total}** campaign(s) in total. **{active}** are currently active."
            if len(campaigns) <= 15:
                all_names = ", ".join(c.get('name', 'Unnamed') for c in campaigns)
                answer += f" Campaigns: {all_names}."
            elif active_list:
                names = ", ".join(c.get('name', 'Unnamed') for c in active_list[:10])
                answer += f" Active: {names}."

        insights = []
        if total > 0:
            insights.append({
                'type': 'campaigns',
                'title': 'Active campaigns',
                'value': f"{active} of {total} active",
                'status': 'good' if active > 0 else 'warning'
            })
        return {
            'success': True,
            'answer': answer,
            'insights': insights,
            'data_summary': self._create_data_summary(marketing_data),
            'question': question,
        }

    def _handle_campaign_detail(self, campaign: Dict, marketing_data: Dict, question: str) -> Dict:
        name   = campaign.get('name') or 'Unnamed'
        status = campaign.get('status') or 'N/A'

        sent    = campaign.get('emails_sent', 0) or 0
        opened  = campaign.get('emails_opened', 0) or 0
        clicked = campaign.get('emails_clicked', 0) or 0
        replied = campaign.get('emails_replied', 0) or 0
        bounced = campaign.get('emails_bounced', 0) or 0
        failed  = campaign.get('emails_failed', 0) or 0

        def _r(v): return v if v is not None else 'N/A'

        lines = [
            f"**{name} ({status})**",
            f"- Emails: sent={sent}, opened={opened}, clicked={clicked}, replied={replied}, bounced={bounced}, failed={failed}",
            f"- Rates: open={_r(campaign.get('open_rate'))}%, click={_r(campaign.get('click_rate'))}%, reply={_r(campaign.get('reply_rate'))}%, bounce={_r(campaign.get('bounce_rate'))}%",
            f"- Leads: {_r(campaign.get('leads_count'))} (target={_r(campaign.get('target_leads'))}, progress={_r(campaign.get('leads_progress'))}%)",
            f"- Conversions: {_r(campaign.get('positive_replies'))} (target={_r(campaign.get('target_conversions'))}, progress={_r(campaign.get('conversion_progress'))}%)",
            f"- Replies: positive={_r(campaign.get('positive_replies'))}, negative={_r(campaign.get('negative_replies'))}",
        ]
        if campaign.get('goals'):
            lines.append(f"- Goals: {campaign['goals']}")
        if campaign.get('channels'):
            lines.append(f"- Channels: {campaign['channels']}")

        return self._ok("\n".join(lines), question, marketing_data)

    def _handle_db_analytics(self, question: str, marketing_data: Dict) -> Dict:
        q = (question or '').strip().lower()
        campaigns = marketing_data.get('campaigns', []) or []

        def _r(v): return v if v is not None else 'N/A'

        def _line(c):
            return (
                f"{c.get('name','Unnamed')} ({c.get('status','N/A')}): "
                f"sent={c.get('emails_sent',0)}, open={_r(c.get('open_rate'))}%, "
                f"click={_r(c.get('click_rate'))}%, reply={_r(c.get('reply_rate'))}%, "
                f"leads={_r(c.get('leads_count'))}, conversion_progress={_r(c.get('conversion_progress'))}%"
            )

        if not campaigns:
            return self._ok("You have **0** campaigns.", question)

        def _score(c):
            def _n(v):
                try:
                    return float(v)
                except:
                    return 0.0
            return (
                _n(c.get('conversion_progress')),
                _n(c.get('reply_rate')),
                _n(c.get('open_rate')),
                _n(c.get('click_rate')),
                int(c.get('emails_sent') or 0),
            )

        # ── Generic average handler ───────────────────────────
        # Works for ANY numeric field: open rate, click rate, reply rate,
        # bounce rate, emails sent/opened/clicked/replied/bounced/failed,
        # leads count, conversion progress, leads progress, etc.
        # Only counts campaigns where the field has actual data (not None).
        if 'average' in q or 'avg' in q:
            result = self._compute_avg(q, campaigns)
            if result:
                return self._ok(result, question, marketing_data)

        # Best performing campaign intent.
        # Handles typo variants like "best camapgin" too.
        is_best_intent = self._is_best_campaign_intent(q)
        if is_best_intent:
            best = sorted(campaigns, key=_score, reverse=True)[:5]
            answer = f"Best performing: **{best[0].get('name','Unnamed')} ({best[0].get('status','N/A')})**.\n"
            answer += "\n".join(f"- {_line(c)}" for c in best)
            return self._ok(answer, question, marketing_data)

        # Low / worst performing campaign intent.
        # Handles typo variants like "low performance camapgin" too.
        is_low_intent = self._is_low_campaign_intent(q)
        if is_low_intent:
            worst = sorted(campaigns, key=_score)[:5]
            answer = f"Lowest performing: **{worst[0].get('name','Unnamed')} ({worst[0].get('status','N/A')})**.\n"
            answer += "\n".join(f"- {_line(c)}" for c in worst)
            return self._ok(answer, question, marketing_data)

        # Status breakdown
        if 'by status' in q or ('status' in q and 'campaign' in q):
            by_status: Dict = {}
            for c in campaigns:
                s = (c.get('status') or 'N/A').lower()
                by_status.setdefault(s, []).append(c)
            parts = [
                f"- **{s}**: {len(items)} ({', '.join(i.get('name','Unnamed') for i in items)})"
                for s, items in sorted(by_status.items())
            ]
            return self._ok("\n".join(parts), question, marketing_data)

        # Generic performance table (up to 10)
        answer = "\n".join(f"- {_line(c)}" for c in campaigns[:10])
        return self._ok(answer, question, marketing_data)

    def _handle_llm_reasoning(self, question: str, marketing_data: Dict, context: Optional[Dict]) -> Dict:
        """Full LLM call. This is now the path for every data question."""
        full_context = self._build_context(marketing_data, context, question)

        # Resolve any filtering in the question here rather than trusting the
        # model to do it over 18 rows — it repeatedly dropped conditions,
        # miscounted, and answered "none" while matches existed.
        hint = self._run_query_plan(question, marketing_data)

        # A question about LEADS wants the people, not the campaign's metrics.
        # The plan for "leads of meow" filters to that campaign, and its row of
        # sent/opened/reply-rate figures then crowded out the lead list the
        # user actually asked for.
        q_lower = (question or '').lower()

        # "which leads got emails but never replied?" is about PEOPLE, but the
        # planner can only filter campaigns, so it produced a campaign-level
        # "no campaign matches" and the answer denied something that was never
        # asked. Drop that hint and let the model work from the lead rows.
        asks_about_leads = bool(re.search(
            r'\b(which|what|who|how many)\b[^.?]{0,40}\b(leads?|contacts?|'
            r'people|persons?)\b', q_lower))

        # "to which campaign do they belong?" right after a lead answer is
        # still about those leads. Treated as a fresh campaign question it came
        # back with campaign metrics instead of naming the leads' campaigns.
        prev_q = (self._previous_question(context) or '').lower()
        prev_was_leads = bool(re.search(r'\b(leads?|contacts?|people)\b', prev_q))
        if (prev_was_leads
                and re.search(r'\b(they|them|their|these|those|it)\b', q_lower)
                and re.search(r'\b(belong|campaign|from|part of|which)\b', q_lower)):
            asks_about_leads = True
            full_context += (
                "\nThe previous answer was about specific LEADS. This follow-up "
                "is about THOSE SAME PEOPLE — only the ones named in your "
                "previous answer, nobody else. For each of them, look their "
                "email up in the LEAD -> CAMPAIGNS index below and write one "
                "line: 'email — campaign, campaign'. Copy the campaign names "
                "from that index; never leave the list empty. Do not answer "
                "with campaign metrics, and do not introduce other leads.\n")
        if hint and asks_about_leads and 'NO campaign matches' in hint:
            self.log_action("Dropped campaign-level 'no match' for a lead question",
                            {"question": question[:120]})
            hint = (
                "NOTE: this question is about individual LEADS, not campaigns. "
                "Answer it from the lead and reply rows in the DETAIL section "
                "below. Do not say 'no campaigns match' — the user did not ask "
                "about campaigns.\n"
            )

        # "types of replies from all leads of X" is about the reply TYPES, not
        # the lead roster — answering it with a plain lead list left the actual
        # question unanswered.
        asks_reply_types = (
            self._mentions(q_lower, 'type', 'types', 'kind', 'kinds',
                           'interest level')
            and self._mentions(q_lower, 'reply', 'replies', 'replied',
                               'respond', 'response', 'responded'))
        if asks_reply_types:
            # Build the finished table here. Asked to copy it from the context
            # the model kept dropping rows — 2 of 5, then 4 of 5. Handing it
            # the completed text removes the chance to trim.
            ready = self._reply_types_table(question, marketing_data)
            if ready:
                hint = (hint or '') + ready
        elif hint and re.search(r'\b(lead|leads|contact|contacts|who|whom)\b', q_lower):
            hint += (
                "The row above identifies WHICH campaign. The question is about "
                "its LEADS — answer from the DETAIL section, listing the people "
                "and their fields. Do not present campaign metrics as the "
                "answer.\n")
        # Same for email content: the plan's metrics row was being returned in
        # place of the subject lines the user asked for.
        if hint and (
                re.search(r'\b(subject|subjects|email content)\b', q_lower)
                or re.search(r'\b(what|which|show|list|tell)\b[^.?]{0,30}'
                             r'\b(emails?|messages?)\b', q_lower)
                or re.search(r'\bemails?\b[^.?]{0,20}\b(sent|went out)\b', q_lower)):
            hint += (
                "The row above identifies WHICH campaign. The question is about "
                "the EMAILS IT SENT — answer from the 'Emails sent, grouped by "
                "subject' rows in the DETAIL section, listing each subject with "
                "its own count. Do not answer with the campaign's totals.\n")

        # A follow-up like "just show their names" or a bare "why?" carries no
        # filter of its own, so nothing is computed and the model answered over
        # ALL campaigns — or, for "why?", claimed it had no information. Plan
        # against the previous question so the same set stays in play.
        # A question that names a campaign is about THAT campaign, not the
        # previous result set — "just tell me about er5t6y7u89" was treated as
        # a re-format because of the word "just" and re-ran the last query.
        low_q = (question or '').lower()
        names_a_campaign = any(
            re.search(r'(?<![a-z0-9])%s(?![a-z0-9])' % re.escape(
                (c.get('name') or '').strip().lower()), low_q)
            for c in (marketing_data.get('campaigns') or [])
            if (c.get('name') or '').strip())

        # "and which campaign is left?" after "17 of 18 target adults" asks for
        # the ONE that did not match — the complement of the previous filter.
        # Without this it was treated as a fresh question and listed 16 rows.
        is_complement = bool(re.search(
            r'\b(left|remaining|rest|other one|others|excluded|not included|'
            r'didn.?t match|does ?n.?t match|missing one|the last one)\b', low_q))
        if not hint and is_complement:
            prev = self._previous_question(context)
            if prev:
                comp = self._complement_answer(prev, marketing_data)
                if comp:
                    hint = comp

        is_why = bool(re.match(r'^\s*(and\s+)?why\b', low_q))
        if (not hint and not names_a_campaign
                and (is_why or self._is_reformat_followup(question))):
            prev = self._previous_question(context)
            if prev:
                hint = self._run_query_plan(prev, marketing_data)
                if hint and is_why:
                    full_context += (
                        "\nThe user asked WHY about the previous answer. Explain "
                        "it using the numbers computed below — never reply that "
                        "you don't have the information.\n")
                if hint:
                    full_context += (
                        "\nThe new question CONTINUES the previous one. It "
                        "applies to exactly the campaigns computed below — the "
                        "same set, nothing added, nothing dropped.\n"
                        "If it asks for a different field (what they achieved, "
                        "their leads, their dates), give that field FOR EACH of "
                        "those campaigns, one row each. Do NOT answer with an "
                        "account-wide total.\n")

        if hint:
            full_context += "\n" + hint

        answer = self._generate_answer(question, full_context, context)

        # An empty reply reached the UI as "No answer provided." — retry once,
        # asking plainly, rather than showing the user a blank.
        if not (answer or '').strip():
            self.log_action("Empty LLM answer, retrying", {"question": question[:100]})
            answer = self._generate_answer(
                "%s\n\n(Answer directly using the campaign data above. Do not "
                "return an empty response.)" % question,
                full_context, context
            )
        if not (answer or '').strip():
            answer = ("I couldn't produce an answer for that. Try rephrasing it, "
                      "or ask about a specific campaign by name.")

        # Strip any working notes the model copied out of the context.
        answer = self._strip_internal_lines(answer)
        answer = self._dedupe_person_rows(answer)

        # A per-campaign listing can still hit the token ceiling and stop
        # mid-row. Silently returning half the campaigns looks like the
        # assistant ignored the rest, so detect it and say what happened.
        answer = self._note_if_truncated(answer, marketing_data)

        insights = self._extract_insights(marketing_data, question)
        return {
            'success': True,
            'answer': answer,
            'insights': insights,
            'data_summary': self._create_data_summary(marketing_data),
            'question': question,
        }

    # ══════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════

    def _ok(self, answer: str, question: str, marketing_data: Optional[Dict] = None) -> Dict:
        """Shorthand for building a success response."""
        return {
            'success': True,
            'answer': answer,
            'insights': [],
            'data_summary': self._create_data_summary(marketing_data) if marketing_data else {},
            'question': question,
        }

    # ── Generic average calculator ────────────────────────────
    # Maps question keywords → campaign dict field key + display info.
    # To support a new field, just add a row to _AVG_FIELD_MAP.
    _AVG_FIELD_MAP = [
        # (keywords_required,          field_key,             label,                        is_pct)
        (('open', 'rate'),             'open_rate',           'open rate',                   True),
        (('click', 'rate'),            'click_rate',          'click rate',                  True),
        (('reply', 'rate'),            'reply_rate',          'reply rate',                  True),
        (('bounce', 'rate'),           'bounce_rate',         'bounce rate',                 True),
        (('conversion', 'progress'),   'conversion_progress', 'conversion progress',         True),
        (('leads', 'progress'),        'leads_progress',      'leads progress',              True),
        (('email', 'sent'),            'emails_sent',         'emails sent',                 False),
        (('email', 'opened'),          'emails_opened',       'emails opened',               False),
        (('email', 'clicked'),         'emails_clicked',      'emails clicked',              False),
        (('email', 'replied'),         'emails_replied',      'emails replied',              False),
        (('email', 'bounced'),         'emails_bounced',      'emails bounced',              False),
        (('email', 'failed'),          'emails_failed',       'emails failed',               False),
        (('lead',),                    'leads_count',         'leads',                       False),
        (('conversion',),             'conversions',         'conversions',                 False),
        (('positive', 'repl'),         'positive_replies',    'positive replies',            False),
        (('negative', 'repl'),         'negative_replies',    'negative replies',            False),
    ]

    def _compute_avg(self, q: str, campaigns: List[Dict]) -> Optional[str]:
        """
        Generic average calculator.
        Matches question keywords to a campaign field, collects values
        only from campaigns that have actual data (not None), and returns
        the formatted answer string — or None if no field matched.
        """
        for keywords, field_key, label, is_pct in self._AVG_FIELD_MAP:
            if all(kw in q for kw in keywords):
                values = []
                for c in campaigns:
                    val = c.get(field_key)
                    if val is None:
                        continue
                    try:
                        values.append(float(val))
                    except (ValueError, TypeError):
                        continue

                total = sum(values)
                count = len(values)
                avg = (total / count) if count > 0 else 0.0
                pct = '%' if is_pct else ''

                return (
                    f"Average {label} per campaign: **{avg:.2f}{pct}** "
                    f"(total={total:.2f}, from {count}/{len(campaigns)} campaigns with data)."
                )
        return None

    def _normalize_question_typos(self, question: str) -> str:
        """Normalise misspellings of "campaign" only.

        The keyword pre-filter matches that one word, so it has to survive a
        typo. Everything else is left alone: the model reads misspellings
        natively, and maintaining a spelling dictionary was a losing game —
        every new typo became a new bug ('elads', 'nubmer', 'higest',
        'ahppen', 'shud'...).

        Uses similarity rather than a fixed list, so unseen variants work too.
        """
        if not question or not isinstance(question, str):
            return question

        def _looks_like_campaign(word: str) -> Optional[str]:
            w = word.lower()
            if len(w) < 5 or len(w) > 12:
                return None
            if w in ('campaign', 'campaigns'):
                return None          # already correct
            if not w.startswith('c'):
                return None
            # Guard real words that are close to "campaign" in shape.
            if w in ('company', 'companies', 'complain', 'complains',
                     'campus', 'camping', 'champion', 'champions',
                     'comparison', 'competitor', 'competitors'):
                return None
            plural = w.endswith('s')
            stem = w[:-1] if plural else w
            target = 'campaign'
            # Same letters, just jumbled/dropped -> a typo of "campaign".
            if sorted(stem) == sorted(target):
                return 'campaigns' if plural else 'campaign'
            ratio = SequenceMatcher(None, stem, target).ratio()
            if ratio >= 0.6:
                return 'campaigns' if plural else 'campaign'
            # Heavily jumbled spellings ('comapgin', 'caomaphin') score low on
            # ordered similarity but use almost the same letters, so compare
            # letter sets too — the guard list above keeps real words out.
            common = len(set(stem) & set(target))
            if common >= 6 and abs(len(stem) - len(target)) <= 2:
                return 'campaigns' if plural else 'campaign'
            return None

        def _fix(m):
            word = m.group(0)
            fixed = _looks_like_campaign(word)
            if not fixed:
                return word
            # Preserve the original capitalisation style.
            if word.isupper():
                return fixed.upper()
            if word[0].isupper():
                return fixed.capitalize()
            return fixed

        return re.sub(r"[A-Za-z]+", _fix, question.strip())

    def _is_best_campaign_intent(self, q: str) -> bool:
        """Detect requests asking for top/best campaign performance, including typo variants."""
        text = (q or '').strip().lower()
        if not text:
            return False

        # Keep typo coverage local to intent matching in case normalization missed one.
        text = re.sub(r'\bcamapgin\b|\bcampagin\b|\bcompagin\b|\bcampain\b', 'campaign', text)

        campaign_word = re.search(r'\bcampaigns?\b', text) is not None
        has_best_signal = (
            'performing best' in text
            or 'best performing' in text
            or 'best campaign' in text
            or 'top campaign' in text
            or 'which campaign is best' in text
            or 'which is the best campaign' in text
            or (('best' in text or 'top' in text) and campaign_word)
        )
        return has_best_signal

    def _is_low_campaign_intent(self, q: str) -> bool:
        """Detect requests asking for low/worst campaign performance, including typo variants."""
        text = (q or '').strip().lower()
        if not text:
            return False

        text = re.sub(r'\bcamapgin\b|\bcampagin\b|\bcompagin\b|\bcampain\b', 'campaign', text)
        campaign_word = re.search(r'\bcampaigns?\b', text) is not None

        has_low_signal = (
            'performing worst' in text
            or 'worst performing' in text
            or 'worst campaign' in text
            or 'lowest campaign' in text
            or 'least performing campaign' in text
            or 'underperforming campaign' in text
            or 'poor performance campaign' in text
            or 'low performance campaign' in text
            or 'which campaign is worst' in text
            or 'which is the worst campaign' in text
            or ((
                'low' in text
                or 'lowest' in text
                or 'worst' in text
                or 'underperform' in text
                or 'poor' in text
                or 'bad' in text
            ) and campaign_word)
        )
        return has_low_signal

    # Pronouns/short-hands that refer back to whatever was discussed last turn.
    # SINGULAR back-references only. Plurals (them/they/their) refer to a whole
    # list, not one campaign, so resolving them to a single campaign is wrong.
    FOLLOWUP_REFS = (
        'it', 'its', "it's", 'that one', 'this one', 'the same',
        'same campaign', 'that campaign', 'this campaign', 'the campaign',
    )
    # If the question carries its own filter it is a fresh query, not a
    # follow-up about one campaign.
    FOLLOWUP_BLOCKERS = (
        'targeting', 'all campaigns', 'campaigns', 'which campaigns',
        'list', 'show me all', 'how many',
    )

    def _resolve_followup_campaign(self, question: str, campaigns: List[Dict],
                                   context: Optional[Dict]) -> Optional[Dict]:
        """When the question refers back ("what's ITS open rate?") instead of
        naming a campaign, find the campaign named in the recent conversation.
        Returns None when the question names no campaign and refers to none."""
        if not campaigns or not context:
            return None

        q = (question or '').strip().lower().rstrip('?!.')

        # A question that names its own scope ("campaigns targeting adults") is a
        # new query, not a follow-up about a single campaign.
        if any(b in q for b in self.FOLLOWUP_BLOCKERS):
            return None

        words = set(re.findall(r"[a-z']+", q))
        if not any((r in words) if ' ' not in r else (r in q) for r in self.FOLLOWUP_REFS):
            return None

        history = context.get('conversation_history') or []
        if not history:
            return None

        # Only the previous QUESTIONS. A previous answer may list many campaigns;
        # picking the first one from it would be arbitrary.
        for pair in reversed(history[-6:]):
            for key in ('question', 'q'):
                text = pair.get(key) or ''
                if not text:
                    continue
                found = self._find_campaign_in_question(text, campaigns)
                if found is not None:
                    return found
        return None

    def _find_campaign_in_question(self, question: str, campaigns: List[Dict]) -> Optional[Dict]:
        """Match a campaign name inside the question text (with fuzzy/partial support)."""
        q = (question or '').strip().lower()
        if not q or not campaigns:
            return None

        def _norm(s: str) -> str:
            s = (s or '').lower()
            s = re.sub(r'[^a-z0-9\s]+', ' ', s)
            return re.sub(r'\s+', ' ', s).strip()

        def _word_boundary_match(name: str, text: str) -> bool:
            """Check if name appears in text as whole words (not partial number/word overlap)."""
            pattern = r'(?<![a-z0-9])' + re.escape(name) + r'(?![a-z0-9])'
            return bool(re.search(pattern, text))

        def _word_similarity(word1: str, word2: str) -> float:
            """Simple character-level similarity (0-1). Handles typos."""
            if word1 == word2:
                return 1.0
            if not word1 or not word2:
                return 0.0
            # Check if one is a prefix/suffix of the other (e.g. 'sale' vs 'sales')
            if word1.startswith(word2) or word2.startswith(word1):
                return 0.85
            # Simple edit-distance ratio
            longer = max(len(word1), len(word2))
            common = sum(1 for a, b in zip(word1, word2) if a == b)
            return common / longer if longer > 0 else 0.0

        qn = _norm(q)
        qn_words = set(qn.split())

        # Collect all substring matches and pick the longest (most specific) one
        substring_match = None
        substring_match_len = 0

        best_match = None
        best_score = 0.0

        for c in campaigns:
            nn = _norm(c.get('name') or '')
            if not nn:
                continue

            # Exact substring match with word boundaries (avoids "sales 2" matching "sales 26")
            if nn in qn and _word_boundary_match(nn, qn):
                if len(nn) > substring_match_len:
                    substring_match = c
                    substring_match_len = len(nn)
                continue

            # All-words exact containment (each word must appear as whole word)
            name_words = [w for w in nn.split() if w]
            if len(name_words) >= 2 and all(w in qn_words for w in name_words):
                name_len = len(nn)
                if name_len > substring_match_len:
                    substring_match = c
                    substring_match_len = name_len
                continue

            # Fuzzy: check if each campaign-name word has a close match in question words
            if len(name_words) >= 2:
                word_scores = []
                for nw in name_words:
                    best_word_score = max(
                        (_word_similarity(nw, qw) for qw in qn_words),
                        default=0.0
                    )
                    word_scores.append(best_word_score)
                # Average similarity across all name words
                avg_score = sum(word_scores) / len(word_scores) if word_scores else 0.0
                # Require high avg similarity (all words roughly match)
                if avg_score > best_score and avg_score >= 0.75:
                    best_score = avg_score
                    best_match = c

        # Prefer exact substring matches over fuzzy matches
        return substring_match or best_match

    # ══════════════════════════════════════════════════════════
    #  DB DATA FETCH (unchanged from original)
    # ══════════════════════════════════════════════════════════

    def _get_marketing_data(self, user_id: Optional[int] = None) -> Dict:
        campaigns_query = Campaign.objects.all()
        if user_id:
            campaigns_query = campaigns_query.filter(owner_id=user_id)

        campaigns = list(campaigns_query.select_related('owner').prefetch_related('performance_metrics'))
        campaign_ids = [c.id for c in campaigns]

        email_stats = {}
        if campaign_ids:
            sent_statuses = ['sent', 'delivered', 'opened', 'clicked']
            for row in EmailSendHistory.objects.filter(campaign_id__in=campaign_ids).values('campaign_id').annotate(
                total_sent    = Count('id', filter=Q(status__in=sent_statuses)),
                total_opened  = Count('id', filter=Q(status__in=['opened', 'clicked'])),
                total_clicked = Count('id', filter=Q(status='clicked')),
                total_bounced = Count('id', filter=Q(status='bounced')),
                total_failed  = Count('id', filter=Q(status='failed')),
            ).order_by('campaign_id'):
                email_stats[row['campaign_id']] = row

        reply_stats = {}
        if campaign_ids:
            for row in Reply.objects.filter(campaign_id__in=campaign_ids).values('campaign_id').annotate(
                total_replied    = Count('id'),
                positive_replies = Count('id', filter=Q(interest_level__in=['positive', 'neutral', 'requested_info', 'objection'])),
                negative_replies = Count('id', filter=Q(interest_level__in=['negative', 'unsubscribe'])),
            ).order_by('campaign_id'):
                reply_stats[row['campaign_id']] = row

        lead_counts = {}
        if campaign_ids:
            for row in CampaignLead.objects.filter(campaign_id__in=campaign_ids).values('campaign_id').annotate(
                count=Count('id')
            ).order_by('campaign_id'):
                lead_counts[row['campaign_id']] = row['count']

        # Per-lead and per-reply detail. Only counts were fetched before, so
        # "who are meow's leads?" and "what did they say?" were unanswerable
        # even though the data exists. Capped per campaign to keep the context
        # manageable; the caps are reported so a truncated list is never
        # presented as complete.
        LEADS_PER_CAMPAIGN = 25
        REPLIES_PER_CAMPAIGN = 15
        leads_by_campaign = {}
        replies_by_campaign = {}
        reply_tally = {}
        if campaign_ids:
            for cl in (CampaignLead.objects
                       .filter(campaign_id__in=campaign_ids)
                       .select_related('lead')
                       .order_by('campaign_id', 'lead__email')):
                bucket = leads_by_campaign.setdefault(cl.campaign_id, [])
                if len(bucket) >= LEADS_PER_CAMPAIGN:
                    continue
                lead = cl.lead
                bucket.append({
                    'email': lead.email,
                    'name': ('%s %s' % (lead.first_name or '',
                                        lead.last_name or '')).strip(),
                    'company': lead.company or '',
                    'job_title': lead.job_title or '',
                    'status': lead.status or '',
                })

            # Per-lead reply tallies, counted over EVERY reply. The displayed
            # rows are capped, and building the tally from those capped rows
            # produced counts that did not match the data.
            # order_by() clears the model's default ordering — SQL Server
            # rejects an ORDER BY column that is not in the GROUP BY.
            for row in (Reply.objects
                        .filter(campaign_id__in=campaign_ids)
                        .values('campaign_id', 'lead__email', 'interest_level')
                        .annotate(n=Count('id'))
                        .order_by()):
                em = row['lead__email']
                if not em:
                    continue
                per = reply_tally.setdefault(row['campaign_id'], {})
                per.setdefault(em, {})[row['interest_level'] or 'not_analyzed'] = row['n']

            for rep in (Reply.objects
                        .filter(campaign_id__in=campaign_ids)
                        .select_related('lead')
                        .order_by('campaign_id', '-replied_at')):
                bucket = replies_by_campaign.setdefault(rep.campaign_id, [])
                if len(bucket) >= REPLIES_PER_CAMPAIGN:
                    continue
                bucket.append({
                    'lead_email': rep.lead.email if rep.lead_id else '',
                    'lead_name': (('%s %s' % (rep.lead.first_name or '',
                                              rep.lead.last_name or '')).strip()
                                  if rep.lead_id else ''),
                    'interest_level': rep.interest_level or '',
                    'subject': (rep.reply_subject or '')[:120],
                    'content': (rep.reply_content or '')[:400],
                    'replied_at': (rep.replied_at.isoformat()
                                   if rep.replied_at else None),
                })

        # Which emails actually went out. Only totals were fetched before, so
        # "what emails did this campaign send?" had nothing to draw on and the
        # model invented subject lines — and put the campaign's total against
        # every one of them.
        sends_by_campaign = {}
        if campaign_ids:
            for row in (EmailSendHistory.objects
                        .filter(campaign_id__in=campaign_ids)
                        .values('campaign_id', 'subject')
                        .annotate(n=Count('id'),
                                  opened=Count('id', filter=Q(status__in=['opened', 'clicked'])),
                                  clicked=Count('id', filter=Q(status='clicked')))
                        .order_by('campaign_id', '-n')):
                bucket = sends_by_campaign.setdefault(row['campaign_id'], [])
                if len(bucket) >= 20:
                    continue
                bucket.append({
                    'subject': row['subject'] or '(no subject)',
                    'sent': row['n'],
                    'opened': row['opened'],
                    'clicked': row['clicked'],
                })

        campaigns_data = []
        for campaign in campaigns:
            cid = campaign.id
            es  = email_stats.get(cid, {})
            rs  = reply_stats.get(cid, {})
            total_sent    = es.get('total_sent') or 0
            total_opened  = es.get('total_opened') or 0
            total_clicked = es.get('total_clicked') or 0
            total_bounced = es.get('total_bounced') or 0
            total_failed  = es.get('total_failed') or 0
            total_replied = rs.get('total_replied') or 0
            positive_replies = rs.get('positive_replies') or 0
            negative_replies = rs.get('negative_replies') or 0
            leads_count = lead_counts.get(cid, 0)

            target_leads        = getattr(campaign, 'target_leads', None)
            target_conversions  = getattr(campaign, 'target_conversions', None)
            conversion_progress = round((positive_replies / target_conversions * 100), 1) if target_conversions and target_conversions > 0 else None
            leads_progress      = round((leads_count / target_leads * 100), 1) if target_leads and target_leads > 0 else None
            open_rate    = round((total_opened  / total_sent) * 100, 2) if total_sent > 0 else None
            click_rate   = round((total_clicked / total_sent) * 100, 2) if total_sent > 0 else None
            reply_rate   = round((total_replied / total_sent) * 100, 2) if total_sent > 0 else None
            bounce_rate  = round((total_bounced / total_sent) * 100, 2) if total_sent > 0 else None

            metrics_prefetched = list(campaign.performance_metrics.all())[:20]
            campaigns_data.append({
                'id': campaign.id, 'name': campaign.name, 'type': campaign.campaign_type,
                'status': campaign.status,
                'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
                'end_date':   campaign.end_date.isoformat()   if campaign.end_date   else None,
                'metrics': [
                    {'name': m.metric_name, 'value': float(m.metric_value),
                     'date': m.date.isoformat(), 'channel': m.channel}
                    for m in metrics_prefetched
                ],
                'goals': campaign.goals, 'channels': campaign.channels,
                # Targeting/demographics — needed for questions that filter on
                # audience ("campaigns targeting young adults", "which target
                # healthcare"). These live on the model but were never read.
                'age_range': getattr(campaign, 'age_range', '') or '',
                'location': getattr(campaign, 'location', '') or '',
                'industry': getattr(campaign, 'industry', '') or '',
                'company_size': getattr(campaign, 'company_size', '') or '',
                'interests': getattr(campaign, 'interests', '') or '',
                'language': getattr(campaign, 'language', '') or '',
                'target_audience': getattr(campaign, 'target_audience', None) or {},
                # Creation date — needed for "when was the last campaign
                # created?" / "how many did I create last Tuesday?", which
                # previously answered "not provided in the context".
                'created_at': campaign.created_at.isoformat() if getattr(campaign, 'created_at', None) else None,
                'description': (getattr(campaign, 'description', '') or '')[:300],
                'target_leads': target_leads, 'target_conversions': target_conversions,
                'leads': leads_by_campaign.get(cid, []),
                'replies': replies_by_campaign.get(cid, []),
                'reply_tally': (reply_tally or {}).get(cid, {}),
                'sent_emails': sends_by_campaign.get(cid, []),
                'leads_count': leads_count, 'positive_replies': positive_replies,
                'negative_replies': negative_replies, 'conversions': positive_replies,
                'conversion_progress': conversion_progress, 'leads_progress': leads_progress,
                'emails_sent': total_sent, 'emails_opened': total_opened,
                'emails_clicked': total_clicked, 'emails_replied': total_replied,
                'emails_bounced': total_bounced, 'emails_failed': total_failed,
                'open_rate': open_rate, 'click_rate': click_rate,
                'reply_rate': reply_rate, 'bounce_rate': bounce_rate,
            })

        research_query = MarketResearch.objects.all()
        if user_id:
            research_query = research_query.filter(created_by_id=user_id)

        research_data = [
            {'id': r.id, 'type': r.research_type, 'topic': r.topic,
             'insights': r.insights, 'findings': r.findings,
             'created_at': r.created_at.isoformat()}
            for r in research_query[:10]
        ]

        active_campaigns = campaigns_query.filter(status='active').count()
        all_metrics = CampaignPerformance.objects.filter(
            campaign__in=campaigns_query
        ).values('metric_name').annotate(
            avg_value=Avg('metric_value'), total_count=Count('id')
        ).order_by('metric_name')

        return {
            'campaigns': campaigns_data,
            'research': research_data,
            'stats': {
                'total_campaigns': len(campaigns_data),
                'active_campaigns': active_campaigns,
                'performance_metrics': list(all_metrics),
            }
        }

    # ══════════════════════════════════════════════════════════
    #  LLM CONTEXT BUILDER (for _handle_llm_reasoning only)
    # ══════════════════════════════════════════════════════════

    def _build_context(self, marketing_data: Dict, additional_context: Optional[Dict] = None,
                       question: str = '') -> str:
        parts = []

        parts.append(
            "PLATFORM CONTEXT: This is the **Marketing Agent** platform with tabs: "
            "Research, Q&A, Campaigns, Notifications, Outreach. "
            "To run a campaign: Campaigns tab → create → add leads → set emails → launch.\n\n"
        )

        conv_history = (additional_context or {}).get('conversation_history') or []
        if conv_history:
            parts.append(
                "RECENT CONVERSATION — background only. Use it to resolve "
                "pronouns ('it', 'that one'). If the new question stands on its "
                "own, answer it over ALL campaigns and ignore what came before; "
                "do not narrow it to the campaigns discussed earlier.")
            for i, pair in enumerate(conv_history[-4:], 1):
                q = pair.get('question') or pair.get('q') or ''
                a = pair.get('answer') or pair.get('a') or ''
                if q or a:
                    parts.append(f"  Q{i}: {q}")
                    parts.append(f"  A{i}: {a[:500]}{'...' if len(a) > 500 else ''}")
            parts.append("")

            # Name the subject explicitly. Left to infer it from the transcript,
            # the model drifted: asked "how many leads does IT have?" about one
            # campaign it answered for three, and "is that realistic?" about a
            # conversion target it answered about every campaign's status.
            subject = self._subject_of_conversation(conv_history, marketing_data, question)
            if subject:
                # Resolve pronouns to this campaign, but do NOT lock the answer
                # to it. An earlier version said "Answer ONLY about X", which
                # made "what about the OTHERS?" and "how do I improve my other
                # campaigns?" keep answering about X — the exact opposite of
                # what was asked.
                parts.append(
                    "LAST CAMPAIGN DISCUSSED: %s\n"
                    "Use this to resolve 'it', 'its', 'that', 'this' in the new "
                    "question. It is NOT a restriction: if the question says "
                    "'the others', 'other campaigns', 'the rest', or names "
                    "different campaigns, answer about THOSE and exclude %s. "
                    "If the question is general, answer generally.\n"
                    % (subject, subject)
                )

        context = "\n".join(parts)
        context += "MARKETING DATA:\n\n"

        stats = marketing_data.get('stats', {})
        context += f"OVERVIEW:\n- Total Campaigns: {stats.get('total_campaigns', 0)}\n- Active: {stats.get('active_campaigns', 0)}\n\n"

        campaigns = marketing_data.get('campaigns', [])
        if campaigns:
            # Send EVERY campaign, with its targeting fields. Truncating to 5 and
            # omitting audience data made whole classes of question unanswerable
            # ("which campaigns target young adults?").
            context += (
                "FIELD MEANINGS:\n"
                "- sent = emails actually delivered. sent=0 means the campaign "
                "has NOT run yet, so it has produced no results of any kind.\n"
                "- leads = contacts uploaded. Uploading leads is not progress; "
                "nothing happens until emails are sent.\n"
                "- positive_replies = leads who replied WITH INTEREST. This is "
                "the only real signal of a deal in progress. A campaign is "
                "'close to converting' only if positive_replies > 0.\n"
                "- status: draft = never launched, paused = stopped, "
                "active = running.\n"
                "- A draft campaign with sent=0 is the FURTHEST from closing a "
                "deal, never the closest.\n"
                "- Some campaigns have more replies than emails sent (rates over "
                "100%), because replies were recorded from earlier sends that are "
                "no longer in the send history. Report such rates as-is if asked, "
                "but rank by the raw counts (positive_replies), not by the "
                "percentage, and don't claim a >100% rate is an error.\n\n"
            )
            # Pre-computed counts. The model was answering "no campaign has sent
            # emails yet" while two rows clearly showed sent=7 and sent=24 — it
            # generalised from the majority of rows instead of checking each one.
            # Stating the totals up front removes the need for it to count.
            sent_c = [c for c in campaigns if (c.get('emails_sent') or 0) > 0]
            pos_c = [c for c in campaigns if (c.get('positive_replies') or 0) > 0]
            lead_c = [c for c in campaigns if (c.get('leads_count') or 0) > 0]
            none_c = [c for c in campaigns if (c.get('emails_sent') or 0) == 0]
            lead_nosend_c = [c for c in lead_c if (c.get('emails_sent') or 0) == 0]

            def _nm(rows):
                return ", ".join(c.get('name', 'Unnamed') for c in rows) or "(none)"

            # Age brackets, resolved here rather than by the model. Asked which
            # campaigns "target children under 10" it answered "below age11"
            # — a campaign whose age range is 25-45 — because the NAME sounded
            # right. Ranges are arithmetic, so compute them.
            def _age_bounds(c):
                raw = str(c.get('age_range') or '').strip()
                if not raw:
                    return None
                m = re.match(r'^(\d+)\s*[-–]\s*(\d+)$', raw)
                if m:
                    return int(m.group(1)), int(m.group(2))
                if re.match(r'^\d+$', raw):
                    n = int(raw)
                    return n, n
                return None

            def _overlaps(c, lo, hi):
                b = _age_bounds(c)
                return b is not None and b[0] <= hi and b[1] >= lo

            kids_c = [c for c in campaigns if _overlaps(c, 0, 12)]
            teens_c = [c for c in campaigns if _overlaps(c, 13, 17)]
            adults_c = [c for c in campaigns if _overlaps(c, 18, 120)]
            noage_c = [c for c in campaigns if _age_bounds(c) is None]

            def _nm_age(rows):
                if not rows:
                    return "(none)"
                return ", ".join("%s [%s]" % (c.get('name', 'Unnamed'),
                                              c.get('age_range') or '?')
                                 for c in rows)

            # Explicit low/high per campaign. The fixed brackets above only
            # answer child/teen/adult; an arbitrary range ("between 10 and 20")
            # still had to be worked out, and the model kept answering "no
            # campaigns match" while listing matches in the same breath.
            _age_rows = []
            for c in campaigns:
                b = _age_bounds(c)
                _age_rows.append(
                    "  %s: low=%s high=%s" % (c.get('name', 'Unnamed'), b[0], b[1])
                    if b else
                    "  %s: no age range set" % c.get('name', 'Unnamed')
                )
            age_table = "\n".join(_age_rows)
            # Without today's date the model cannot resolve "last Tuesday",
            # "this month", "recently" against the created= values.
            _today = datetime.now()
            context += "TODAY: %s (%s)\n\n" % (
                _today.strftime('%Y-%m-%d'), _today.strftime('%A'))
            # MEMBERSHIP, not just counts. With counts alone the model still
            # claimed "none have sent emails" while two rows showed sent=7 and
            # sent=24, and listed leads=0 rows as "campaigns with leads".
            # Naming the members leaves nothing for it to derive or mis-read.
            context += (
                "PRE-COMPUTED FACTS (authoritative — quote these, never "
                "re-derive them from the rows below):\n"
                "- HAVE SENT EMAILS (%d): %s\n"
                "- HAVE SENT NOTHING (%d): %s\n"
                "- HAVE POSITIVE REPLIES (%d): %s\n"
                "- HAVE LEADS UPLOADED (%d): %s\n"
                "- HAVE LEADS BUT NEVER SENT (%d): %s\n"
                "- TARGET CHILDREN, age 0-12 (%d): %s\n"
                "- TARGET TEENS, age 13-17 (%d): %s\n"
                "- TARGET ADULTS, age 18+ (%d): %s\n"
                "- NO AGE RANGE SET (%d): %s\n"
                "\nAGE RANGES, low-high per campaign (for ANY age question, "
                "including ranges not listed above):\n%s\n"
                "OVERLAP RULE: a campaign matches an asked range A-B when its "
                "low <= B AND its high >= A. Example: asking 10-20, a campaign "
                "with 18-35 MATCHES (18 <= 20 and 35 >= 10). Apply this test to "
                "every row above before answering — most ranges overlap far more "
                "campaigns than you would guess.\n"
                "A campaign NOT in a list does NOT have that property. Never "
                "name a campaign as having leads, sends or replies unless it "
                "appears in the matching list above. 'No campaign has sent "
                "emails' is true ONLY if the first list is (none).\n"
                "The age lists are computed from the age= numbers, not from "
                "campaign names. A name like 'below age11' means nothing — only "
                "its age range counts. Answer age questions from these lists.\n\n"
                % (len(sent_c), _nm(sent_c),
                   len(none_c), _nm(none_c),
                   len(pos_c), _nm(pos_c),
                   len(lead_c), _nm(lead_c),
                   len(lead_nosend_c), _nm(lead_nosend_c),
                   len(kids_c), _nm_age(kids_c),
                   len(teens_c), _nm_age(teens_c),
                   len(adults_c), _nm_age(adults_c),
                   len(noage_c), _nm(noage_c),
                   age_table)
            )
            # Totals and averages, computed here. Asked "what's the average?"
            # the model produced 11.5 and 1.11 in the same reply and asserted
            # both — arithmetic over 18 rows is not something to delegate.
            def _sum(key):
                return sum((c.get(key) or 0) for c in campaigns)

            def _avg_over(key, rows):
                return (sum((c.get(key) or 0) for c in rows) / len(rows)) if rows else 0

            n_all = len(campaigns) or 1
            rates = [(c, c.get('open_rate')) for c in sent_c
                     if c.get('open_rate') is not None]
            avg_open = (sum(r for _, r in rates) / len(rates)) if rates else None
            context += (
                "TOTALS AND AVERAGES (already computed — quote these, never "
                "recalculate):\n"
                "- total leads: %d | total emails sent: %d | total positive "
                "replies: %d | total conversions: %d\n"
                "- avg leads per campaign: %.2f over all %d, or %.2f over the "
                "%d that have leads\n"
                "- avg positive replies: %.2f over all %d, or %.2f over the %d "
                "that have sent emails\n"
                "- avg open rate: %s (over the %d campaigns that sent emails; "
                "the other %d have no rate at all)\n"
                "When asked for 'the average' without saying of what, give the "
                "figure over campaigns that actually have the data, state which "
                "denominator you used, and give ONE number — never two.\n\n"
                % (_sum('leads_count'), _sum('emails_sent'), _sum('positive_replies'),
                   _sum('positive_replies'),
                   _sum('leads_count') / n_all, len(campaigns),
                   _avg_over('leads_count', lead_c), len(lead_c),
                   _sum('positive_replies') / n_all, len(campaigns),
                   _avg_over('positive_replies', sent_c), len(sent_c),
                   ("%.2f%%" % avg_open) if avg_open is not None else "n/a",
                   len(rates), len(campaigns) - len(rates))
            )
            context += "CAMPAIGNS (all %d — this is the COMPLETE list):\n" % len(campaigns)
            for c in campaigns[:60]:
                targeting = []
                if c.get('age_range'):
                    targeting.append("age=%s" % c['age_range'])
                if c.get('location'):
                    targeting.append("location=%s" % c['location'])
                if c.get('industry'):
                    targeting.append("industry=%s" % c['industry'])
                if c.get('company_size'):
                    targeting.append("company_size=%s" % c['company_size'])
                if c.get('interests'):
                    targeting.append("interests=%s" % c['interests'])
                if c.get('language'):
                    targeting.append("language=%s" % c['language'])
                targeting_str = "; ".join(targeting) if targeting else "no targeting set"

                # positive_replies is what actually signals a deal in progress —
                # a lead who answered with interest. Without it the model has to
                # guess from lead counts, and picks campaigns that never sent an
                # email as "about to close".
                created = (c.get('created_at') or '')[:10] or 'unknown'
                context += (
                    "- %s (%s): created=%s, sent=%s, opened=%s, replied=%s, "
                    "positive_replies=%s, negative_replies=%s, "
                    "open=%s%%, click=%s%%, reply=%s%%, "
                    "leads=%s, conversions=%s/%s, conv_progress=%s%%, "
                    "runs=%s to %s "
                    "| TARGETING: %s\n" % (
                        c.get('name', 'Unnamed'), c.get('status', 'N/A'),
                        created,
                        c.get('emails_sent', 0), c.get('emails_opened', 0),
                        c.get('emails_replied', 0),
                        c.get('positive_replies', 0), c.get('negative_replies', 0),
                        c.get('open_rate', 'N/A'), c.get('click_rate', 'N/A'),
                        c.get('reply_rate', 'N/A'),
                        c.get('leads_count', 'N/A'),
                        c.get('positive_replies', 0),
                        c.get('target_conversions') if c.get('target_conversions') is not None else 'N/A',
                        c.get('conversion_progress', 'N/A'),
                        c.get('start_date') or 'not set',
                        c.get('end_date') or 'not set',
                        targeting_str,
                    )
                )
            if len(campaigns) > 60:
                context += "  (...%d more not shown)\n" % (len(campaigns) - 60)

            # Lead and reply detail, only when the question is about them.
            # Included always it would dominate every answer and cost tokens on
            # questions that never touch it.
            q_low = (question or '').lower()
            wants_leads = self._mentions(
                q_low, 'lead', 'leads', 'contact', 'contacts', 'who', 'whom',
                'email address', 'addresses', 'people')
            # A follow-up about people carries no such word ("to which campaign
            # do they belong?"), so fall back to the previous question.
            if not wants_leads:
                prev_low = (self._previous_question(additional_context) or '').lower()
                if (re.search(r'\b(lead|leads|contact|contacts|people)\b', prev_low)
                        and re.search(r'\b(they|them|their|these|those|it)\b', q_low)):
                    wants_leads = True
            wants_replies = self._mentions(
                q_low, 'reply', 'replies', 'replied', 'respond', 'response',
                'responded', 'said', 'wrote', 'feedback', 'interested',
                'interest level', 'unsubscribe', 'unsubscribed', 'positive',
                'negative', 'objection')
            # "which CAMPAIGNS have sent emails" asks which campaigns, not what
            # was in them — it must not pull in every subject line.
            # Written loosely on purpose: "what were the emails sent by X"
            # failed a tighter pattern because of the words between "what" and
            # "emails".
            wants_sends = bool(
                re.search(r'\b(subject|subjects|email content)\b', q_low)
                or re.search(r'\b(what|which|show|list|tell)\b[^.?]{0,30}'
                             r'\b(emails?|messages?)\b', q_low)
                or re.search(r'\bemails?\b[^.?]{0,20}\b(sent|went out)\b', q_low)
            ) and not re.search(r'\bwhich campaigns?\b', q_low)

            if wants_leads or wants_replies or wants_sends:
                context += "\n"
                for c in campaigns[:60]:
                    leads = c.get('leads') or []
                    replies = c.get('replies') or []
                    sends = c.get('sent_emails') or []
                    if not leads and not replies and not sends:
                        continue
                    context += "DETAIL for %s:\n" % c.get('name', 'Unnamed')
                    if wants_sends and sends:
                        context += (
                            "  Emails sent, grouped by subject (these counts "
                            "add up to the campaign total — do NOT put the "
                            "campaign total against each subject):\n")
                        for S in sends:
                            context += (
                                "    - subject: %s | sent: %d | opened: %d | "
                                "clicked: %d\n" % (
                                    S.get('subject'), S.get('sent', 0),
                                    S.get('opened', 0), S.get('clicked', 0)))
                    if wants_leads and leads:
                        context += "  Leads (%d of %d):\n" % (
                            len(leads), c.get('leads_count') or len(leads))
                        for L in leads:
                            # Every field is labelled and always present, even
                            # when empty. Appending company only when set made
                            # the model treat it as optional and drop it from
                            # answers that asked for it.
                            context += (
                                "    - name: %s | email: %s | company: %s | "
                                "job title: %s | status: %s\n" % (
                                    L.get('name') or 'not set',
                                    L.get('email') or 'not set',
                                    L.get('company') or 'not set',
                                    L.get('job_title') or 'not set',
                                    L.get('status') or 'unknown'))
                    if wants_replies and replies:
                        # Spell out how many PEOPLE these replies came from.
                        # Given only the rows, the model listed one lead twice
                        # because that lead had replied twice.
                        senders = {R.get('lead_email') for R in replies
                                   if R.get('lead_email')}
                        # Who replied and who stayed silent, worked out here.
                        # Given the two lists separately the model had to
                        # intersect them itself and returned every lead as a
                        # non-replier.
                        lead_emails = {L.get('email') for L in (c.get('leads') or [])
                                       if L.get('email')}
                        if lead_emails:
                            replied = sorted(senders & lead_emails)
                            silent = sorted(lead_emails - senders)
                            context += (
                                "  Replied at least once (%d): %s\n"
                                "  Never replied (%d): %s\n" % (
                                    len(replied), ", ".join(replied) or "(none)",
                                    len(silent), ", ".join(silent) or "(none)"))

                        # Reply types PER LEAD. Asked "what types of replies
                        # from all leads of X", the model returned the lead
                        # list with no types attached — it had the rows but not
                        # the per-person tally.
                        # Counted over every reply, not just the rows shown.
                        per_lead = c.get('reply_tally') or {}
                        if per_lead:
                            # Name the campaign on the heading. Without it the
                            # table read as account-wide and the answer never
                            # said whose replies these were.
                            context += (
                                "  (the table below is for %s only, and has %d "
                                "rows — reproduce every one)\n" % (
                                    c.get('name', 'Unnamed'),
                                    len(lead_emails or per_lead)))
                            context += "  Reply types per lead:\n"
                            for em in sorted(lead_emails or per_lead):
                                counts = per_lead.get(em)
                                context += "    %s -> %s\n" % (
                                    em,
                                    ", ".join("%s x%d" % (k, v) for k, v in
                                              sorted(counts.items(),
                                                     key=lambda t: -t[1]))
                                    if counts else "no replies")
                        # Pre-counted so "what reply types did we get?" is a
                        # lookup rather than a tally across rows.
                        kinds = {}
                        for R in replies:
                            k = R.get('interest_level') or 'not_analyzed'
                            kinds[k] = kinds.get(k, 0) + 1
                        context += (
                            "  Replies (%d reply rows from %d distinct "
                            "lead(s) — the same person can appear more than "
                            "once):\n"
                            "  Reply types here: %s\n" % (
                                len(replies), len(senders),
                                ", ".join("%s=%d" % (k, v) for k, v
                                          in sorted(kinds.items(),
                                                    key=lambda t: -t[1]))))
                        for R in replies:
                            context += (
                                "    - %s <%s> [%s] on %s\n"
                                "      subject: %s\n"
                                "      says: %s\n" % (
                                    R.get('lead_name') or '(no name)',
                                    R.get('lead_email'),
                                    R.get('interest_level') or 'not analysed',
                                    (R.get('replied_at') or '')[:10],
                                    R.get('subject') or '(none)',
                                    (R.get('content') or '(empty)').replace('\n', ' ')))
                # Which campaigns each lead belongs to. The detail above is
                # grouped BY campaign, so "which campaign do they belong to?"
                # had to be inferred by scanning every block — the model
                # answered with campaign metrics instead.
                if wants_leads:
                    lead_to_campaigns = {}
                    for c in campaigns[:60]:
                        for L in (c.get('leads') or []):
                            em = L.get('email')
                            if em:
                                lead_to_campaigns.setdefault(em, []).append(
                                    c.get('name', 'Unnamed'))
                    if lead_to_campaigns:
                        context += "\nLEAD -> CAMPAIGNS (which campaigns each lead is on):\n"
                        for em, names in sorted(lead_to_campaigns.items()):
                            context += "  %s -> %s\n" % (em, ", ".join(names))

                context += (
                    "\nThese lists are capped (25 leads, 15 replies per "
                    "campaign). If a campaign's lead count is higher than the "
                    "number shown, say the list is partial rather than "
                    "presenting it as everyone.\n"
                    "When asked about leads, answer with the LEAD ROWS above — "
                    "give every field each row carries (name, email, company, "
                    "job title, status), not just the ones you consider "
                    "interesting. 'Details of leads' means the people, not the "
                    "campaign's metrics: do not answer it with sent/opened/"
                    "reply-rate figures.\n"
                    "Subject lines exist ONLY in the 'Emails sent' rows above. "
                    "Never write a subject line that is not listed there, and "
                    "never repeat the campaign's total against each subject — "
                    "each row already carries its own count.\n"
                    "When listing PEOPLE, each lead appears ONCE however many "
                    "times they replied. If one lead sent three replies, that "
                    "is still one lead — say '1 lead (3 replies)', never the "
                    "same person three times. Count the distinct email "
                    "addresses, not the reply rows.\n")

        research = marketing_data.get('research', [])
        if research:
            context += "\nMARKET RESEARCH (for strategy questions only):\n"
            for r in research[:3]:
                context += f"- {r['type']}: {r['topic']}\n"

        if additional_context:
            extra = {k: v for k, v in additional_context.items() if k != 'conversation_history'}
            if extra:
                context += f"\nADDITIONAL CONTEXT:\n{json.dumps(extra, indent=2)}\n"

        return context

    def _generate_answer(self, question: str, context: str, request_context: Optional[Dict] = None) -> str:
        prompt = (
            f'Answer this question using the provided context: "{question}"\n\n'
            f"{context}\n\n"
            "RULES:\n"
            "- Be direct — no filler like 'based on...'. Keep prose short, but "
            "NEVER drop data the question asked for. Length follows the question: "
            "a yes/no gets one line, 'list all campaigns with X, Y and Z' gets a "
            "full row per campaign.\n"
            "- ANSWER EVERY PART OF THE QUESTION. If the user names fields "
            "(leads, industry, country, open rate, ages...), show EACH named "
            "field for EACH campaign, as 'name (status) - field: value, "
            "field: value'. Listing just names and statuses when specific "
            "fields were requested is a wrong answer.\n"
            "- If a requested field is empty for a campaign, print it as "
            "'not set' rather than leaving it out.\n"
            "- The CAMPAIGNS list above is COMPLETE. Never invent a campaign that "
            "is not in it, and never invent metrics or targeting values.\n"
            "- YOU ONLY KNOW WHAT IS IN THIS CONTEXT. If the answer is not in "
            "the data above, say 'I don't have that information' and stop. This "
            "applies especially to outside facts — API pricing, model costs, "
            "industry benchmarks, competitor numbers, news, dates, definitions. "
            "You have no access to them, and a number that looks plausible is "
            "still a fabrication. Never state a figure you cannot point to a "
            "line of the context for.\n"
            "- STAY IN SCOPE. You answer questions about THIS account's "
            "marketing data. General knowledge is out of scope even when you "
            "happen to know it: geography, history, science, celebrities, "
            "current events, other companies' pricing, coding help, recipes. "
            "For those reply exactly: \"That's outside what I can help with — "
            "I answer questions about your campaigns and marketing data.\" Do "
            "not answer and then add a disclaimer; just decline.\n"
            "- Do not produce creative writing (poems, songs, stories, jokes) "
            "even about the campaign data. Say you can summarise the data "
            "instead, and offer the summary.\n"
            "- OPEN WITH THE ANSWER. Name the campaign(s) in the first sentence "
            "(e.g. 'new1234 performs best: 13 positive replies from 24 sent'). "
            "Never open with 'No campaigns match that' when campaigns follow in "
            "the same reply — that contradicts itself.\n"
            "- Write 'No campaigns match that.' ONLY when your entire reply names "
            "zero campaigns, i.e. the filter genuinely matched nothing. Then say "
            "what the campaigns DO have, so the user can adjust. Never list every "
            "campaign as if it answered the question.\n"
            "- A vague question ('which one is good?', 'which is best?', 'sab se "
            "achi konsi hai?') always HAS an answer: rank the campaigns by the "
            "most sensible metric, name the winner, and say which metric you "
            "used. It is never an unmatched filter.\n"
            "- A campaign matches an audience filter ONLY if its TARGETING line "
            "actually says so. 'no targeting set' or a missing age means UNKNOWN "
            "— such a campaign must be EXCLUDED from the matching list, never "
            "counted as a match. Do not guess from the campaign's name.\n"
            "- When filtering by age, compare against the campaign's age= value. "
            "'adults' means 18+; a range like 10-30 means the campaign's range "
            "must overlap it. State each matching campaign's actual age range.\n"
            "- Start a filtered answer with the count, e.g. '3 of 17 campaigns "
            "target ...', then list only those, each with its age range. If the "
            "rest have no targeting set, say so in one short line.\n"
            "- You can only READ data. You cannot create, edit, delete, pause, "
            "launch or send anything. If asked to perform an action, say you "
            "can't do it and point to the relevant tab in the UI. NEVER claim an "
            "action was done.\n"
            "- For follow-ups like 'it', 'that campaign', 'their', 'them', use the "
            "campaign(s) named in RECENT CONVERSATION above instead of asking "
            "which one. 'What is THEIR number of leads?' means the campaigns from "
            "your previous answer — give each one's leads, not the account total.\n"
            "- For counts and totals, COUNT the rows in the CAMPAIGNS list above. "
            "Do not estimate. When asked for a total, add up the per-campaign "
            "values and show the arithmetic briefly if more than two numbers.\n"
            "- For 'highest/lowest/best/worst', compare the relevant number across "
            "ALL campaigns listed and name the winner(s) with the value. If two "
            "tie, say both.\n"
            "- Always answer with something concrete. Never reply with an empty "
            "message. If the question is unclear, say what you think was meant and "
            "answer that, or ask one short clarifying question.\n"
            "- The context above is working material, not the answer. Never "
            "reproduce its headings, instructions, per-condition counts, raw "
            "field names or operators (emails_sent, duration_days, '> 7', "
            "'!='). Write for someone who has never seen the data model: "
            "'campaigns that ran longer than a week', not 'duration_days > 7'.\n"
            "- Read FIELD MEANINGS above before ranking anything. For questions "
            "about progress, conversions, or 'closing deals', rank by "
            "positive_replies. Never present a draft campaign that has sent 0 "
            "emails as the closest to converting.\n"
            "- BEFORE answering 'none', CHECK EVERY ROW of the CAMPAIGNS list. "
            "Answer 'none' ONLY when literally zero rows qualify. Most campaigns "
            "having sent=0 does NOT mean all of them do — if even one row has "
            "sent>0 or positive_replies>0, that row IS the answer. Saying 'no "
            "campaign has sent emails' while rows show sent=7 and sent=24 is "
            "flatly wrong.\n"
            "- Never contradict yourself: if you say nothing matches and then "
            "list matching rows, the correct answer was the list. Decide from "
            "the data first, then write one consistent answer. Never show two "
            "different values for the same figure and let the reader choose — "
            "work it out, then state one number.\n"
            "- THE COUNT MUST MATCH THE LIST. If you open with 'N campaigns...', "
            "N must equal how many you then list. Write the list first, count "
            "its rows, and use that number. Saying '6 campaigns' above a list "
            "of 16 is a wrong answer.\n"
            "- A counting or filtering question covers ALL 18 campaigns unless "
            "the user restricts it. 'How many were created before August?' means "
            "every campaign, not just the ones discussed a moment ago. Check the "
            "created= value of each row before answering.\n"
            "- BUT a request to re-present the last answer ('just show their "
            "names', 'with their dates', 'shorter') keeps the SAME set of "
            "campaigns you just listed. Change only the formatting — never widen "
            "it back to every campaign.\n"
            "- 'and how much did they achieve?' after a filtered list means: for "
            "EACH campaign in that list, give the figure. One row per campaign, "
            "never a single account-wide total. The same goes for 'their leads', "
            "'their dates', 'their rates'.\n"
            "- 'mention its detail' / 'more detail' / 'break it down' asks for "
            "the full row(s) of whatever was just discussed — every field you "
            "have for them. Never answer that with 'I don't have that "
            "information': you have the rows in the CAMPAIGNS list.\n"
            "- A bare 'why?' asks you to justify the answer you JUST gave, using "
            "the numbers behind it. You always have those — they are in the "
            "context. 'I don't have that information' is never a valid reply to "
            "'why?'.\n"
            "- A follow-up asks for something NEW about the same subject — never "
            "repeat your previous answer verbatim. 'and why?' wants the reasoning "
            "and the numbers behind what you just said, not the same sentence "
            "again.\n"
            "- 'the others' / 'other campaigns' / 'the rest' / 'my other X' means "
            "EXCLUDE the campaign(s) you just discussed and answer about the "
            "remaining ones. Naming the same campaign again is a wrong answer. "
            "If the remaining campaigns are many and similar, group them (e.g. "
            "'the 15 drafts have sent nothing — launch or delete them') instead "
            "of listing every row.\n"
            "- 'How do I improve X' asks for ADVICE, not a metric dump. Give "
            "concrete steps tied to what the data shows is weak (never launched, "
            "no leads uploaded, low open rate, no targeting set). Restating the "
            "numbers is not advice.\n"
            "- Answer the question that was ACTUALLY asked. If it does not "
            "follow from the previous turn, treat it as a fresh question rather "
            "than bending it to fit the last topic. If a question is about the "
            "platform, your own limits, or anything outside the campaign data "
            "(e.g. 'is the limit reset?'), say you don't have that information "
            "instead of answering it with campaign metrics.\n"
            "- 'Best' is ambiguous: say which metric you ranked by, and if a "
            "different metric would give a different winner, mention that in one "
            "clause (e.g. 'by positive replies X leads; by open rate Y does').\n"
            "- 'Performing best/worst' means RESULTS, so only campaigns with "
            "sent>0 can be ranked. A campaign that never sent an email has no "
            "performance at all — never call it the best performer just because "
            "it has leads. Rank among sent>0 rows only.\n"
            "- A judgement question ('is that realistic?', 'is it good?') is "
            "about the NUMBER just discussed. Answer it with arithmetic on that "
            "campaign: compare the target against what it has achieved so far "
            "and its send volume, then say realistic or not and why. Do not "
            "answer with the status of every campaign in the account.\n"
            "- Never say 'all campaigns are X' unless every single row is X. "
            "Check the status values in the list before making a claim about "
            "all of them.\n"
            "- created=YYYY-MM-DD is when the campaign was created; runs=... is "
            "its scheduled window. Use created= for 'when was it made / created "
            "last week'. There is no budget or spend data — if asked, say that "
            "field isn't tracked rather than guessing.\n"
            "- 'age' about a CAMPAIGN means the audience age range it targets "
            "(the age= value), never how old the campaign is. 'All campaigns "
            "with their age' means name + age range, not creation dates.\n"
            "- When you name a winner, quote the number that makes it the winner.\n"
        )
        # 700 tokens could not hold a full per-campaign listing: the answer was
        # cut off mid-row ("below age11 (draft) - sent:0, opened:0, ...open"),
        # which reads as the assistant ignoring half the question. Size the
        # budget to what the question actually asks for.
        n_campaigns = 0
        m = re.search(r'CAMPAIGNS \(all (\d+)', context or '')
        if m:
            n_campaigns = int(m.group(1))

        q = (question or '').lower()
        wants_all = any(w in q for w in (
            'all', 'each', 'every', 'list', 'their information', 'full detail',
            'details of', 'mention their', 'along with',
        ))
        if wants_all and n_campaigns:
            # A detailed row measures ~85 tokens, but the budget also has to
            # cover whatever the model spends thinking before it writes. Sizing
            # purely off the visible text left the answer cut off at 10 of 18
            # rows, so allow 3x the raw row cost with a generous floor.
            max_tokens = min(8000, max(2500, 400 + n_campaigns * 250))
        else:
            max_tokens = 1500

        try:
            return self._call_llm_for_reasoning(
                prompt, self.system_prompt, temperature=0.3, max_tokens=max_tokens
            )
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower():
                return "The service is busy. Please try again in a few seconds."
            return "Analysis could not be completed at this time. Please try again."

    OUT_OF_SCOPE_SYSTEM = (
        "You gate questions for an assistant that ONLY answers questions about "
        "one company's own marketing campaigns (their metrics, targeting, "
        "leads, emails, dates) and marketing advice about them.\n"
        "Reply with exactly one word.\n\n"
        "allow  - about this account's campaigns/marketing, or advice on them. "
        "Each campaign stores TARGETING fields: age range, location, industry, "
        "company size, interests, language. Questions about those are ALWAYS "
        "allowed — 'what is their company size?' asks which company size a "
        "campaign targets, and 'show their industries' asks which industries "
        "they target. Neither is a question about outside companies.\n"
        "reject - general knowledge (geography, history, science, celebrities, "
        "news), OTHER companies' pricing or products, coding help, recipes, "
        "creative writing (poems, songs, stories, jokes), or anything else "
        "unrelated to this account's marketing data.\n\n"
        "A question does NOT have to mention the word 'campaign'. Short "
        "follow-ups, comparisons, and campaign names on their own are part of "
        "an ongoing conversation about the data — allow them. When unsure, "
        "ALLOW: wrongly blocking a real question is far worse than answering a "
        "borderline one.\n\n"
        "Examples:\n"
        "'which campaigns have sent emails?' -> allow\n"
        "'how do I improve my open rate?' -> allow\n"
        "'should I delete the drafts?' -> allow\n"
        "'compare er5t6y7u89 and new1234' -> allow\n"
        "'what should I do about the others?' -> allow\n"
        "'and why?' -> allow\n"
        "'from total?' -> allow\n"
        "'which one is good?' -> allow\n"
        "'what is the capital of France?' -> reject\n"
        "'how much does OpenAI charge per token?' -> reject\n"
        "'write me a poem about my campaigns' -> reject\n"
        "'tell me a joke' -> reject\n"
    )

    def _is_out_of_scope(self, question: str,
                         campaign_names: Optional[List[str]] = None,
                         has_history: bool = False) -> bool:
        """True when the question isn't about this account's marketing.

        The prompt rules alone did not hold — the model answered 'what is the
        capital of France?' and wrote a poem on request. On any failure this
        returns False, so a real question is never blocked by a broken check.
        """
        if not question or not question.strip():
            return False

        # A question naming one of the user's own campaigns is always in scope,
        # whatever the classifier thinks. It wrongly rejected "compare
        # er5t6y7u89 and new1234" — blocking a real question is the worse error.
        low = question.lower()
        for name in (campaign_names or []):
            n = (name or '').strip().lower()
            if n and re.search(r'(?<![a-z0-9])%s(?![a-z0-9])' % re.escape(n), low):
                return False

        # Creative writing is out of scope even when it is about the campaigns,
        # so this is checked before the domain-term allowance below (a poem
        # request mentions "campaigns" too).
        if re.search(r'\b(write|compose|make up|create)\b[^.]{0,30}'
                     r'\b(poem|poetry|song|story|joke|rap|haiku|limerick)\b', low):
            return True

        # Any question mentioning a field we actually store is in scope. The
        # classifier read "what is their company size?" as being about outside
        # companies and blocked it, though company_size is a targeting field on
        # every campaign.
        domain_terms = (
            'campaign', 'campaigns', 'lead', 'leads', 'email', 'emails',
            'sent', 'open rate', 'click', 'reply', 'replies', 'bounce',
            'conversion', 'conversions', 'target', 'targeting', 'audience',
            'age range', 'company size', 'industry', 'industries', 'interests',
            'location', 'language', 'draft', 'drafts', 'paused', 'active',
            'performance', 'metrics', 'created', 'status',
        )
        if any(t in low for t in domain_terms):
            return False

        # Mid-conversation, a short question with a back-reference is a
        # follow-up about the data just discussed — "mention its deal" was
        # blocked because it names no field of its own. The subject comes from
        # the previous turn, so it cannot be judged in isolation.
        if has_history:
            words = set(re.findall(r"[a-z']+", low))
            refs = {'it', 'its', "it's", 'that', 'this', 'those', 'these',
                    'them', 'they', 'their', 'same', 'above', 'previous',
                    'others', 'other', 'rest'}
            if len(low.split()) <= 12 and (words & refs):
                return False
        try:
            out = self._call_llm_for_reasoning(
                'Question: "%s"' % question.strip()[:300],
                self.OUT_OF_SCOPE_SYSTEM, temperature=0.0, max_tokens=5,
            )
        except Exception as e:
            self.log_action("Scope check failed", {"error": str(e)})
            return False
        return bool(out) and 'reject' in out.strip().lower()

    # Question wording -> the campaign field it refers to.
    # ══════════════════════════════════════════════════════════
    #  QUERY PLANNER
    #  The model turns a question into a filter spec; Python executes it.
    #
    #  This replaced six hand-written filter helpers (age ranges, dates,
    #  numeric thresholds, booleans, ranking, industry/location text). Each
    #  handled the cases it was written for and silently dropped the rest, so
    #  every new field or combination was a new bug: "campaigns with positive
    #  replies AND clicks" ignored the clicks entirely because no helper knew
    #  that field. A spec covers every field and operator at once.
    # ══════════════════════════════════════════════════════════

    # Fields the planner may filter or sort on, and how to read each one.
    #   kind: 'num'   -> numeric compare
    #         'text'  -> case-insensitive substring
    #         'range' -> "25-45" style, compared by overlap
    #         'date'  -> ISO date string, compared lexically
    PLANNABLE_FIELDS = {
        'name':               ('text',  'name'),
        'status':             ('text',  'status'),
        'industry':           ('text',  'industry'),
        'location':           ('text',  'location'),
        'language':           ('text',  'language'),
        'company_size':       ('text',  'company_size'),
        'interests':          ('text',  'interests'),
        'age_range':          ('range', 'age_range'),
        'created_at':         ('date',  'created_at'),
        'start_date':         ('date',  'start_date'),
        'end_date':           ('date',  'end_date'),
        'emails_sent':        ('num',   'emails_sent'),
        'emails_opened':      ('num',   'emails_opened'),
        'emails_clicked':     ('num',   'emails_clicked'),
        'emails_replied':     ('num',   'emails_replied'),
        'emails_bounced':     ('num',   'emails_bounced'),
        'positive_replies':   ('num',   'positive_replies'),
        'negative_replies':   ('num',   'negative_replies'),
        'leads_count':        ('num',   'leads_count'),
        'target_leads':       ('num',   'target_leads'),
        'target_conversions': ('num',   'target_conversions'),
        'open_rate':          ('num',   'open_rate'),
        'click_rate':         ('num',   'click_rate'),
        'reply_rate':         ('num',   'reply_rate'),
        'bounce_rate':        ('num',   'bounce_rate'),
        'conversion_progress': ('num',  'conversion_progress'),
        # Derived: end_date - start_date. Without it "campaigns running more
        # than a week" had no way to be expressed, so the model guessed and
        # returned a 7-day campaign as "more than a week".
        'duration_days':      ('num',   '_duration_days'),
    }

    PLANNER_SYSTEM = (
        "You translate a question about marketing campaigns into a JSON filter "
        "spec. Reply with ONLY the JSON object, no prose, no code fences.\n\n"
        "Shape:\n"
        '{"filters": [{"field": "...", "op": "...", "value": ...}], '
        '"sort": {"field": "...", "desc": true}, "limit": null}\n\n'
        "Fields you may use:\n"
        "  text  : name, status (draft|paused|active), industry, location, "
        "language, company_size, interests\n"
        "  range : age_range        (use op 'overlaps' with [low, high])\n"
        "  date  : created_at, start_date, end_date  (values 'YYYY-MM-DD')\n"
        "  number: emails_sent, emails_opened, emails_clicked, emails_replied, "
        "emails_bounced, positive_replies, negative_replies, leads_count, "
        "target_leads, target_conversions, open_rate, click_rate, reply_rate, "
        "bounce_rate, conversion_progress, duration_days\n\n"
        "duration_days is end_date minus start_date, already computed. Use it "
        "for 'runs for more than a week' (> 7), 'longer than a month' (> 30), "
        "'short campaigns', and similar. A week is 7 days, a month is 30.\n"
        "IMPORTANT: start_date/end_date are the PLANNED schedule. A draft "
        "campaign has never launched, so it is not actually running. When the "
        "question is about campaigns that RUN or ARE RUNNING (present tense), "
        "add {\"field\":\"emails_sent\",\"op\":\">\",\"value\":0} so only "
        "campaigns that actually went out are returned. If the question is "
        "about how long they are SCHEDULED for, do not add it.\n\n"
        "Operators: =, !=, >, >=, <, <=, contains, overlaps\n\n"
        "Rules:\n"
        "- EVERY condition in the question must appear as a filter. 'paused "
        "campaigns with positive replies and clicks' is THREE filters.\n"
        "- 'has X' / 'with X' means X > 0. 'no X' / 'zero X' means X = 0.\n"
        "- 'never sent' is emails_sent = 0; 'have sent' is emails_sent > 0.\n"
        "- 'clicks' is emails_clicked; 'opens' is emails_opened.\n"
        "- Industry/location: use 'contains' with the shortest distinctive "
        "word ('tech', 'commerce', 'united states') so spelling variants match.\n"
        "- Read through typos: 'ecomerce'->commerce, 'postive'->positive.\n"
        "- best/worst PERFORMING ranks by positive_replies AND requires "
        "emails_sent > 0 (a campaign that never ran has no performance). Use "
        "sort + limit 1.\n"
        "- If the question asks for no filtering at all, return "
        '{"filters": [], "sort": null, "limit": null}.\n'
        "- If the question names a SPECIFIC campaign, filter on its name: "
        '{"field":"name","op":"contains","value":"<the name>"}.\n'
        "- If the question asks about something NOT in the field list above — "
        "ROI, budget, spend, cost, revenue, profit, CTR benchmarks — return "
        '{"filters": [], "sort": null, "limit": null, "unavailable": "<field>"}. '
        "Never substitute a different field for one you do not have: 'highest "
        "ROI' is NOT 'most positive replies'.\n"
        "- 'unavailable' is ONLY for the four money concepts above (ROI, "
        "budget/spend/cost, revenue/profit, external benchmarks). If the word "
        "appears anywhere in the field list — language, location, industry, "
        "interests, company_size, age_range, any rate or count — it EXISTS and "
        "'unavailable' is wrong. Asking 'what are the languages of these "
        "campaigns' is a question about a field you have.\n"
        "- Individual LEADS and their REPLIES are also available (name, email, "
        "company, job title, status; reply text, reply subject, reply date, and "
        "interest level: positive, negative, neutral, requested_info, "
        "objection, unsubscribe, not_analyzed). Sent emails carry their subject "
        "lines too. A question like 'who are meow's leads', 'what did they "
        "reply', 'what reply types did we get' or 'what subjects were sent' is "
        "answerable — that detail is supplied automatically. Never call leads, "
        "replies, reply types or subjects unavailable.\n"
        "- Only use 'unavailable' when the DATA is missing, not when the "
        "phrasing is unusual. 'campaigns targeting multiple countries' is a "
        "question about the location field, which you DO have — use "
        '{"field":"location","op":"contains","value":","} because a location '
        "listing several countries is comma-separated. The same trick works "
        "for multiple industries or languages.\n\n"
        "Examples:\n"
        "Q: which paused campaigns have positive replies but no clicks?\n"
        'A: {"filters": [{"field":"status","op":"=","value":"paused"},'
        '{"field":"positive_replies","op":">","value":0},'
        '{"field":"emails_clicked","op":"=","value":0}], "sort":null, "limit":null}\n'
        "Q: ecomerce campaigns with more than 100 conversion target\n"
        'A: {"filters": [{"field":"industry","op":"contains","value":"commerce"},'
        '{"field":"target_conversions","op":">","value":100}], "sort":null, "limit":null}\n'
        "Q: which campaigns target ages 10 to 20?\n"
        'A: {"filters": [{"field":"age_range","op":"overlaps","value":[10,20]}], '
        '"sort":null, "limit":null}\n'
        "Q: campaigns created before August 2026\n"
        'A: {"filters": [{"field":"created_at","op":"<","value":"2026-08-01"}], '
        '"sort":null, "limit":null}\n'
        "Q: which campaign performs worst?\n"
        'A: {"filters": [{"field":"emails_sent","op":">","value":0}], '
        '"sort":{"field":"positive_replies","desc":false}, "limit":1}\n'
        "Q: tell me about er5t6y7u89\n"
        'A: {"filters": [{"field":"name","op":"contains","value":"er5t6y7u89"}], '
        '"sort":null, "limit":null}\n'
        "Q: which campaign has the highest ROI?\n"
        'A: {"filters": [], "sort":null, "limit":null, "unavailable":"ROI"}\n'
        "Q: what is the budget of cmp1?\n"
        'A: {"filters": [], "sort":null, "limit":null, "unavailable":"budget"}\n'
    )

    def _plan_query(self, question: str) -> Optional[Dict]:
        """Ask the model for a filter spec. None when it can't produce one."""
        if not question or not question.strip():
            return None
        # The model has no idea what year it is and defaulted to its training
        # data: "before September" planned a cutoff of 2023-09-01 against 2026
        # campaigns, so nothing matched. State today's date every time.
        today = datetime.now()
        dated_system = self.PLANNER_SYSTEM + (
            "\nTODAY IS %s (%s). Any month named without a year means that "
            "month in %d — 'before September' is '%d-09-01'. 'last month' is "
            "%s, 'this month' is %s. Never use a year from memory.\n"
            % (today.strftime('%Y-%m-%d'), today.strftime('%A'),
               today.year, today.year,
               (today.replace(day=1) - timedelta(days=1)).strftime('%Y-%m'),
               today.strftime('%Y-%m'))
        )
        try:
            raw = self._call_llm_for_reasoning(
                'Q: %s\nA:' % question.strip()[:400],
                dated_system, temperature=0.0, max_tokens=300,
            )
        except Exception as e:
            self.log_action("Query planning failed", {"error": str(e)})
            return None
        if not raw:
            return None
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return None
        try:
            plan = json.loads(m.group(0))
        except (ValueError, TypeError):
            return None
        return plan if isinstance(plan, dict) else None

    @staticmethod
    def _duration_days(campaign: Dict) -> Optional[int]:
        """end_date - start_date in days, or None when either is missing."""
        a = str(campaign.get('start_date') or '')[:10]
        b = str(campaign.get('end_date') or '')[:10]
        if len(a) != 10 or len(b) != 10:
            return None
        try:
            d1 = datetime.strptime(a, '%Y-%m-%d')
            d2 = datetime.strptime(b, '%Y-%m-%d')
        except ValueError:
            return None
        return (d2 - d1).days

    @staticmethod
    def _parse_range(raw) -> Optional[tuple]:
        s = str(raw or '').strip()
        m = re.match(r'^(\d+)\s*[-–]\s*(\d+)$', s)
        if m:
            return int(m.group(1)), int(m.group(2))
        if re.match(r'^\d+$', s):
            return int(s), int(s)
        return None

    def _apply_filter(self, campaign: Dict, flt: Dict) -> Optional[bool]:
        """Evaluate one condition. None when it cannot be evaluated."""
        field = str(flt.get('field') or '')
        spec = self.PLANNABLE_FIELDS.get(field)
        if not spec:
            return None
        kind, key = spec
        op = str(flt.get('op') or '=').strip()
        want = flt.get('value')
        if key == '_duration_days':
            have = self._duration_days(campaign)
        else:
            have = campaign.get(key)

        if kind == 'range':
            bounds = self._parse_range(have)
            if bounds is None:
                return False          # no age set is not a match
            if op == 'overlaps' and isinstance(want, (list, tuple)) and len(want) == 2:
                try:
                    lo, hi = float(want[0]), float(want[1])
                except (TypeError, ValueError):
                    return None
                return bounds[0] <= hi and bounds[1] >= lo
            return None

        if kind == 'num':
            if have is None:
                return False          # no data is not a match either way
            try:
                a, b = float(have), float(want)
            except (TypeError, ValueError):
                return None
            return {'>': a > b, '>=': a >= b, '<': a < b, '<=': a <= b,
                    '=': a == b, '==': a == b, '!=': a != b}.get(op)

        # text and date are both string compares; dates are ISO so this is safe.
        a = str(have or '').strip().lower()
        # company_size is stored as text ("11-50"), so the planner sometimes
        # sends it as a range. Treat that as the literal bucket it names.
        if isinstance(want, (list, tuple)) and len(want) == 2:
            b = '%s-%s' % (want[0], want[1])
            if op == 'overlaps':
                op = 'contains'
        else:
            b = str(want or '').strip().lower()
        b = b.strip().lower()
        if kind == 'date':
            a = a[:10]
            b = b[:10]
            if not a:
                return False
        if op in ('contains', 'includes', 'has'):
            return b in a
        if op == '!=':
            return b not in a if kind == 'text' else a != b
        if op in ('=', '=='):
            return (b in a) if kind == 'text' else a == b
        if kind == 'date':
            return {'>': a > b, '>=': a >= b, '<': a < b, '<=': a <= b}.get(op)
        return None

    def _complement_answer(self, previous_question: str,
                           marketing_data: Dict) -> Optional[str]:
        """The campaigns the PREVIOUS filter did not match.

        "17 of 18 target adults" followed by "which one is left?" is asking for
        the 18th. Re-running the previous plan and inverting it is exact; asked
        to work it out itself the model listed sixteen unrelated campaigns.
        """
        campaigns = (marketing_data or {}).get('campaigns') or []
        if not campaigns:
            return None
        plan = self._plan_query(previous_question)
        if not plan:
            return None
        filters = plan.get('filters')
        if not isinstance(filters, list) or not filters:
            return None

        missed = []
        for c in campaigns:
            verdicts = [self._apply_filter(c, f) for f in filters
                        if isinstance(f, dict)]
            if any(v is None for v in verdicts) or not verdicts:
                return None          # can't trust a partial evaluation
            if not all(verdicts):
                missed.append(c)

        described = " AND ".join(
            "%s %s %s" % (f.get('field'), f.get('op'), f.get('value'))
            for f in filters if isinstance(f, dict))
        if not missed:
            return (
                "ANSWER FOR THIS QUESTION (already computed):\n"
                "Every campaign matched the previous filter, so none is left "
                "over. Say that plainly.\n"
            )

        shown = []
        for f in filters:
            fld = f.get('field')
            if fld in self.PLANNABLE_FIELDS and fld not in shown:
                shown.append(fld)
        rows = []
        for c in missed:
            bits = ", ".join(
                "%s: %s" % (f.replace('_', ' '),
                            c.get(self.PLANNABLE_FIELDS[f][1])
                            if c.get(self.PLANNABLE_FIELDS[f][1]) is not None
                            else 'not set')
                for f in shown)
            rows.append("  - %s (%s)%s" % (c.get('name', 'Unnamed'),
                                           c.get('status', 'N/A'),
                                           (" - " + bits) if bits else ""))
        return (
            "ANSWER FOR THIS QUESTION (already computed):\n"
            "The previous question filtered on: %s\n"
            "%d of %d campaigns did NOT match — these are the ones left over:\n"
            "%s\n"
            "List exactly these. Explain briefly why each fell outside (usually "
            "the field is not set). Do not list the campaigns that DID match.\n"
            % (described, len(missed), len(campaigns), "\n".join(rows))
        )

    def _run_query_plan(self, question: str, marketing_data: Dict) -> Optional[str]:
        """Execute a planned filter and return the finished answer as context.

        The model plans; Python filters. That split is the point: the model is
        good at reading intent out of a typo-ridden sentence and bad at
        comparing numbers across 18 rows, and this asks each to do only what it
        is good at.
        """
        campaigns = (marketing_data or {}).get('campaigns') or []
        if not campaigns:
            return None

        plan = self._plan_query(question)
        if not plan:
            return None

        # The question asks for a field we do not store (ROI, budget, spend).
        # Say so — the model otherwise substitutes a field it does have and
        # presents the wrong metric as the answer.
        unavailable = plan.get('unavailable')
        # Only four things are genuinely missing. Checking against the field
        # list alone was not enough — 'language' and then 'reply types' were
        # both declared unavailable while the data existed, telling the user
        # their own records weren't there. Allow the refusal only for money
        # concepts we truly do not store.
        if unavailable:
            u = str(unavailable).strip().lower()
            truly_missing = (
                'roi', 'return on investment', 'budget', 'spend', 'spent',
                'cost', 'costs', 'revenue', 'profit', 'margin', 'cpc', 'cpl',
                'cpa', 'benchmark', 'benchmarks', 'industry average',
            )
            if not any(m in u for m in truly_missing):
                self.log_action("Ignored bogus 'unavailable'", {"field": u})
                unavailable = None
        if unavailable:
            return (
                "ANSWER FOR THIS QUESTION (already computed — use it verbatim):\n"
                "This account does not track %s. There is no such field on a "
                "campaign, so the question cannot be answered from the data.\n"
                "Say that plainly. Do NOT answer with a different metric "
                "instead, and do not estimate it.\n" % unavailable
            )

        filters = plan.get('filters')
        if not isinstance(filters, list) or not filters:
            return None            # nothing to pre-compute

        matched, described = [], []
        for c in campaigns:
            verdicts = [self._apply_filter(c, f) for f in filters
                        if isinstance(f, dict)]
            if any(v is None for v in verdicts) or not verdicts:
                # An unusable filter means we cannot trust the result; leave the
                # question to the model rather than answering it wrongly.
                return None
            if all(verdicts):
                matched.append(c)

        for f in filters:
            described.append("%s %s %s" % (f.get('field'), f.get('op'),
                                           f.get('value')))
        label = " AND ".join(described)

        sort = plan.get('sort') or None
        if isinstance(sort, dict) and sort.get('field') in self.PLANNABLE_FIELDS:
            skey = self.PLANNABLE_FIELDS[sort['field']][1]
            matched.sort(key=lambda c: (c.get(skey) is None, c.get(skey) or 0),
                         reverse=bool(sort.get('desc')))
        limit = plan.get('limit')
        if isinstance(limit, int) and 0 < limit < len(matched):
            matched = matched[:limit]

        self.log_action("Query plan executed",
                        {"filters": label, "matched": len(matched)})

        if not matched:
            # Show how each condition fares on its own, so the explanation for
            # "none" is grounded instead of guessed ("they have sent nothing"
            # was offered for campaigns that had in fact sent emails).
            breakdown = []
            for f in filters:
                if not isinstance(f, dict):
                    continue
                n = sum(1 for c in campaigns
                        if self._apply_filter(c, f) is True)
                breakdown.append("  %s %s %s -> %d campaign(s)" % (
                    f.get('field'), f.get('op'), f.get('value'), n))
            return (
                "ANSWER FOR THIS QUESTION (already computed):\n"
                "NO campaign matches: %s\n"
                "\n--- INTERNAL, DO NOT REPRODUCE ---\n"
                "Per-condition counts, for working out the reason only:\n%s\n"
                "--- END INTERNAL ---\n"
                % (label, "\n".join(breakdown))
                +
                "Reply to the user in one or two plain sentences: say nothing "
                "matched, and give the reason in words (e.g. 'the campaigns "
                "that sent emails are all English'). Never print the counts "
                "above, the field names, or the operators — they are working "
                "notes, not part of the answer. Do not list other campaigns.\n"
            )

        # Show the fields that were filtered or sorted on, so each listed row
        # visibly satisfies the conditions.
        shown = []
        for f in filters:
            fld = f.get('field')
            if fld in self.PLANNABLE_FIELDS and fld not in shown:
                shown.append(fld)
        if isinstance(sort, dict) and sort.get('field') in self.PLANNABLE_FIELDS:
            if sort['field'] not in shown:
                shown.append(sort['field'])

        def _display(campaign, field):
            key = self.PLANNABLE_FIELDS[field][1]
            if key == '_duration_days':
                d = self._duration_days(campaign)
                return ('%d days (%s to %s)' % (d, campaign.get('start_date'),
                                                campaign.get('end_date'))
                        if d is not None else 'no dates set')
            v = campaign.get(key)
            return v if v is not None else 'not set'

        rows = []
        for c in matched:
            bits = ", ".join(
                "%s: %s" % (f.replace('_', ' '), _display(c, f)) for f in shown)
            rows.append("  - %s (%s) - %s" % (c.get('name', 'Unnamed'),
                                              c.get('status', 'N/A'), bits))

        # A duration answer that includes drafts reads as though those campaigns
        # are running. They are not — the dates are only a plan.
        caveat = ""
        if any(f.get('field') == 'duration_days' for f in filters):
            drafts = [c.get('name') for c in matched
                      if (c.get('emails_sent') or 0) == 0]
            if drafts:
                caveat = (
                    "NOTE: %s never sent an email, so %s scheduled for that "
                    "long, not actually running. Say so — do not describe a "
                    "draft as running.\n"
                    % (", ".join(drafts),
                       "it is" if len(drafts) == 1 else "they are")
                )

        return (
            "ANSWER FOR THIS QUESTION (already computed — do not recount and do "
            "not re-filter):\n"
            "%d of %d campaigns match. The matching campaigns are:\n%s\n%s"
            "List exactly these, all of them — do not add or drop any.\n"
            "Describe the condition in plain words, never as a raw filter: say "
            "'run longer than a week', not 'duration_days > 7'. Field names and "
            "operators are internal.\n"
            "Write each row as 'name (status) - label: value, label: value'. "
            "Never prefix a label with the word 'field' — 'location: Pakistan', "
            "not 'field: location: Pakistan'.\n"
            % (len(matched), len(campaigns), "\n".join(rows), caveat)
        )

    def _is_reformat_followup(self, question: str) -> bool:
        """True when the question continues the PREVIOUS result set.

        Covers both re-presentations ("just show their names") and requests for
        a different field about the same campaigns ("and how much did they
        achieve?"). Either way the previous filter still applies — answering
        the latter across all 18 campaigns was wrong.
        """
        q = (question or '').strip().lower().rstrip('?!.')
        # A follow-up is short. A long question states its own criteria.
        if not q or len(q.split()) > 10:
            return False
        # A question naming its own scope is a new query, not a follow-up.
        # ("their"/"those" excluded — "how many of them" is still a follow-up.)
        if re.search(r'\b(all|every|each)\s+campaigns?\b', q):
            return False
        if re.search(r'\bwhich\s+campaigns?\b', q):
            return False

        words = set(re.findall(r"[a-z']+", q))
        refs = {'their', 'them', 'they', 'those', 'these', 'that', 'it', 'its',
                'same', 'this'}
        trims = {'just', 'only', 'shorter', 'briefly', 'simply'}

        # A back-reference means "the set we were just discussing".
        if words & refs:
            return True
        # A bare trim with no subject ("just names") means the same.
        return bool(words & trims)

    def _previous_question(self, additional_context: Optional[Dict]) -> Optional[str]:
        """The most recent user question from the conversation history."""
        history = (additional_context or {}).get('conversation_history') or []
        for pair in reversed(history):
            q = (pair.get('question') or pair.get('q') or '').strip()
            if q:
                return q
        return None

    def _subject_of_conversation(self, conv_history: List[Dict],
                                 marketing_data: Dict,
                                 current_question: str = '') -> Optional[str]:
        """The campaign the conversation is currently about, or None.

        Only returns a name when the recent turns are focused on ONE campaign;
        a conversation ranging over several has no single subject to pin.
        """
        campaigns = (marketing_data or {}).get('campaigns') or []
        names = [(c.get('name') or '').strip() for c in campaigns]
        names = [n for n in names if n]
        if not names or not conv_history:
            return None

        # Only pin a subject when the NEW question actually refers back. After
        # "compare er5t6y7u89 and new1234", asking "how many campaigns were
        # created before August 2026?" is a fresh, self-contained question —
        # naming a subject made the model answer it about those two only.
        q_new = (current_question or '').strip().lower()
        if q_new:
            refs = ('it', 'its', "it's", 'that', 'this', 'those', 'these',
                    'them', 'they', 'their', 'same', 'above', 'previous')
            words = set(re.findall(r"[a-z']+", q_new))
            names_in_q = any(
                re.search(r'(?<![a-z0-9])%s(?![a-z0-9])' % re.escape(n.lower()), q_new)
                for n in names)
            if not (words & set(refs)) and not names_in_q:
                return None
            if names_in_q:
                # The question names campaigns itself — that wins over history.
                # One name is the subject; several is a comparison, so no pin.
                named = [n for n in names
                         if re.search(r'(?<![a-z0-9])%s(?![a-z0-9])' % re.escape(n.lower()), q_new)]
                return named[0] if len(named) == 1 else None

        def _found(text: str) -> List[str]:
            low = (text or '').lower()
            hits = []
            for n in names:
                if re.search(r'(?<![a-z0-9])%s(?![a-z0-9])' % re.escape(n.lower()), low):
                    hits.append(n)
            return hits

        # Walk backwards; the most recent turn that pins exactly one campaign
        # wins. A turn naming several is a comparison, not a single subject.
        for pair in reversed(conv_history[-4:]):
            hits = set(_found(pair.get('question') or pair.get('q') or ''))
            if len(hits) == 1:
                return hits.pop()
            if hits:
                return None      # comparison — no single subject
            hits = set(_found(pair.get('answer') or pair.get('a') or ''))
            if len(hits) == 1:
                return hits.pop()
        return None

    def _dedupe_person_rows(self, answer: str) -> str:
        """Drop repeated lead rows for the same email address.

        A lead who replied several times has several reply rows, and the model
        listed the person once per row — the same name and address twice under
        "which leads replied negatively". One person is one row.
        """
        if not answer or answer.count('@') < 2:
            return answer

        out, seen = [], set()
        for line in answer.split('\n'):
            emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', line)
            # Only collapse rows that are ABOUT one person, not prose that
            # happens to mention an address.
            if len(emails) == 1 and len(line.strip()) < 220:
                key = emails[0].lower()
                if key in seen:
                    continue
                seen.add(key)
            out.append(line)
        return '\n'.join(out)

    def _reply_types_table(self, question: str,
                           marketing_data: Dict) -> Optional[str]:
        """The finished per-lead reply-type answer, ready to be repeated.

        Told to copy the table from the context, the model kept omitting leads.
        Composing the final text here leaves nothing to trim.
        """
        campaigns = (marketing_data or {}).get('campaigns') or []
        if not campaigns:
            return None

        low = (question or '').lower()
        targets = [c for c in campaigns
                   if (c.get('name') or '').strip()
                   and re.search(r'(?<![a-z0-9])%s(?![a-z0-9])'
                                 % re.escape(c['name'].strip().lower()), low)]

        # The question may name a campaign that does not exist ("new123456").
        # Falling back to every campaign answered about the wrong data and gave
        # no clue whose replies these were — say the name is unknown instead.
        if not targets:
            named = re.findall(r'\b(?:of|for|from|in)\s+([A-Za-z0-9_-]{3,})\s*$',
                               (question or '').strip(), re.IGNORECASE)
            if named:
                typo = named[-1]
                # Offer the nearest existing names so the user can correct it.
                close = sorted(
                    ((SequenceMatcher(None, typo.lower(),
                                      (c.get('name') or '').lower()).ratio(),
                      c.get('name')) for c in campaigns if c.get('name')),
                    reverse=True)[:3]
                suggestions = [n for score, n in close if score >= 0.4]
                return (
                    "\nANSWER FOR THIS QUESTION (already computed — use it "
                    "verbatim, add nothing):\n"
                    "No match found for '%s'.%s\n"
                    "Reply with just that. Do NOT show reply data, lead rows or "
                    "metrics for any campaign.\n"
                    % (typo,
                       (" Closest names: " + ", ".join(suggestions) + ".")
                       if suggestions else "")
                )
            # No campaign named at all — cover every campaign that has replies,
            # each clearly labelled.
            targets = [c for c in campaigns if c.get('reply_tally')]
        if not targets:
            return None

        out = []
        for c in targets:
            tally = c.get('reply_tally') or {}
            emails = sorted({L.get('email') for L in (c.get('leads') or [])
                             if L.get('email')} | set(tally))
            if not emails:
                continue
            lines = []
            totals = {}
            for em in emails:
                kinds = tally.get(em) or {}
                for k, v in kinds.items():
                    totals[k] = totals.get(k, 0) + v
                lines.append("  - %s: %s" % (
                    em,
                    ", ".join("%s x%d" % (k, v) for k, v in
                              sorted(kinds.items(), key=lambda t: -t[1]))
                    if kinds else "no replies"))
            out.append(
                "%s (%s) — all %d lead(s):\n%s\nTotals: %s" % (
                    c.get('name'), c.get('status', 'N/A'), len(emails),
                    "\n".join(lines),
                    ", ".join("%s %d" % (k, v) for k, v in
                              sorted(totals.items(), key=lambda t: -t[1]))
                    or "no replies at all"))

        if not out:
            return None
        return (
            "\nANSWER FOR THIS QUESTION (already computed — reproduce it "
            "exactly, every line, adding nothing and dropping nothing):\n"
            + "\n\n".join(out) + "\n"
        )

    def _mentions(self, question: str, *keywords) -> bool:
        """Typo-tolerant keyword test.

        Exact patterns kept failing on ordinary misspellings — "replis" matched
        nothing, so the reply detail never reached the context and the answer
        came back without it.
        """
        q = (question or '').lower()
        tokens = re.findall(r"[a-z]+", q)
        for kw in keywords:
            if kw in q:
                return True
            if ' ' in kw:
                continue
            for t in tokens:
                if len(kw) >= 5 and abs(len(t) - len(kw)) <= 3 and \
                        SequenceMatcher(None, t, kw).ratio() >= 0.78:
                    return True
        return False

    def _strip_internal_lines(self, answer: str) -> str:
        """Remove working notes the model echoed from the context.

        The pre-computed hints carry per-condition counts and raw filter
        expressions for the model to reason with. Those are internal; when they
        reached the reply the user saw "language != English -> 3 campaign(s)"
        under their answer. Prompt rules alone did not reliably stop it.
        """
        if not answer:
            return answer

        drop_exact = (
            'each condition on its own', 'per-condition counts',
            'answer for this question', '--- internal', '--- end internal',
            'do not reproduce', 'already computed',
        )
        out = []
        for line in answer.split('\n'):
            low = line.strip().lower()
            if not low:
                out.append(line)
                continue
            if any(m in low for m in drop_exact):
                continue
            # "field op value -> N campaign(s)" — a raw breakdown row.
            if re.match(r'^[a-z_]+\s*(!=|>=|<=|>|<|=|contains|overlaps)\s*\S.*'
                        r'->\s*\d+\s*campaign', low):
                continue
            # A bare filter expression on its own line.
            if re.match(r'^[a-z_]{3,}\s*(!=|>=|<=|>|<|=)\s*[\w\'"%.-]+$', low):
                continue
            out.append(line)

        cleaned = '\n'.join(out)

        # "field: location: Pakistan" -> "location: Pakistan". The model picked
        # the word up from the plan and repeated it before every label.
        cleaned = re.sub(r'\bfield\s*:\s*(?=[a-z_ ]+\s*:)', '', cleaned,
                         flags=re.IGNORECASE)

        # Trailing filter expressions inside an otherwise fine sentence:
        # "2 of 18 campaigns match: duration_days > 7" -> drop from the colon.
        # Anchored on "match:" so a normal data row ("sent: 7, leads: 5")
        # is never touched.
        cleaned = re.sub(
            r'\bmatch(?:es|ing)?\s*:\s*[a-z_]{3,}\s*'
            r'(?:!=|>=|<=|>|<|=|contains|overlaps)[^\n]*',
            'match', cleaned)
        # Underscored field names are left alone here. Rewriting them turned
        # legitimate data rows ("sent: 7, positive_replies: 10") into different
        # text, and the prompt already asks for plain wording.

        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
        return cleaned or answer

    def _note_if_truncated(self, answer: str, marketing_data: Dict) -> str:
        """Append a note when a per-campaign listing was cut short.

        The model can run out of output tokens mid-listing. Without this the
        user just sees fewer campaigns than they asked for, with no clue that
        anything was dropped.
        """
        campaigns = (marketing_data or {}).get('campaigns') or []
        total = len(campaigns)
        if total < 4 or not answer:
            return answer

        # Repair a count that disagrees with the list under it. The model wrote
        # "6 campaigns have not sent emails" above 16 rows; the list was right
        # and the number was not, so correct the number rather than leaving the
        # reader to spot it.
        answer = self._fix_count_mismatch(answer, campaigns)

        # Truncation is only flagged when the text ends on a DANGLING LABEL —
        # a metric name with its separator and no value ("…opened: 4, open:").
        # Every looser test produced false positives on complete answers, and a
        # wrong "cut off" note is worse than missing a rare real truncation.
        stripped = answer.rstrip()
        last_line = stripped.split('\n')[-1].strip()
        if not last_line or len(last_line) < 15:
            return answer
        cut = re.search(
            r'\b(sent|leads|opened|open|click|clicked|reply|replied|'
            r'positive_replies|negative_replies|conversions|conversion|'
            r'age|created|status|target)\s*[:=]\s*$',
            last_line.lower())
        if not cut:
            return answer

        return stripped + (
            "\n\n_The reply was cut off before the end. Ask again for the "
            "remaining campaigns, or narrow the question._"
        )

    def _fix_count_mismatch(self, answer: str, campaigns: List[Dict]) -> str:
        """Correct an opening count that disagrees with the list beneath it.

        The model wrote "6 campaigns have not sent emails" and then listed 16.
        The list comes from the data and is reliable; the count is where it slips.
        """
        if not answer or not campaigns:
            return answer

        names = [(c.get('name') or '').strip() for c in campaigns]
        names = [n for n in names if n]

        lines = answer.split('\n')
        # Rows that name exactly one campaign — the listing itself.
        listed = 0
        for ln in lines:
            low = ln.lower()
            hits = [n for n in names
                    if re.search(r'(?<![a-z0-9])%s(?![a-z0-9])' % re.escape(n.lower()), low)]
            if len(hits) == 1 and re.search(
                    r'\b(sent|leads|open|click|reply|positive_replies|age|created)\s*[:=]', low):
                listed += 1
        if listed < 3:
            return answer

        # The opening line's leading number, if it has one.
        for i, ln in enumerate(lines[:3]):
            m = re.match(r'^\s*(\d+)\b', ln)
            if not m:
                continue
            stated = int(m.group(1))
            if stated == listed or stated > len(campaigns):
                return answer
            # "N of M" keeps its M; only the first number is wrong.
            lines[i] = re.sub(r'^(\s*)\d+\b', r'\g<1>%d' % listed, ln, count=1)
            self.log_action("Corrected count in answer",
                            {"stated": stated, "listed": listed})
            return '\n'.join(lines)
        return answer

    def _extract_insights(self, marketing_data: Dict, question: str) -> List[Dict]:
        insights = []
        stats     = marketing_data.get('stats', {})
        campaigns = marketing_data.get('campaigns', [])
        total  = stats.get('total_campaigns', 0)
        active = stats.get('active_campaigns', 0)
        if total > 0:
            pct = (active / total) * 100
            insights.append({
                'type': 'campaigns', 'title': 'Active Campaigns',
                'value': f"{active}/{total} campaigns active ({pct:.1f}%)",
                'status': 'good' if pct > 50 else 'warning',
            })
        if campaigns:
            has_data = [c for c in campaigns if c.get('emails_sent', 0) and c['emails_sent'] > 0]
            if has_data:
                insights.append({
                    'type': 'performance', 'title': 'Data Availability',
                    'value': f"{len(has_data)} campaigns have performance data",
                    'status': 'good',
                })
        return insights

    def _create_data_summary(self, marketing_data: Optional[Dict]) -> Dict:
        if not marketing_data:
            return {}
        return {
            'campaigns_count': len(marketing_data.get('campaigns', [])),
            'research_count':  len(marketing_data.get('research', [])),
            'has_performance_data': any(
                c.get('metrics') for c in marketing_data.get('campaigns', [])
            ),
            'stats': marketing_data.get('stats', {}),
        }

    # ══════════════════════════════════════════════════════════
    #  CAMPAIGN ANALYSIS (unchanged public API)
    # ══════════════════════════════════════════════════════════

    def analyze_campaign_performance(self, campaign_id: int, user_id: Optional[int] = None) -> Dict:
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if user_id and campaign.owner_id != user_id:
                return {'success': False, 'error': 'Access denied'}

            metrics = CampaignPerformance.objects.filter(campaign=campaign)
            total_impressions = metrics.filter(metric_name='impressions').aggregate(total=Sum('metric_value'))['total'] or 0
            total_clicks      = metrics.filter(metric_name='clicks').aggregate(total=Sum('metric_value'))['total'] or 0
            total_conversions = metrics.filter(metric_name='conversions').aggregate(total=Sum('metric_value'))['total'] or 0
            ctr              = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            conversion_rate  = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0

            analysis_prompt = (
                f"Analyze this campaign performance:\n"
                f"Campaign: {campaign.name}\nType: {campaign.campaign_type}\nStatus: {campaign.status}\n"
                f"Impressions: {total_impressions:,.0f}\nClicks: {total_clicks:,.0f}\n"
                f"Conversions: {total_conversions:,.0f}\nCTR: {ctr:.2f}%\nConversion Rate: {conversion_rate:.2f}%\n\n"
                "Provide: 1) Overall assessment  2) What's working  3) Areas to improve  4) Recommendations"
            )
            analysis = self._call_llm_for_reasoning(analysis_prompt, self.system_prompt, temperature=0.3)
            return {
                'success': True, 'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'metrics': {
                    'impressions': float(total_impressions), 'clicks': float(total_clicks),
                    'conversions': float(total_conversions), 'ctr': ctr,
                    'conversion_rate': conversion_rate,
                },
                'analysis': analysis,
            }
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            return {'success': False, 'error': str(e)}