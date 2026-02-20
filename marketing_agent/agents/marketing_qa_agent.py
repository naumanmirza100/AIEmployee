"""
Marketing Knowledge Q&A + Analytics Agent
Foundation Agent - Provides data understanding and answers marketing questions
This is the BRAIN that all other agents will use.
"""

from .marketing_base_agent import MarketingBaseAgent
from .platform_content import get_platform_response
from typing import Dict, Optional, List
from marketing_agent.models import Campaign, CampaignPerformance, MarketResearch, EmailSendHistory, Reply
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
        - "What campaigns are performing best?"
        - "Which channels are most effective?"
        - "What should we focus on?"
        
        Always base your answers on the data provided. Be specific, actionable, and data-driven.

        CONVERSATION CONTEXT:
        - When the user says "this campaign", "the active one", "that campaign", "it", "in this campaign", or similar, resolve the reference from the RECENT CONVERSATION below (the last answer that mentioned a specific campaign).
        - When the user says "for all campaigns", "for all campaign", "tell generally for all", "same for other campaign", "also for other campaigns", "for other campaign", "bc and cc for all campaign", or similar, they mean: apply the SAME TOPIC or SUBJECT from the PREVIOUS answer to all campaigns or in general. Look at the last Q&A in RECENT CONVERSATION—what was the user asking and what did you explain? Continue that same topic (e.g. CC/BC and how to use them to improve emails) and answer it generally or for all campaigns. Do NOT ignore the previous topic and only list campaign names or give a generic reply.
        - When answering about campaigns, always include campaign names (e.g. "summer sales 261", "testing compagin")—do not say "the campaign" without naming it when multiple campaigns exist.
        - For follow-up questions (e.g. "What is our lead conversion rate? in this campaign"), use the campaign identified in the recent conversation and the CAMPAIGNS data to compute or state the metric."""
    
    def _normalize_question_typos(self, question: str) -> str:
        """Fix common typos so platform/campaign detection and LLM understand the question."""
        if not question or not isinstance(question, str):
            return question
        q = question.strip()
        # Common typos for "campaign" (preserve rest of question)
        typos = [
            (r'\bcaomaphin\b', 'campaign'),
            (r'\bcampagin\b', 'campaign'),
            (r'\bcompagin\b', 'campaign'),
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
        
        campaigns = campaigns_query.select_related('owner').prefetch_related('performance_metrics')
        
        # Get campaign data (including email stats from EmailSendHistory and Reply)
        campaigns_data = []
        for campaign in campaigns:
            # Legacy performance metrics (CampaignPerformance table)
            metrics = CampaignPerformance.objects.filter(campaign=campaign)
            # Email campaign stats (source of truth for sent, open, click, reply rates)
            email_sends = EmailSendHistory.objects.filter(campaign=campaign)
            total_sent = email_sends.filter(status__in=['sent', 'delivered', 'opened', 'clicked']).count()
            total_opened = email_sends.filter(status__in=['opened', 'clicked']).count()
            total_clicked = email_sends.filter(status='clicked').count()
            total_bounced = email_sends.filter(status='bounced').count()
            total_replied = Reply.objects.filter(campaign=campaign).count()
            total_failed = email_sends.filter(status='failed').count()
            leads_count = campaign.leads.count()
            # Positive/neutral = conversions (same as dashboard "Progress Towards Targets")
            positive_replies = Reply.objects.filter(
                campaign=campaign,
                interest_level__in=['positive', 'neutral', 'requested_info', 'objection']
            ).count()
            negative_replies = Reply.objects.filter(
                campaign=campaign,
                interest_level__in=['negative', 'unsubscribe']
            ).count()
            target_leads = getattr(campaign, 'target_leads', None)
            target_conversions = getattr(campaign, 'target_conversions', None)
            conversion_progress = round((positive_replies / target_conversions * 100), 1) if target_conversions and target_conversions > 0 else None
            leads_progress = round((leads_count / target_leads * 100), 1) if target_leads and target_leads > 0 else None
            # Rates (only when we have sends)
            open_rate = round((total_opened / total_sent) * 100, 2) if total_sent > 0 else None
            click_rate = round((total_clicked / total_sent) * 100, 2) if total_sent > 0 else None
            reply_rate = round((total_replied / total_sent) * 100, 2) if total_sent > 0 else None
            bounce_rate = round((total_bounced / total_sent) * 100, 2) if total_sent > 0 else None

            camp_dict = {
                'id': campaign.id,
                'name': campaign.name,
                'type': campaign.campaign_type,
                'status': campaign.status,
                'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
                'end_date': campaign.end_date.isoformat() if campaign.end_date else None,
                'metrics': [
                    {
                        'name': m.metric_name,
                        'value': float(m.metric_value),
                        'date': m.date.isoformat(),
                        'channel': m.channel
                    }
                    for m in metrics[:20]
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
            parts.append("RECENT CONVERSATION (use this to resolve 'this campaign', 'the active one', 'it', and to understand 'for all campaigns' / 'tell generally' = same TOPIC as previous answer):")
            for i, pair in enumerate(conv_history[-6:], 1):  # last 6 Q&A
                q = pair.get('question') or pair.get('q') or ''
                a = pair.get('answer') or pair.get('a') or ''
                if q or a:
                    parts.append(f"  Q{i}: {q}")
                    # Keep enough of the answer so the TOPIC is clear (e.g. CC/BC + email tips)
                    parts.append(f"  A{i}: {a[:1200]}{'...' if len(a) > 1200 else ''}")
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
- **Single-word "campaign" or "campaigns"**: If the question is just "campaign" or "campaigns", interpret as asking about the user's campaigns. Answer with count and names from OVERVIEW and CAMPAIGNS (e.g. "You have X campaigns: [names]. Ask for a specific campaign for details."). Do not say you couldn't find information.
- **"This platform" / "this agent"**: Use the PLATFORM CONTEXT in the data above. When the user asks about "this platform", "this agent", "how does it work", or "how to run a campaign", explain using that context. Do not say you don't have information—the platform context is provided.
- **Topic continuity ("for all campaigns", "tell generally")**: If the user says "for all campaigns", "for all campaign", "tell generally for all", "same for other campaign", "also for other campaigns", "bc and cc for all campaign", or similar, they are referring to the TOPIC of the PREVIOUS answer. Look at the last Q&A in RECENT CONVERSATION: what was explained (e.g. CC/BC full form and how to use them to improve emails)? Your reply must CONTINUE that same topic—give the same type of content (definitions, tips, advice) applied generally or for all campaigns. Do NOT reply with only campaign names or "let me know if you'd like to know more"; give the actual advice/content for all campaigns.
- **Resolve references from conversation**: If the user says "this campaign", "the active one", "that campaign", "it", "in this campaign", or "in the active campaign", look at the RECENT CONVERSATION and use the campaign name(s) from the last relevant answer (e.g. "summer sales 261"). Then answer using that campaign's data from the CAMPAIGNS section.
- **Always name campaigns**: When discussing campaigns, always include their names (e.g. "summer sales 261", "testing compagin"). When listing or counting campaigns, include the names. Do not say "the campaign" without the name when multiple campaigns exist.
- **Campaign count/status questions** (e.g. "how many campaigns", "give their names"): Answer with numbers from OVERVIEW and list campaign names from CAMPAIGNS. One short sentence plus the names.
- **Campaign count/status questions** (e.g. "how many are working", "campaigns working now"): Answer ONLY from OVERVIEW and CAMPAIGNS. Do NOT output "Market Trend Analysis" or generic trend content.
- **Campaign details / "proper details" / "give details"**: Use the EMAIL stats from the CAMPAIGNS section (Emails sent, Open rate, Click rate, Reply rate, Leads, Failed emails). These are the real numbers. Do NOT use "Legacy metrics" when a campaign has "Emails sent" and rates listed.
- **Lead conversion rate / conversion rate**: If the user asks about "lead conversion rate" or "conversion rate" (for "this campaign", "the active campaign", or a named campaign), use the RECENT CONVERSATION to identify the campaign, then use that campaign's data from CAMPAIGNS. We track conversions as Positive/Neutral replies. Give: (1) **Conversion progress**: positive_replies / target_conversions (e.g. 7/10 = 70%). (2) **Leads progress**: leads_count / target_leads (e.g. 3/100 = 3%). Always state the campaign name and the numbers (e.g. "For **summer sales 261**: conversions 7/10 = **70%**; leads 3/100 = **3%**."). Never say "I don't have the data" when CAMPAIGNS section has Positive/Neutral replies and Targets.
- **Default: SHORT.** Unless the user asks for "details", "full analysis", "recommendations", "insights", "strategy", or "why", give 1–4 sentences only. No "Key Insights", "Recommendations", or long tables.
- **Simple factual questions** (how many, list, count, total, which, status): One direct sentence or brief list; include campaign names when relevant. No trend analysis.
- **Only when the user explicitly asks for more** (e.g. "analyze", "recommend", "insights", "strategy"): You may add ## Key Insights and ## Recommendations. Otherwise do not.

FORMATTING:
1. Use **double asterisks** for key metrics/terms.
2. Prefer 1–3 sentences. No ## sections unless the user asked for analysis/recommendations/details.
3. Never respond with "Market Trend Analysis" or "Current Market Trends" unless the user explicitly asked about market trends.

Be specific and use numbers from the OVERVIEW and CAMPAIGNS data. Resolve "this campaign" from RECENT CONVERSATION. When in doubt, keep the answer short."""
        
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
            return f"I encountered an error while analyzing the data: {str(e)}"
    
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
        
        # Performance insights (if metrics exist)
        if campaigns:
            campaigns_with_metrics = [c for c in campaigns if c.get('metrics')]
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

