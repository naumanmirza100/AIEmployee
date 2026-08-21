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

        # Everything else is a question about the data → let the LLM answer it
        # with the full dataset in context.
        marketing_data = self._get_marketing_data(user_id)
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
        full_context = self._build_context(marketing_data, context)
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
                'description': (getattr(campaign, 'description', '') or '')[:300],
                'target_leads': target_leads, 'target_conversions': target_conversions,
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

    def _build_context(self, marketing_data: Dict, additional_context: Optional[Dict] = None) -> str:
        parts = []

        parts.append(
            "PLATFORM CONTEXT: This is the **Marketing Agent** platform with tabs: "
            "Research, Q&A, Campaigns, Notifications, Outreach. "
            "To run a campaign: Campaigns tab → create → add leads → set emails → launch.\n\n"
        )

        conv_history = (additional_context or {}).get('conversation_history') or []
        if conv_history:
            parts.append("RECENT CONVERSATION (last campaign mentioned = current context):")
            for i, pair in enumerate(conv_history[-4:], 1):
                q = pair.get('question') or pair.get('q') or ''
                a = pair.get('answer') or pair.get('a') or ''
                if q or a:
                    parts.append(f"  Q{i}: {q}")
                    parts.append(f"  A{i}: {a[:500]}{'...' if len(a) > 500 else ''}")
            parts.append("")

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
                context += (
                    "- %s (%s): sent=%s, opened=%s, replied=%s, "
                    "positive_replies=%s, negative_replies=%s, "
                    "open=%s%%, click=%s%%, reply=%s%%, "
                    "leads=%s, conversions=%s/%s, conv_progress=%s%% "
                    "| TARGETING: %s\n" % (
                        c.get('name', 'Unnamed'), c.get('status', 'N/A'),
                        c.get('emails_sent', 0), c.get('emails_opened', 0),
                        c.get('emails_replied', 0),
                        c.get('positive_replies', 0), c.get('negative_replies', 0),
                        c.get('open_rate', 'N/A'), c.get('click_rate', 'N/A'),
                        c.get('reply_rate', 'N/A'),
                        c.get('leads_count', 'N/A'),
                        c.get('positive_replies', 0),
                        c.get('target_conversions') if c.get('target_conversions') is not None else 'N/A',
                        c.get('conversion_progress', 'N/A'),
                        targeting_str,
                    )
                )
            if len(campaigns) > 60:
                context += "  (...%d more not shown)\n" % (len(campaigns) - 60)

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
            "- If the question asks for campaigns matching a condition and NONE "
            "match, say so plainly: 'No campaigns match that.' Then say what the "
            "campaigns DO target. Do NOT fall back to listing every campaign as "
            "if it answered the question.\n"
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
            "- Read FIELD MEANINGS above before ranking anything. For questions "
            "about progress, conversions, or 'closing deals', rank by "
            "positive_replies. If EVERY campaign has positive_replies=0, the "
            "honest answer is 'None — no campaign has any positive replies yet', "
            "not the least-bad campaign. Never present a draft campaign that has "
            "sent 0 emails as the closest to converting.\n"
            "- When you name a winner, quote the number that makes it the winner. "
            "If that number is 0, say the result is 'no data yet' instead.\n"
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

        # Count how many campaign names actually made it into the answer.
        low = answer.lower()
        named = [c for c in campaigns
                 if (c.get('name') or '').strip()
                 and (c.get('name') or '').strip().lower() in low]
        shown = len(named)

        # Only a listing-style answer is worth checking: several names present
        # but not all of them.
        if shown < 3 or shown >= total:
            return answer

        # A filtered answer legitimately shows a subset ("2 of 18 campaigns
        # target tech"). Don't call that truncated — the model said up front
        # how many it was listing.
        if re.search(r'\b\d+\s+of\s+\d+\b', low) or 'no campaigns match' in low:
            return answer

        # A truncated listing ends mid-row; a finished one ends in punctuation.
        # If the last line looks like a complete sentence, trust it.
        last_line = answer.rstrip().split('\n')[-1].strip()
        if last_line.endswith(('.', '!', '?', ':')) and len(last_line) < 120:
            return answer

        missing = [c.get('name', 'Unnamed') for c in campaigns if c not in named]
        return answer.rstrip() + (
            "\n\n_Showing %d of %d campaigns — the reply hit its length limit. "
            "Still missing: %s. Ask about those by name for their details._"
            % (shown, total, ", ".join(missing[:12]) + ("..." if len(missing) > 12 else ""))
        )

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