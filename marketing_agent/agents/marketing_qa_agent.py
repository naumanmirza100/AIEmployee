"""
Marketing Knowledge Q&A + Analytics Agent
Foundation Agent - Provides data understanding and answers marketing questions
This is the BRAIN that all other agents will use.
"""

from .marketing_base_agent import MarketingBaseAgent
from .platform_content import get_platform_response
from typing import Dict, Optional, List
from marketing_agent.models import Campaign, CampaignPerformance, MarketResearch, EmailSendHistory, Reply, CampaignLead
import json
import re
from datetime import datetime, timedelta
from django.db.models import Sum, Avg, Count, Q


class MarketingQAAgent(MarketingBaseAgent):
    """
    Foundation Agent - Marketing Knowledge Q&A + Analytics
    
    This agent is the BRAIN of the marketing system:
    - Answers marketing and business questions using data
    - Analyzes campaign performance
    - Provides data-backed insights
    - Connects internal data with market insights
    - Serves as foundation for all other marketing agents
    
    Capabilities:
    - Answer questions like "Why are sales dropping?"
    - Analyze what's working and what's not
    - Compare campaign performance
    - Provide marketing intelligence
    - Data-driven recommendations
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Marketing Knowledge Q&A + Analytics Agent - the foundation brain of a marketing system.
        Your role is to:
        1. Answer marketing and business questions using data
        2. Analyze campaign performance and metrics
        3. Provide data-backed insights and recommendations
        4. Understand what's working and what's not working
        5. Connect internal company data with market insights
        
        You provide intelligent, data-driven answers to questions like:
        - "Why are sales dropping?"
        - "What campaigns are performing best?" (always name the best campaign(s) first with a short reason, then optionally list others)
        - "Which channels are most effective?"
        - "What should we focus on?"
        
        Always base your answers on the data provided. Be specific, actionable, and data-driven.
        When asked "which/what campaigns are performing best?", you must state clearly which campaign(s) are best and why (e.g. highest open rate, conversion progress)—do not only list all campaigns.
        When asked general questions like "best practices for our industry" or "industry best practices", give general best practices only—do not list campaign names, metrics, Key Trends, or "which campaign is this about".
        Do NOT put your reasoning in the answer (no "To answer your question...", "I will look at...", "The last Q&A..."). Give only the direct answer with numbers. Never repeat the same sentence or paragraph—state each fact once, then stop.

        CONVERSATION CONTEXT (apply this first, for every question):
        - **Override – "all campaigns" in current question:** If the user's current question says "all campaigns", "of all campaigns", "for all campaigns", "each campaign", "every campaign", or "all campagins", answer for **ALL** campaigns (list or aggregate for every campaign). Do NOT answer only for the last-discussed campaign.
        - **STEP 1 – Which campaign is being discussed?** Look at the **most recent (last) Q&A pair only**. The campaign in context is the one from the **last** user question or **last** answer. Example: if the last Q was "detail about campaign summer sales 26" and the last A was about summer sales 26, then the next question ("Are we on track?") is about **summer sales 26**, not summer sales 261 from earlier in the conversation. Do NOT use a campaign from an older Q&A when the most recent exchange was about a different campaign.
        - **If YES (a campaign in the last Q&A):** Answer in that campaign's context. For "it"/"its"/"this campaign"/"the campaign" (singular) answer **ONLY** that campaign—do NOT add other campaigns. For other questions (goals, opportunities, conversion rate, etc.) when the user did NOT say "all campaigns", answer **ONLY** for that campaign. Do NOT list or discuss summer sales 26, testing compagin, or any other campaign unless the user explicitly asked for "all campaigns".
        - **If NO (no campaign in the last Q&A):** Answer using ALL campaigns.
        - **Exceptions:** (1) "all campaigns" / "of all campaigns" in current question → answer for all. (2) "this platform" / "how to run a campaign" → use PLATFORM CONTEXT. (3) User names a campaign in current question → use that campaign.
        - When naming or listing campaigns, always include **status** after each name (e.g. summer sales 261 (paused), testing compagin (draft), summer sales 26 (paused)). **Conversion rate** = conversions/target_conversions. **Lead conversion rate** = leads_count/target_leads."""
    
    def _normalize_question_typos(self, question: str) -> str:
        """Fix common typos so platform/campaign detection and LLM understand the question."""
        if not question or not isinstance(question, str):
            return question
        q = question.strip()
        # Common typos for "campaign" (preserve rest of question)
        typos = [
            (r'\bcaomaphin\b', 'campaign'),
            (r'\bcaompagin\b', 'campaign'),
            (r'\bcampagin\b', 'campaign'),
            (r'\bcompagin\b', 'campaign'),
            (r'\bcomapgin\b', 'campaign'),
            (r'\bcampagins\b', 'campaigns'),
            (r'\bcaampaign\b', 'campaign'),
            (r'\bcampain\b', 'campaign'),
            (r'\bcampagn\b', 'campaign'),
        ]
        for pattern, replacement in typos:
            q = re.sub(pattern, replacement, q, flags=re.IGNORECASE)
        return q
    
    def _is_greeting_or_small_talk(self, question: str) -> bool:
        """Return True if the input is just a greeting or small talk, not a real question."""
        if not question or not isinstance(question, str):
            return True
        t = question.strip().lower().rstrip('?!.')
        if len(t) > 35:
            return False
        greetings = (
            'hi', 'hello', 'hey', 'hi there', 'hello there', 'hey there',
            'good morning', 'good afternoon', 'good evening', 'howdy',
            'yo', 'sup', 'what\'s up', 'greetings', 'hi!', 'hello!', 'hey!',
            'how are you', 'how are u', 'how r u', 'how r you', 'howre you',
            'how\'s it going', 'hows it going', 'how are you doing', 'how u doing',
            'whats up', 'what\'s going on', 'how do you do', 'how is it going',
            'how have you been', 'how\'s everything', 'hows everything',
        )
        if t in greetings:
            return True
        if t in ('thanks', 'thank you', 'ok', 'okay', 'bye', 'goodbye'):
            return True
        # Short acknowledgments / affirmations (not marketing questions)
        if t in ('good', 'great', 'nice', 'cool', 'alright', 'fine', 'good to know', 'got it', 'understood', 'perfect', 'sure', 'yeah', 'yep', 'nope', 'no'):
            return True
        if len(t) <= 30 and (t.startswith('how are') or t.startswith('how\'s it') or t.startswith('hows it') or t.startswith('how do you do')):
            return True
        return False

    def _is_platform_question(self, question: str) -> bool:
        """Return True if the user is asking about this platform/website/system—what it is, how to use it, how to run a campaign."""
        if not question or not isinstance(question, str):
            return False
        q = question.strip().lower()
        if len(q) > 120:
            return False
        platform_phrases = (
            'what is this platform', 'what does this platform', 'how helpful is this platform',
            'what is this website', 'what is this site', 'what is this app', 'what is this system',
            'how to use this platform', 'how to use this', 'how to run campaign', 'how to build campaign',
            'how to create campaign', 'how do i run a campaign', 'what are the agents', 'what agents',
            'tell me about this platform', 'explain this platform', 'describe this platform',
            # Questions about a specific agent (campaign agent, research agent, etc.) → platform, not your campaign list
            'campaign agent', 'campaigns agent', 'research agent', 'outreach agent', 'notification agent', 'notifications agent',
            'what is the campaign agent', 'which is campaign agent', 'what is campaign agent',
            # Broader: "this agent", "this platform" as subject; how it works
            'this agent', 'what is this agent', 'how does this agent', 'how this agent work',
            'how does this platform work', 'how this platform work', 'how does it work', 'how does this work',  # "it"/"this" = platform
            'how to run a campaign', 'run campaign on it', 'run a campaign on it', 'how to run campaign on it',
        )
        if any(p in q for p in platform_phrases):
            return True
        # Short questions that are clearly about the platform/agent
        if len(q) <= 25 and q in ('this platform', 'this agent', 'what is this', 'how does this work'):
            return True
        return False

    def _is_meta_question(self, question: str) -> bool:
        """Return True if the user is asking what they can ask / how the agent helps (not a data question)."""
        if not question or not isinstance(question, str):
            return False
        q = question.strip().lower()
        if len(q) > 80:
            return False
        meta_phrases = (
            'what question', 'what questions', 'what can i ask', 'what can you answer',
            'how can you help', 'how can i use', 'what do you do', 'what do you know',
            'what can you tell', 'what can you do', 'how does this work', 'what should i ask',
            'give me examples', 'example questions', 'what to ask', 'help me ask',
        )
        return any(p in q for p in meta_phrases)

    def _is_definition_or_general_question(self, question: str) -> bool:
        """Return True if the question is about meaning/full form/definition (general knowledge, not marketing data)."""
        if not question or not isinstance(question, str):
            return False
        q = question.strip().lower()
        if len(q) > 100:
            return False
        # Do NOT treat as definition when user is asking about OUR data / metrics / campaign
        if any(x in q for x in (
            'our ', 'my ', 'this campaign', 'the campaign', 'the active',
            'lead conversion', 'conversion rate', 'our lead', 'campaign',
        )):
            return False
        definition_phrases = (
            'full form of', 'full form', 'what is the full form', 'fullform of',
            'what does ', 'what is ', 'meaning of', 'what do you mean by',
            'define ', 'definition of', 'abbreviation of', 'stand for',
        )
        return any(p in q for p in definition_phrases)

    def _is_campaign_count_or_status_question(self, question: str) -> bool:
        """Return True if the question is asking how many campaigns, how many working/active, or list/status of campaigns."""
        if not question or not isinstance(question, str):
            return False
        q = question.strip().lower()
        if len(q) > 120:
            return False
        count_status_phrases = (
            'how many campaign', 'how many campaigns', 'how many are working', 'how many campaign are working',
            'campaigns are working', 'campaigns working', 'how many are active', 'how many active',
            'number of campaign', 'number of campaigns', 'total campaign', 'total campaigns',
            'list my campaign', 'list campaign', 'list my campaigns', 'list campaigns',
            'how many campaign do', 'how many campaigns do', 'campaign count', 'campaigns count',
        )
        return any(p in q for p in count_status_phrases)

    def _answer_campaign_count_or_status(self, marketing_data: Dict) -> Optional[Dict]:
        """Answer campaign count/status directly from data. Returns None if not applicable."""
        stats = marketing_data.get('stats', {})
        campaigns = marketing_data.get('campaigns', [])
        total = stats.get('total_campaigns', len(campaigns))
        active = stats.get('active_campaigns', 0)
        active_list = [c for c in campaigns if (c.get('status') or '').lower() == 'active']
        if len(active_list) != active and campaigns:
            active = len(active_list)
        # Build a short, direct answer
        if total == 0:
            answer = "You have **0** campaigns. Create a campaign to get started."
        else:
            answer = f"You have **{total}** campaign(s) in total. **{active}** are currently active (working)."
            if campaigns and len(campaigns) <= 15:
                all_names = ", ".join(c.get('name', 'Unnamed') for c in campaigns)
                answer += f" Campaign names: {all_names}."
            elif active_list and len(active_list) <= 10:
                names = ", ".join(c.get('name', 'Unnamed') for c in active_list)
                answer += f" Active: {names}."
        insights = []
        if total > 0:
            insights.append({
                'type': 'campaigns',
                'title': 'Active campaigns',
                'value': f"{active} of {total} active",
                'status': 'good' if active > 0 else 'warning'
            })
        return {'answer': answer, 'insights': insights}

    def _generate_general_answer(self, question: str) -> str:
        """Answer a definition/general-knowledge question with AI, without using marketing data."""
        prompt = f"""The user asked: "{question}"

Give a brief, direct answer only (definition, full form, or general knowledge). Do NOT mention marketing data, campaigns, or market trends. Keep it to the point: 1–4 sentences. If you don't know, say so briefly."""
        try:
            return self._call_llm_for_reasoning(
                prompt,
                "You answer general knowledge and definition questions briefly and to the point.",
                temperature=0.2,
                max_tokens=500,
            )
        except Exception as e:
            self.log_action("Error generating general answer", {"error": str(e)})
            return "I couldn't answer that. For definitions or full forms, try a search engine."

    def process(self, question: str, context: Optional[Dict] = None, user_id: Optional[int] = None) -> Dict:
        """
        Main entry point - answers marketing questions with data
        
        Args:
            question (str): Marketing/business question
            context (Dict): Optional context (campaigns, performance data, etc.)
            user_id (int): User ID for filtering user's data
            
        Returns:
            Dict: Answer with insights and data
        """
        self.log_action("Processing marketing question", {"question": question[:100]})
        
        # Normalize typos so "caomaphin"/"campagin" -> "campaign" for routing and LLM
        question = self._normalize_question_typos(question)
        
        # Greetings and small talk: short reply, no data or insights
        if self._is_greeting_or_small_talk(question):
            q_lower = (question or '').strip().lower()
            if any(x in q_lower for x in ('how are', 'how r u', 'how\'s it', 'hows it', 'how do you do')):
                answer = "I'm doing well, thanks for asking! How can I help you with your marketing today?"
            elif q_lower in ('good', 'great', 'nice', 'cool', 'alright', 'fine', 'good to know', 'got it', 'understood', 'perfect', 'sure', 'yeah', 'yep'):
                answer = "Got it. What would you like to ask about your marketing?"
            else:
                answer = 'Hi! How can I help you with your marketing today? Ask me about campaigns, performance, or insights.'
            return {
                'success': True,
                'answer': answer,
                'insights': [],
                'data_summary': {},
                'question': question
            }

        # Platform/website/system questions: full Marketing Agent overview or single-agent detail
        if self._is_platform_question(question):
            answer = get_platform_response(question)
            return {
                'success': True,
                'answer': answer,
                'insights': [],
                'data_summary': {},
                'question': question
            }

        # Meta/support questions ("what can I ask", "how can you help"): short answer only
        if self._is_meta_question(question):
            answer = (
                "You can ask me about your **campaigns** (how many, status, list), **performance** (clicks, conversions, ROI), "
                "**leads**, and **marketing insights**. Examples: \"How many campaigns?\", \"What's performing best?\", \"List my campaigns.\" "
                "Ask for details or recommendations only when you want a longer analysis."
            )
            return {
                'success': True,
                'answer': answer,
                'insights': [],
                'data_summary': {},
                'question': question
            }

        # Definition/general knowledge (full form of, what is X, meaning of): answer from AI only, no marketing data
        if self._is_definition_or_general_question(question):
            answer = self._generate_general_answer(question)
            return {
                'success': True,
                'answer': answer,
                'insights': [],
                'data_summary': {},
                'question': question
            }
        
        # Get marketing data from database
        marketing_data = self._get_marketing_data(user_id)
        
        # Direct answer for "how many campaigns" / "campaigns working" / "active campaigns" – use data only, no LLM
        if self._is_campaign_count_or_status_question(question):
            direct = self._answer_campaign_count_or_status(marketing_data)
            if direct is not None:
                return {
                    'success': True,
                    'answer': direct['answer'],
                    'insights': direct.get('insights', []),
                    'data_summary': self._create_data_summary(marketing_data),
                    'question': question
                }
        
        # Build comprehensive context (includes conversation history if provided)
        full_context = self._build_context(marketing_data, context)
        
        # Generate answer using AI
        answer = self._generate_answer(question, full_context, context)
        
        # Extract insights
        insights = self._extract_insights(marketing_data, question)
        
        return {
            'success': True,
            'answer': answer,
            'insights': insights,
            'data_summary': self._create_data_summary(marketing_data),
            'question': question
        }
    
    def _get_marketing_data(self, user_id: Optional[int] = None) -> Dict:
        """Get all marketing data from database"""
        campaigns_query = Campaign.objects.all()
        if user_id:
            campaigns_query = campaigns_query.filter(owner_id=user_id)
        
        campaigns = list(campaigns_query.select_related('owner').prefetch_related('performance_metrics'))
        campaign_ids = [c.id for c in campaigns]

        # Bulk aggregates to avoid N+1 queries (one query per aggregate type)
        email_stats = {}
        if campaign_ids:
            sent_statuses = ['sent', 'delivered', 'opened', 'clicked']
            for row in EmailSendHistory.objects.filter(campaign_id__in=campaign_ids).values('campaign_id').annotate(
                total_sent=Count('id', filter=Q(status__in=sent_statuses)),
                total_opened=Count('id', filter=Q(status__in=['opened', 'clicked'])),
                total_clicked=Count('id', filter=Q(status='clicked')),
                total_bounced=Count('id', filter=Q(status='bounced')),
                total_failed=Count('id', filter=Q(status='failed')),
            ).order_by('campaign_id'):
                email_stats[row['campaign_id']] = row

        reply_stats = {}
        if campaign_ids:
            for row in Reply.objects.filter(campaign_id__in=campaign_ids).values('campaign_id').annotate(
                total_replied=Count('id'),
                positive_replies=Count('id', filter=Q(interest_level__in=['positive', 'neutral', 'requested_info', 'objection'])),
                negative_replies=Count('id', filter=Q(interest_level__in=['negative', 'unsubscribe'])),
            ).order_by('campaign_id'):
                reply_stats[row['campaign_id']] = row

        lead_counts = {}
        if campaign_ids:
            for row in CampaignLead.objects.filter(campaign_id__in=campaign_ids).values('campaign_id').annotate(count=Count('id')).order_by('campaign_id'):
                lead_counts[row['campaign_id']] = row['count']

        # Build campaign data using prefetched metrics and bulk lookups
        campaigns_data = []
        for campaign in campaigns:
            cid = campaign.id
            es = email_stats.get(cid, {})
            rs = reply_stats.get(cid, {})
            total_sent = es.get('total_sent') or 0
            total_opened = es.get('total_opened') or 0
            total_clicked = es.get('total_clicked') or 0
            total_bounced = es.get('total_bounced') or 0
            total_failed = es.get('total_failed') or 0
            total_replied = rs.get('total_replied') or 0
            positive_replies = rs.get('positive_replies') or 0
            negative_replies = rs.get('negative_replies') or 0
            leads_count = lead_counts.get(cid, 0)

            target_leads = getattr(campaign, 'target_leads', None)
            target_conversions = getattr(campaign, 'target_conversions', None)
            conversion_progress = round((positive_replies / target_conversions * 100), 1) if target_conversions and target_conversions > 0 else None
            leads_progress = round((leads_count / target_leads * 100), 1) if target_leads and target_leads > 0 else None
            open_rate = round((total_opened / total_sent) * 100, 2) if total_sent > 0 else None
            click_rate = round((total_clicked / total_sent) * 100, 2) if total_sent > 0 else None
            reply_rate = round((total_replied / total_sent) * 100, 2) if total_sent > 0 else None
            bounce_rate = round((total_bounced / total_sent) * 100, 2) if total_sent > 0 else None

            metrics_prefetched = list(campaign.performance_metrics.all())[:20]
            camp_dict = {
                'id': campaign.id,
                'name': campaign.name,
                'type': campaign.campaign_type,
                'status': campaign.status,
                'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
                'end_date': campaign.end_date.isoformat() if campaign.end_date else None,
                'metrics': [
                    {'name': m.metric_name, 'value': float(m.metric_value), 'date': m.date.isoformat(), 'channel': m.channel}
                    for m in metrics_prefetched
                ],
                'goals': campaign.goals,
                'channels': campaign.channels,
                'target_leads': target_leads,
                'target_conversions': target_conversions,
                'leads_count': leads_count,
                'positive_replies': positive_replies,
                'negative_replies': negative_replies,
                'conversions': positive_replies,
                'conversion_progress': conversion_progress,
                'leads_progress': leads_progress,
                'emails_sent': total_sent,
                'emails_opened': total_opened,
                'emails_clicked': total_clicked,
                'emails_replied': total_replied,
                'emails_bounced': total_bounced,
                'emails_failed': total_failed,
                'open_rate': open_rate,
                'click_rate': click_rate,
                'reply_rate': reply_rate,
                'bounce_rate': bounce_rate,
            }
            campaigns_data.append(camp_dict)
        
        # Get market research data
        research_query = MarketResearch.objects.all()
        if user_id:
            research_query = research_query.filter(created_by_id=user_id)
        
        research_data = [
            {
                'id': r.id,
                'type': r.research_type,
                'topic': r.topic,
                'insights': r.insights,
                'findings': r.findings,
                'created_at': r.created_at.isoformat()
            }
            for r in research_query[:10]  # Recent research
        ]
        
        # Calculate aggregate metrics
        active_campaigns = campaigns_query.filter(status='active').count()
        
        # Get performance aggregates
        all_metrics = CampaignPerformance.objects.filter(
            campaign__in=campaigns_query
        ).values('metric_name').annotate(
            avg_value=Avg('metric_value'),
            total_count=Count('id')
        ).order_by('metric_name')  # Override default ordering to fix SQL Server GROUP BY error
        
        return {
            'campaigns': campaigns_data,
            'research': research_data,
            'stats': {
                'total_campaigns': len(campaigns_data),
                'active_campaigns': active_campaigns,
                'performance_metrics': list(all_metrics)
            }
        }
    
    def _build_context(self, marketing_data: Dict, additional_context: Optional[Dict] = None) -> str:
        """Build comprehensive context string for AI"""
        parts = []

        # Platform/agent context: so the model can answer "this platform", "this agent", "how does it work", "how to run campaign"
        parts.append(
            "PLATFORM CONTEXT (use when the user asks about 'this platform', 'this agent', 'how does it work', or 'how to run a campaign'): "
            "This is the **Marketing Agent** platform. It has tabs: **Research** (market/competitor reports), **Q&A** (this agent—answers about campaigns, ROI, conversion, leads), **Campaigns** (create and run campaigns: add leads, set emails, launch), **Notifications**, **Outreach**. "
            "When the user says 'this agent' they mean this Q&A/analytics agent or the whole platform. "
            "To run a campaign: go to Campaigns tab → create campaign (name, goal, audience) → add/import leads → set up emails → launch. Track performance in the dashboard and ask this Q&A agent for insights.\n\n"
        )

        # Recent conversation so the model can resolve "this campaign", "the active one", follow-ups
        conv_history = (additional_context or {}).get('conversation_history') or []
        if conv_history:
            parts.append("RECENT CONVERSATION – Campaign in context = the campaign from the **last Q&A only**. If the user says 'the campaign', 'it', 'its', or 'performance/issues/improvement of the campaign' (and did NOT say 'all campaigns'), answer **ONLY** for that one campaign. Do NOT add summer sales 26, testing compagin, or any other campaign. If user says 'all campaigns' or 'of all campaigns', answer for ALL campaigns.")
            for i, pair in enumerate(conv_history[-4:], 1):  # last 4 Q&A to keep prompt smaller
                q = pair.get('question') or pair.get('q') or ''
                a = pair.get('answer') or pair.get('a') or ''
                if q or a:
                    parts.append(f"  Q{i}: {q}")
                    parts.append(f"  A{i}: {a[:600]}{'...' if len(a) > 600 else ''}")
            parts.append("")

        context = "\n".join(parts) if parts else ""
        context += (
            "INSTRUCTION: For questions about HOW MANY campaigns, which are WORKING/ACTIVE, or campaign COUNT/STATUS, "
            "answer ONLY from the OVERVIEW and CAMPAIGNS sections below. Do NOT use the Market Research section for those questions.\n\n"
        )
        context += "MARKETING DATA CONTEXT:\n\n"
        
        # Add stats (primary source for count/status)
        stats = marketing_data.get('stats', {})
        context += f"OVERVIEW (use these numbers for 'how many' / 'working' / 'active' questions):\n"
        context += f"- Total Campaigns: {stats.get('total_campaigns', 0)}\n"
        context += f"- Active Campaigns: {stats.get('active_campaigns', 0)}\n\n"
        
        # Add campaigns (include email stats so "proper details" uses real numbers)
        campaigns = marketing_data.get('campaigns', [])
        if campaigns:
            context += f"CAMPAIGNS ({len(campaigns)} total):\n"
            for camp in campaigns[:10]:
                context += f"\nCampaign: {camp['name']}\n"
                context += f"- Type: {camp['type']}, Status: {camp['status']}\n"
                # Email performance (source of truth for campaign details)
                if camp.get('emails_sent') is not None and camp['emails_sent'] > 0:
                    context += f"- Emails sent: {camp['emails_sent']}\n"
                    if camp.get('open_rate') is not None:
                        context += f"  Open rate: {camp['open_rate']}%\n"
                    if camp.get('click_rate') is not None:
                        context += f"  Click rate: {camp['click_rate']}%\n"
                    if camp.get('reply_rate') is not None:
                        context += f"  Reply rate: {camp['reply_rate']}%\n"
                    if camp.get('bounce_rate') is not None:
                        context += f"  Bounce rate: {camp['bounce_rate']}%\n"
                    if camp.get('emails_opened') is not None:
                        context += f"  Emails opened: {camp['emails_opened']}\n"
                    if camp.get('emails_clicked') is not None:
                        context += f"  Emails clicked: {camp['emails_clicked']}\n"
                    if camp.get('emails_replied') is not None:
                        context += f"  Replies: {camp['emails_replied']}\n"
                    if camp.get('emails_failed') is not None and camp['emails_failed'] > 0:
                        context += f"  Failed emails: {camp['emails_failed']}\n"
                if camp.get('leads_count') is not None:
                    context += f"- Leads: {camp['leads_count']}\n"
                if camp.get('target_leads') is not None or camp.get('target_conversions') is not None:
                    context += f"- Targets: leads={camp.get('target_leads', 'N/A')}, conversions={camp.get('target_conversions', 'N/A')}\n"
                if camp.get('positive_replies') is not None or camp.get('conversions') is not None:
                    context += f"- Positive/Neutral replies (conversions): {camp.get('positive_replies', camp.get('conversions', 'N/A'))}\n"
                if camp.get('conversion_progress') is not None:
                    context += f"- Conversion progress: {camp['conversion_progress']}% (towards target conversions)\n"
                if camp.get('leads_progress') is not None:
                    context += f"- Leads progress: {camp['leads_progress']}% (towards target leads)\n"
                if camp['metrics']:
                    context += f"- Legacy metrics (use only if no email stats above):\n"
                    for metric in camp['metrics'][:5]:
                        context += f"  * {metric['name']}: {metric['value']} ({metric.get('channel', 'N/A')})\n"
        
        # Add market research (for strategy/trend questions only – do not use for count/status)
        research = marketing_data.get('research', [])
        if research:
            context += f"\nMARKET RESEARCH (recent topics only – do NOT use for 'how many campaigns' or 'working now'):\n"
            for r in research[:5]:
                context += f"- {r['type']}: {r['topic']}\n"
                if r.get('insights'):
                    context += f"  (Summary: {r['insights'][:150]}...)\n"
        
        # Add additional context if provided (skip conversation_history, already added above)
        if additional_context:
            extra = {k: v for k, v in additional_context.items() if k != 'conversation_history'}
            if extra:
                context += f"\nADDITIONAL CONTEXT:\n{json.dumps(extra, indent=2)}\n"
        
        return context
    
    def _generate_answer(self, question: str, context: str, request_context: Optional[Dict] = None) -> str:
        """Generate AI-powered answer to marketing question using Groq API"""
        # Format prompt for Groq (chat format)
        prompt = f"""Based on the marketing data and any RECENT CONVERSATION provided below, answer this question: "{question}"

{context}

CRITICAL RULES:
- **GENERAL / INDUSTRY QUESTIONS – no campaign data:** When the user asks **general** questions like "What are the best practices for our industry?", "best practices for email marketing?", "industry best practices", or "best practices for [marketing/campaigns]", give **general** best practices only (e.g. clear subject lines, A/B testing, segmentation, lead nurturing, clear CTAs, mobile-friendly, optimize send time). Do NOT list campaign names, conversion rates, "Key Trends", "Active Campaigns: 1", "Total campaigns: 5", "Campaign: tutor nearby users", "Which campaign is this about?", or any CAMPAIGNS data. One optional short line like "You can apply these to your campaigns" is fine; no dump of campaign metrics or status.
- **NEVER repeat the same sentence or paragraph.** If you have already stated a metric or fact once, STOP. Do not output "However, since the user..." or the same conversion/rate line again. One short answer only. If you find yourself writing the same line twice, delete it and end the response.
- **Do NOT put reasoning in your answer.** Do NOT write "To answer your question...", "I will look at the most recent Q&A...", "The last Q&A pair is...", "Since the user asked...", "Let me...". Give ONLY the direct answer with numbers (e.g. "For **summer sales 26**: conversion rate 0/100 = **0%**."). The user must see only the result.
- **Override – "all campaigns" in current question:** If the user says "all campaigns", "of all campaigns", "for all campaigns", "each campaign", "every campaign", or "all campagins" in the **current question**, answer for **ALL** campaigns (list metric or detail for every campaign). Do NOT answer only for the last-discussed campaign.
- **STEP 1 – Campaign in context = most recent Q&A only:** Which campaign (if any) is in the **last** user question or **last** answer? Use only that. If a campaign is in context and the user did NOT say "all campaigns", answer **ONLY** for that campaign. Do NOT add other campaigns (e.g. do NOT add summer sales 26, testing compagin, etc.). If the user says "the campaign", "it", "its", "this campaign", "performance/issues/improvement of the campaign", that means the campaign from the last Q&A only—answer for that one campaign only and stop. If no campaign in last Q&A → answer for all campaigns. Give one direct answer; no repetition.
- **User names a campaign in current question:** Use that campaign. **User says "it"/"its"/"this campaign"/"the campaign":** Use the campaign from the **last** Q&A only; answer ONLY for that campaign. Do NOT list other campaigns.
- **Single-word "campaign" or "campaigns":** Answer with count and names from OVERVIEW and CAMPAIGNS.
- **"This platform" / "this agent":** Use PLATFORM CONTEXT.
- **"For all campaigns" / "tell generally":** Apply the PREVIOUS answer's topic to all campaigns; give the actual content, not just campaign names.
- **Always name campaigns with status**: When listing or naming campaigns, always include **status** (draft/active/paused) after each name, e.g. "summer sales 261 (paused)", "testing compagin (draft)". Do not list campaign names without their status.
- **"What campaigns are performing best?" / "Which campaigns are performing best?" / "best performing campaigns"**: You MUST **name the best campaign(s) first** with a short reason (e.g. highest open rate, conversion progress, or reply rate). Then optionally list others briefly. Example: "**summer sales 261** (paused) is performing best: 54.55% open rate, 72.73% reply rate, 70% conversion progress. Other campaigns have 0 emails sent or 0% rates." Do NOT only list all campaigns with metrics—always state clearly "**X** is performing best" (or "**X** and **Y**") and why, then stop or briefly summarize the rest.
- **"How are our campaigns performing?" / "campaigns performing this month?"**: The user wants **performance metrics**, not just names. For each campaign in CAMPAIGNS, give name **with status** (e.g. summer sales 261 (paused)), then: Emails sent, Open rate, Click rate, Reply rate, Conversion progress, Leads progress. Do NOT reply with only "Total: 4, Active: 0" and a list of names—include actual performance numbers per campaign, each with status.
- **Campaign count/status questions** (e.g. "how many campaigns", "give their names"): Answer with numbers from OVERVIEW and list each campaign with its status, e.g. "summer sales 2 (draft), testing compagin (draft), summer sales 261 (paused), summer sales 26 (paused)".
- **"Are we on track to meet our campaign goals?"**: Answer **first with Yes or No** (e.g. "**No.**" or "**Yes**, for [campaign name]."), then give reasons. Format: "**No.** Reasons: (1) ... (2) ..." or "**Yes**, for summer sales 261. Reasons: ...". Do NOT start with "Reasons:" only—always state Yes or No first.
- **"What are the key trends in our marketing data?"**: "Key trends" means **performance patterns** in the data, not just a list of campaigns. Summarize: (a) overall pattern (e.g. no active campaigns; all draft/paused); (b) **performance trends** by campaign—which have strong vs weak conversion, open/click rates, leads progress (e.g. summer sales 261 (paused): 70% conversion progress but 3% leads progress, 54% open rate; summer sales 26: 0% open/click); (c) takeaway (e.g. low engagement overall, leads lagging targets). Do NOT answer with only "Total: 4, Active: 0" and campaign names with status—include **metrics and patterns** (conversion %, open %, click %, leads %).
- **"Which campaigns are in working state?" / "which campaigns are working?" / "which are active?"**: Use OVERVIEW (active_campaigns) and CAMPAIGNS (Status: active/draft/paused). If active_campaigns = 0, answer clearly: "**None** of your campaigns are currently in active/working state. All [N] are draft or paused: [list each with status, e.g. summer sales 2 (draft), testing compagin (draft), summer sales 261 (paused), summer sales 26 (paused)]." If some are active, list only those: "Campaigns in working/active state: [names]. Others are draft/paused: [names]." Do NOT just list all campaign names without stating clearly that none are working when active = 0.
- **Campaign count/status questions** (e.g. "how many are working", "campaigns working now"): Answer from OVERVIEW and CAMPAIGNS. Give a clear count and, for "which are working", list by status as above. Do NOT output "Market Trend Analysis" or generic trend content.
- **"Why are sales dropping?" / "why is performance low?" / "why are conversions low?"**: This is an **analysis** question—give **reasons** from the data, not just one metric. Use CAMPAIGNS and OVERVIEW: e.g. no campaigns are currently active (all draft/paused) so there’s no live outreach; low conversion or leads progress; low open/click rates; few emails sent. List 2–4 specific causes from the data (campaign status, conversion %, leads %, open/click rates). Do NOT reply with only "conversion rate 0/100"—explain **why** sales might be dropping (e.g. "**Reasons:** (1) No campaigns are active—all are draft or paused. (2) Campaigns that ran have low leads progress (e.g. 3/100) and low click rates. (3) ...").
- **"How do they need optimization?" / "how do [these] campaigns need to be optimized?"** (follow-up after "which need optimization"): Give **specific optimization steps** using CAMPAIGNS data. Do NOT repeat the list of campaign names only. For each campaign (or in summary): **Paused/draft** → Resume or launch; **Low open rate** → Improve subject lines and send time; **Low click rate** → Improve email content and CTA; **Low leads/conversion progress** → Improve targeting, lead magnets, follow-up. Use actual metrics (e.g. summer sales 261 (paused): click rate 9.09% → improve CTAs; leads 3/100 → improve lead gen). Give concrete **how** (actions/steps), not just names.
- **"Ideal email template" / "best email template" / "what should email template include"**: Answer with **template structure and best practices** (e.g. clear subject line, preview text, personalized greeting, short body, one clear CTA, signature, mobile-friendly, concise). Do NOT paste full campaign stats (Emails sent, Open rate, etc.) in this answer—give template advice only. Optionally one short line on how it helps open/click rates, but no campaign data dump.
- **Campaign details / "proper details" / "give details"**: Use the EMAIL stats from the CAMPAIGNS section (Emails sent, Open rate, Click rate, Reply rate, Leads, Failed emails). These are the real numbers. Do NOT use "Legacy metrics" when a campaign has "Emails sent" and rates listed.
- **Conversion rate** (when the user asks "conversion rate" or "our conversion rate" only—NOT "lead conversion rate"): This is progress toward the **Conversions Target** (positive_replies / target_conversions). When the user does NOT name a campaign, report for **every campaign that has conversion data**, e.g. "summer sales 261: **70%** (7/10); summer sales 26: 0%; others: 0%." Do NOT default to only the first or "active" campaign—that can wrongly show 0%. If only one campaign has non-zero conversion progress, say e.g. "**70%** for summer sales 261; other campaigns have 0%." so the user sees the real number.
- **Lead conversion rate** (when the user asks "lead conversion rate" or "our lead conversion rate"): This is **only** leads_count / target_leads (Leads Target progress). Report e.g. "summer sales 261: 3/100 = **3%**". **Never** report positive_replies/target_conversions (e.g. 7/10 = 70%) as "lead conversion rate"—that is "conversion rate". Lead conversion rate = leads progress only (3/100 = 3%). If specific campaign in context, use that; otherwise give for all campaigns.
- **"About which campaign are you answering?" / "which campaign is this about?" / "which campaign u are answering?"**: Answer from the **last answer** you gave. If the last answer was about **one** campaign (because the user had asked about "this campaign" or named a campaign), say "I was answering about **[that campaign name]**." If the last answer was about **all** campaigns (e.g. "what campaigns are performing best?", "how are campaigns performing?"), say "I was answering about **all** your campaigns—you didn’t specify one, so I summarized or compared all of them." Do NOT guess or pick the first/active campaign name when the user had asked about all campaigns.
- **Default: SHORT.** Unless the user asks for "details", "full analysis", "recommendations", "insights", "strategy", or "why", give 1–4 sentences only. No "Key Insights", "Recommendations", or long tables.
- **Simple factual questions** (how many, list, count, total, which, status): One direct sentence or brief list; include campaign names **with status** (e.g. summer sales 261 (paused)) when listing campaigns. No trend analysis.
- **Only when the user explicitly asks for more** (e.g. "analyze", "recommend", "insights", "strategy"): You may add ## Key Insights and ## Recommendations. Otherwise do not.

FORMATTING:
1. Use **double asterisks** for key metrics/terms.
2. Prefer 1–3 sentences. No ## sections unless the user asked for analysis/recommendations/details.
3. Never respond with "Market Trend Analysis" or "Current Market Trends" unless the user explicitly asked about market trends.
4. **No repetition**: Give a single, direct answer. NEVER write the same sentence or paragraph twice. If you have given the conversion rate (or any metric) once, END the response. Do not write "However, since the user..." more than once. Do not repeat the same line (e.g. "For summer sale 26, the conversion rate is 0 conversions...") again—once only, then stop.
5. **No reasoning in the answer**: Do not start with "To answer your question...", "I will look at...", "The last Q&A pair is...". Start directly with the answer (e.g. "For **summer sales 26**: conversion rate 0/100 = **0%**.").
6. **One campaign only when user said "the campaign" / "it" / "its":** When the user asked about "performance, issues, steps of improvement of the campaign" and the last Q&A was about one campaign, give details for **that one campaign only**. Stop after that campaign.

Be specific and use numbers. Give only the direct answer; then stop."""
        
        try:
            # Use Groq for Q&A
            answer = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.3,  # Lower temperature for more factual answers
                max_tokens=2000  # Groq supports longer responses
            )
            return answer
        except Exception as e:
            self.log_action("Error generating answer", {"error": str(e)})
            err_str = str(e)
            if "429" in err_str or "rate_limit" in err_str.lower():
                return "The service is busy (rate limit). Please try again in a few seconds."
            return f"I encountered an error while analyzing the data: {err_str}"
    
    def _extract_insights(self, marketing_data: Dict, question: str) -> List[Dict]:
        """Extract key insights from data"""
        insights = []
        
        stats = marketing_data.get('stats', {})
        campaigns = marketing_data.get('campaigns', [])
        
        # Campaign status insights
        active_count = stats.get('active_campaigns', 0)
        total_count = stats.get('total_campaigns', 0)
        if total_count > 0:
            active_percentage = (active_count / total_count) * 100
            insights.append({
                'type': 'campaigns',
                'title': 'Active Campaigns',
                'value': f"{active_count}/{total_count} campaigns active ({active_percentage:.1f}%)",
                'status': 'good' if active_percentage > 50 else 'warning'
            })
        
        # Performance insights (email stats or legacy metrics)
        if campaigns:
            campaigns_with_metrics = [c for c in campaigns if c.get('metrics') or (c.get('emails_sent') is not None and c.get('emails_sent', 0) > 0)]
            if campaigns_with_metrics:
                insights.append({
                    'type': 'performance',
                    'title': 'Data Availability',
                    'value': f"{len(campaigns_with_metrics)} campaigns have performance data",
                    'status': 'good'
                })
        
        return insights
    
    def _create_data_summary(self, marketing_data: Dict) -> Dict:
        """Create summary of available data"""
        return {
            'campaigns_count': len(marketing_data.get('campaigns', [])),
            'research_count': len(marketing_data.get('research', [])),
            'has_performance_data': any(
                c.get('metrics') for c in marketing_data.get('campaigns', [])
            ),
            'stats': marketing_data.get('stats', {})
        }
    
    def analyze_campaign_performance(self, campaign_id: int, user_id: Optional[int] = None) -> Dict:
        """
        Analyze specific campaign performance
        
        Args:
            campaign_id (int): Campaign ID to analyze
            user_id (int): User ID for access control
            
        Returns:
            Dict: Performance analysis
        """
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            if user_id and campaign.owner_id != user_id:
                return {'success': False, 'error': 'Access denied'}
            
            metrics = CampaignPerformance.objects.filter(campaign=campaign)
            
            # Calculate key metrics
            total_impressions = metrics.filter(metric_name='impressions').aggregate(
                total=Sum('metric_value')
            )['total'] or 0
            
            total_clicks = metrics.filter(metric_name='clicks').aggregate(
                total=Sum('metric_value')
            )['total'] or 0
            
            total_conversions = metrics.filter(metric_name='conversions').aggregate(
                total=Sum('metric_value')
            )['total'] or 0
            
            # Calculate rates
            ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            conversion_rate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
            
            # Generate analysis
            analysis_prompt = f"""Analyze this campaign performance:

Campaign: {campaign.name}
Type: {campaign.campaign_type}
Status: {campaign.status}

Performance Metrics:
- Impressions: {total_impressions:,.0f}
- Clicks: {total_clicks:,.0f}
- Conversions: {total_conversions:,.0f}
- CTR: {ctr:.2f}%
- Conversion Rate: {conversion_rate:.2f}%

Provide:
1. Overall performance assessment
2. What's working well
3. Areas for improvement
4. Recommendations for optimization"""
            
            # Use Groq for Q&A analysis
            analysis = self._call_llm_for_reasoning(analysis_prompt, self.system_prompt, temperature=0.3)
            
            return {
                'success': True,
                'campaign_id': campaign_id,
                'campaign_name': campaign.name,
                'metrics': {
                    'impressions': float(total_impressions),
                    'clicks': float(total_clicks),
                    'conversions': float(total_conversions),
                    'ctr': ctr,
                    'conversion_rate': conversion_rate
                },
                'analysis': analysis
            }
        except Campaign.DoesNotExist:
            return {'success': False, 'error': 'Campaign not found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

