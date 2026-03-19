"""
Marketing Knowledge Q&A + Analytics Agent
Foundation Agent - Provides data understanding and answers marketing questions

ROUTING ARCHITECTURE (Smart Enum Router):
  Every question goes through _classify_question() which returns ONE of these:
  
  DB-only (0 LLM tokens):
    - GREETING          → short friendly reply
    - PLATFORM_INFO     → static platform description
    - META_HELP         → "what can I ask?" reply
    - DB_COUNT_STATUS   → campaign count / active / list
    - DB_TOTAL_LEADS    → total leads number
    - DB_ANALYTICS      → open rate, click rate, top campaigns
    - DB_CAMPAIGN_DETAIL→ specific named campaign metrics
    - DB_BEST_CHANNEL   → channel recommendation (static logic)

  LLM-needed:
    - GENERAL_DEFINITION→ "what is X", full form, meaning (small LLM call, no data)
    - LLM_REASONING     → why, strategy, improve, optimize (full LLM + data)
"""

from .marketing_base_agent import MarketingBaseAgent
from .platform_content import get_platform_response
from typing import Dict, Optional, List
from marketing_agent.models import Campaign, CampaignPerformance, MarketResearch, EmailSendHistory, Reply, CampaignLead
import json
import re
from enum import Enum
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
            'how are', "how's it", 'hows it', 'how do you do',
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

        # ── 4. DB: total leads ────────────────────────────────
        cfg = ROUTER_CONFIG[QuestionCategory.DB_TOTAL_LEADS]
        if len(q) <= cfg["max_len"] and any(p in q for p in cfg["contains"]):
            return QuestionCategory.DB_TOTAL_LEADS

        # ── 5. DB: campaign count / status ────────────────────
        cfg = ROUTER_CONFIG[QuestionCategory.DB_COUNT_STATUS]
        if len(q) <= cfg["max_len"] and any(p in q for p in cfg["contains"]):
            return QuestionCategory.DB_COUNT_STATUS

        # ── 6. DB: specific campaign detail ───────────────────
        #    Check this BEFORE generic analytics so named campaigns win
        if campaigns:
            perf_terms = (
                'performance', 'open rate', 'click rate', 'reply rate', 'bounce',
                'conversion', 'leads', 'goal', 'target', 'positive', 'negative',
                'details', 'detail', 'about', 'achieved', 'achievement',
                'status', 'how is', 'how are', 'tell me about',
            )
            if any(t in q for t in perf_terms):
                matched = self._find_campaign_in_question(question, campaigns)
                if matched is not None:
                    return QuestionCategory.DB_CAMPAIGN_DETAIL

        # ── 7. General definition (strong signals) ─────────────
        #    Check BEFORE analytics so "what is meant by conversion rate"
        #    is treated as a definition, not a stats query
        cfg = ROUTER_CONFIG[QuestionCategory.GENERAL_DEFINITION]
        if len(q) <= cfg["max_len"]:
            if any(p in q for p in cfg.get("contains_strong", ())):
                return QuestionCategory.GENERAL_DEFINITION

        # ── 8. DB: analytics / performance summary ────────────
        cfg = ROUTER_CONFIG[QuestionCategory.DB_ANALYTICS]
        if len(q) <= cfg["max_len"]:
            has_exclude = any(x in q for x in cfg["exclude_if_contains"])
            if not has_exclude:
                # exact match (short vague follow-ups like "performance", "stats")
                if q in cfg.get("exact_also", set()):
                    return QuestionCategory.DB_ANALYTICS
                # phrase match
                if any(p in q for p in cfg["contains"]):
                    return QuestionCategory.DB_ANALYTICS

        # ── 9. DB: best channel ───────────────────────────────
        cfg = ROUTER_CONFIG[QuestionCategory.DB_BEST_CHANNEL]
        if len(q) <= cfg["max_len"]:
            has_trigger = any(x in q for x in cfg["requires_any"])
            has_channel = any(t in q for t in cfg["requires_channel"])
            has_phrase  = any(p in q for p in cfg["contains"])
            if (has_trigger and has_channel) or has_phrase:
                return QuestionCategory.DB_BEST_CHANNEL

        # ── 10. General definition (weak signals) ─────────────
        cfg = ROUTER_CONFIG[QuestionCategory.GENERAL_DEFINITION]
        if len(q) <= cfg["max_len"]:
            has_exclude = any(x in q for x in cfg["exclude_if_contains"])
            if not has_exclude:
                if any(p in q for p in cfg["contains"]):
                    return QuestionCategory.GENERAL_DEFINITION
                # "what is X" / "what does X" only when short and no data context
                if len(q) <= 50 and any(q.startswith(p) for p in cfg["startswith_short"]):
                    return QuestionCategory.GENERAL_DEFINITION

        # ── 10. Default: needs LLM reasoning ──────────────────
        return QuestionCategory.LLM_REASONING

    # ══════════════════════════════════════════════════════════
    #  MAIN ENTRY POINT
    # ══════════════════════════════════════════════════════════

    def process(self, question: str, context: Optional[Dict] = None, user_id: Optional[int] = None) -> Dict:
        """
        Main entry point — classifies question and routes to correct handler.
        """
        self.log_action("Processing marketing question", {"question": (question or '')[:100]})

        # Fix common typos first
        question = self._normalize_question_typos(question)

        # ── Fast-path: categories that need NO DB data ────────
        pre_db_category = self._classify_question(question, campaigns=None)

        if pre_db_category == QuestionCategory.GREETING:
            return self._handle_greeting(question)

        if pre_db_category == QuestionCategory.PLATFORM_INFO:
            return self._handle_platform_info(question)

        if pre_db_category == QuestionCategory.META_HELP:
            return self._handle_meta_help(question)

        if pre_db_category == QuestionCategory.DB_BEST_CHANNEL:
            return self._handle_best_channel(question)

        if pre_db_category == QuestionCategory.GENERAL_DEFINITION:
            return self._handle_general_definition(question)

        # ── DB required from here ─────────────────────────────
        marketing_data = self._get_marketing_data(user_id)
        campaigns = marketing_data.get('campaigns', []) or []

        # Re-classify with campaign list (needed for DB_CAMPAIGN_DETAIL)
        category = self._classify_question(question, campaigns=campaigns)

        if category == QuestionCategory.DB_TOTAL_LEADS:
            return self._handle_total_leads(marketing_data, question)

        if category == QuestionCategory.DB_COUNT_STATUS:
            return self._handle_count_status(marketing_data, question)

        if category == QuestionCategory.DB_CAMPAIGN_DETAIL:
            matched = self._find_campaign_in_question(question, campaigns)
            if matched:
                return self._handle_campaign_detail(matched, marketing_data, question)

        if category == QuestionCategory.DB_ANALYTICS:
            return self._handle_db_analytics(question, marketing_data)

        # ── LLM reasoning (last resort) ───────────────────────
        return self._handle_llm_reasoning(question, marketing_data, context)

    # ══════════════════════════════════════════════════════════
    #  HANDLERS — one per category
    # ══════════════════════════════════════════════════════════

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
        """Full LLM call — only reached when DB handlers cannot answer."""
        full_context = self._build_context(marketing_data, context)
        answer = self._generate_answer(question, full_context, context)
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
        if not question or not isinstance(question, str):
            return question
        q = question.strip()
        typos = [
            (r'\bcaomaphin\b', 'campaign'),  (r'\bcaompagin\b', 'campaign'),
            (r'\bcampagin\b',  'campaign'),  (r'\bcompagin\b',  'campaign'),
            (r'\bcamapgin\b',  'campaign'),  (r'\bcamapagin\b', 'campaign'),
            (r'\bcomapgin\b',  'campaign'),  (r'\bcampagins\b', 'campaigns'),
            (r'\bcaampaign\b', 'campaign'),  (r'\bcampain\b',   'campaign'),
            (r'\bcampagn\b',   'campaign'),
            (r'\bavergae\b',      'average'),       (r'\baverge\b',      'average'),
            (r'\bavreage\b',      'average'),       (r'\bavgerage\b',    'average'),
            (r'\bperformane\b',   'performance'),  (r'\bperformace\b',  'performance'),
            (r'\bperfomance\b',   'performance'),   (r'\bpreformance\b', 'performance'),
            (r'\banaltics\b',     'analytics'),     (r'\banalyitcs\b',   'analytics'),
            (r'\bleades\b',       'leads'),          (r'\bledes\b',       'leads'),
            (r'\bchanel\b',       'channel'),        (r'\bchanell\b',     'channel'),
            (r'\bplatfrom\b',     'platform'),       (r'\bplatfom\b',     'platform'),
            (r'\bqeustion\b',     'question'),       (r'\bqestion\b',     'question'),
            (r'\bemials\b',       'emails'),         (r'\bemails\b',      'emails'),
            (r'\bstaregy\b',      'strategy'),       (r'\bstratgey\b',    'strategy'),
        ]
        for pattern, replacement in typos:
            q = re.sub(pattern, replacement, q, flags=re.IGNORECASE)
        return q

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
            context += f"CAMPAIGNS (up to 5):\n"
            for c in campaigns[:5]:
                context += (
                    f"- {c.get('name','Unnamed')} ({c.get('status','N/A')}): "
                    f"sent={c.get('emails_sent',0)}, open={c.get('open_rate','N/A')}%, "
                    f"click={c.get('click_rate','N/A')}%, reply={c.get('reply_rate','N/A')}%, "
                    f"leads={c.get('leads_count','N/A')}, conv_progress={c.get('conversion_progress','N/A')}%\n"
                )

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
            "- Be direct and short (1–4 sentences unless details were asked).\n"
            "- No filler like 'based on...'.\n"
            "- If listing campaigns, include status after each name.\n"
        )
        try:
            return self._call_llm_for_reasoning(
                prompt, self.system_prompt, temperature=0.3, max_tokens=700
            )
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower():
                return "The service is busy. Please try again in a few seconds."
            return f"Error analyzing data: {err_str}"

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
            return {'success': False, 'error': str(e)}