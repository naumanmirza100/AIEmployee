"""
Market & Competitive Research Agent
Continuously analyzes market trends, customer behavior, and competitor activities
to identify opportunities, risks, and positioning strategies.
"""

from .marketing_base_agent import MarketingBaseAgent
from .platform_content import get_platform_response
from typing import Dict, Optional, List
from marketing_agent.models import MarketResearch
from django.contrib.auth.models import User
import json
import re
from datetime import datetime


class MarketResearchAgent(MarketingBaseAgent):
    """
    Market & Competitive Research Agent
    
    This agent:
    - Analyzes market trends and opportunities
    - Tracks competitor activities and strategies
    - Identifies customer behavior patterns
    - Discovers market opportunities and threats
    - Generates positioning strategies
    - Stores research findings for use by Q&A and other agents
    
    This is Phase 2 - feeds insights into Q&A agent and other marketing agents.
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Market & Competitive Research Agent for a marketing system.
        Your role is to:
        1. Analyze market trends and identify opportunities
        2. Research competitor activities and strategies
        3. Understand customer behavior patterns
        4. Identify market risks and threats
        5. Suggest positioning strategies
        6. Provide actionable market intelligence

        IMPORTANT: Keep responses concise and to the point. Use short bullet points instead of long paragraphs.
        Limit each section to 3-5 key points maximum. Avoid filler text and repetition.
        Be specific, analytical, and strategic in your research findings."""

    INTENT_CLASSIFY_SYSTEM = """You are an intent classifier for a Market & Competitive Research agent.
Given the user's message, reply with exactly one word:
- greeting: hi, hello, how are you, thanks, bye, lets start, ready, small talk, etc. (NOT asking about the platform or what it does.)
- platform_question: user is asking about THIS PLATFORM/APP/WEBSITE/SYSTEM—what it does, how helpful it is, how to use it, how to run a campaign (e.g. "what does this platform do", "how helpful is this platform", "what is this website", "what is this system", "how to use this", "how to run campaign here"). They want an answer about the product itself.
- meta_question: user is asking what THIS RESEARCH AGENT can do or which topics it can research (e.g. what can you research, which topics, what questions can you answer, give me examples of research topics). They want to know research capabilities of this tab.
- definition: user is asking for the MEANING, FULL FORM, or DEFINITION of a term/abbreviation (e.g. "meaning of AWS", "what is API"). NOT a research report.
- off_topic: not a research request (e.g. dismissive, random, or unrelated).
- research: user wants an actual REPORT on a market/competitor/customer/opportunity/risk topic (e.g. "cloud trends", "web and ai companies", "competitor analysis for Amazon"). They gave a topic to analyze.
Ignore typos and casual language. Reply with only one word: greeting, platform_question, meta_question, definition, off_topic, or research."""

    def _classify_intent(self, topic: str) -> str:
        """
        Use the LLM to classify user intent so any phrasing/typos are handled.
        Returns one of: 'greeting', 'platform_question', 'meta_question', 'definition', 'off_topic', 'research'.
        On failure or empty topic, returns 'greeting' for empty and 'research' otherwise (don't block real research).
        """
        if not topic or not isinstance(topic, str):
            return 'greeting'
        t = topic.strip()
        if not t:
            return 'greeting'
        if not self.groq_client:
            return 'research'
        try:
            prompt = f'User message: "{t[:500]}"'
            out = self._call_llm_for_reasoning(
                prompt,
                self.INTENT_CLASSIFY_SYSTEM,
                temperature=0.0,
                max_tokens=20
            )
            if not out:
                return 'research'
            parts = out.strip().lower().split()
            first = (parts[0] if parts else '').strip()
            first = re.sub(r'[^a-z_]', '', first)
            if first in ('greeting', 'platform_question', 'platform', 'meta_question', 'meta', 'definition', 'def', 'off_topic', 'offtopic', 'research'):
                if first == 'platform':
                    return 'platform_question'
                if first == 'meta':
                    return 'meta_question'
                if first == 'def':
                    return 'definition'
                if first in ('offtopic', 'off_topic'):
                    return 'off_topic'
                return first
            if 'greeting' in out.lower():
                return 'greeting'
            if 'platform' in out.lower():
                return 'platform_question'
            if 'meta' in out.lower() or 'question' in out.lower():
                return 'meta_question'
            if 'definition' in out.lower() or 'meaning' in out.lower() or 'define' in out.lower():
                return 'definition'
            if 'off' in out.lower() or 'topic' in out.lower():
                return 'off_topic'
            if 'research' in out.lower():
                return 'research'
            return 'research'
        except Exception as e:
            self.log_action("Intent classification failed, treating as research", {"error": str(e)})
            return 'research'

    def _get_short_definition(self, topic: str) -> str:
        """Return a short (1-3 sentence) definition for the term the user asked about. Handles typos like 'meanin gof aws'."""
        if not self.groq_client:
            return (
                "This agent does **market and competitive research** only. For the meaning of terms (e.g. AWS = Amazon Web Services), "
                "try a quick search. If you want a research report on a topic, ask e.g. 'market trends for cloud computing' or 'competitor analysis for AWS'."
            )
        try:
            prompt = f"""The user asked for the meaning or definition of something. They may have typos (e.g. "meanin gof aws" = meaning of AWS).
Reply with a brief, clear definition in 1-3 sentences. If it's an abbreviation, give the full form first (e.g. "AWS = Amazon Web Services. It is ...").
User message: "{topic[:200]}"
Reply only with the definition, no preamble."""
            out = self._call_llm_for_reasoning(
                prompt,
                "You are a helpful assistant that gives short, accurate definitions of terms and abbreviations. Be concise.",
                temperature=0.2,
                max_tokens=150
            )
            if out and out.strip():
                return out.strip()
        except Exception as e:
            self.log_action("Short definition failed", {"error": str(e)})
        return (
            "This agent focuses on **market and competitive research**. For definitions, try a quick search. "
            "If you want a research report (e.g. on the AWS/cloud market), ask e.g. 'market trends for cloud computing'."
        )

    def process(self, research_type: str, topic: str, user_id: int, 
                additional_context: Optional[Dict] = None) -> Dict:
        """
        Main entry point - conducts market research
        
        Args:
            research_type (str): Type of research (market_trend, competitor, customer_behavior, opportunity, threat)
            topic (str): Research topic/question
            user_id (int): User ID for storing research
            additional_context (Dict): Optional context (competitor names, industry, etc.)
            
        Returns:
            Dict: Research findings with insights
        """
        self.log_action("Conducting market research", {
            "type": research_type,
            "topic": topic[:100]
        })

        intent = self._classify_intent(topic)
        if intent == 'greeting':
            return {
                'success': True,
                'research_id': None,
                'research_type': research_type,
                'topic': topic,
                'findings': {},
                'insights': "Hi! Enter a research topic to get started (e.g. market trends for cloud, competitor analysis for X). Choose a research type and add optional context above.",
                'opportunities': [],
                'risks': [],
                'recommendations': [],
                'source_urls': []
            }
        if intent == 'platform_question':
            insights = get_platform_response(topic)
            return {
                'success': True,
                'research_id': None,
                'research_type': research_type,
                'topic': topic,
                'findings': {},
                'insights': insights,
                'opportunities': [],
                'risks': [],
                'recommendations': [],
                'source_urls': []
            }
        if intent == 'meta_question':
            return {
                'success': True,
                'research_id': None,
                'research_type': research_type,
                'topic': topic,
                'findings': {},
                'insights': (
                    "You can research **market trends**, **competitors**, **customer behavior**, **opportunities**, or **risks**. "
                    "Enter a topic (e.g. 'cloud adoption in UK', 'competitor analysis for Amazon', 'web and AI companies') and choose a research type above. "
                    "Ask for a specific topic when you want a full report."
                ),
                'opportunities': [],
                'risks': [],
                'recommendations': [],
                'source_urls': []
            }
        if intent == 'off_topic':
            return {
                'success': True,
                'research_id': None,
                'research_type': research_type,
                'topic': topic,
                'findings': {},
                'insights': (
                    "That doesn't look like a research topic. Ask about a **specific market**, **competitor**, or **trend**—e.g. "
                    "'cloud adoption in UK', 'competitor analysis for Amazon', or 'customer behavior in e-commerce'."
                ),
                'opportunities': [],
                'risks': [],
                'recommendations': [],
                'source_urls': []
            }
        if intent == 'definition':
            definition_insights = self._get_short_definition(topic)
            return {
                'success': True,
                'research_id': None,
                'research_type': research_type,
                'topic': topic,
                'findings': {},
                'insights': definition_insights,
                'opportunities': [],
                'risks': [],
                'recommendations': [],
                'source_urls': []
            }

        # Run research (no relevance check—accept the user's topic and selected type)
        research_findings = self._conduct_research(research_type, topic, additional_context)
        
        # Store research in database
        try:
            user = User.objects.get(id=user_id)
            market_research = MarketResearch.objects.create(
                research_type=research_type,
                topic=topic,
                findings=research_findings.get('findings', {}),
                insights=research_findings.get('insights', ''),
                source_urls=research_findings.get('source_urls', []),
                created_by=user
            )
            
            research_id = market_research.id
        except User.DoesNotExist:
            research_id = None
            self.log_action("Warning: User not found, research not saved", {"user_id": user_id})
        
        return {
            'success': True,
            'research_id': research_id,
            'research_type': research_type,
            'topic': topic,
            'findings': research_findings.get('findings', {}),
            'insights': research_findings.get('insights', ''),
            'opportunities': research_findings.get('opportunities', []),
            'risks': research_findings.get('risks', []),
            'recommendations': research_findings.get('recommendations', []),
            'source_urls': research_findings.get('source_urls', [])
        }
    
    def _conduct_research(self, research_type: str, topic: str, 
                         additional_context: Optional[Dict] = None) -> Dict:
        """
        Conduct research using AI - analyzes market, competitors, trends, etc.
        
        Args:
            research_type (str): Type of research
            topic (str): Research topic
            additional_context (Dict): Additional context (competitors, industry, etc.)
            
        Returns:
            Dict: Structured research findings
        """
        # Build research prompt based on type
        prompt = self._build_research_prompt(research_type, topic, additional_context)
        
        # Get AI-generated research
        try:
            research_response = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.5,
                max_tokens=700
            )
        except Exception as e:
            self.log_action("Error generating research", {"error": str(e)})
            from core.api_key_service import QuotaExhausted, NoKeyAvailable
            if isinstance(e, QuotaExhausted):
                raise
            if isinstance(e, NoKeyAvailable):
                raise
            research_response = f"Research analysis encountered an error: {str(e)}"
        
        # Parse and structure findings
        findings = self._parse_research_response(research_type, research_response, additional_context)
        
        return findings
    
    def _build_research_prompt(self, research_type: str, topic: str, 
                               additional_context: Optional[Dict] = None) -> str:
        """Build research prompt based on type"""
        
        base_prompt = f"Research Topic: {topic}\n\n"
        
        if additional_context:
            context_str = "\nContext:\n"

            competitors = additional_context.get('competitors') or additional_context.get('competitor')
            if competitors:
                if isinstance(competitors, list):
                    context_str += f"Competitors: {', '.join(str(c) for c in competitors)}\n"
                else:
                    context_str += f"Competitors: {competitors}\n"

            if 'industry' in additional_context:
                context_str += f"Industry: {additional_context['industry']}\n"
            if 'geographic_region' in additional_context:
                context_str += f"Region: {additional_context['geographic_region']}\n"

            known_fields = {'competitors', 'competitor', 'industry', 'geographic_region'}
            for key, value in additional_context.items():
                if key not in known_fields and value:
                    context_str += f"{key.replace('_', ' ').title()}: {value}\n"

            context_str += "\nAnalyze ONLY the provided competitors. Be specific, not generic.\n\n"
            base_prompt += context_str
        
        if research_type == 'market_trend':
            has_specific_competitors = additional_context and ('competitors' in additional_context or 'competitor' in additional_context)

            if has_specific_competitors:
                prompt = f"""{base_prompt}
Keep response SHORT (under 400 words). Use bullet points, not paragraphs.

## 📈 Trends Impacting Competitors
| Trend | Competitor Impact | Who Benefits |
|-------|------------------|--------------|
(3 rows max)

## 🎯 Key Takeaways
- 3-4 bullet points: top trends, who's best positioned, biggest opportunity

## 📝 Conclusion
2-3 sentences only. End here, nothing after this."""
            else:
                prompt = f"""{base_prompt}
Keep response SHORT (under 400 words). Use bullet points, not paragraphs.

## 📈 Top Market Trends
- 3-4 key trends (1 line each)

## 📊 Market Drivers
| Driver | Impact | Timeframe |
(3 rows max)

## 🎯 Recommendations
1-3 actionable recommendations (1 line each)

## 📝 Conclusion
2-3 sentences only. End here, nothing after this."""
        
        elif research_type == 'competitor':
            has_specific_competitors = additional_context and ('competitors' in additional_context or 'competitor' in additional_context)

            if has_specific_competitors:
                prompt = f"""{base_prompt}
Keep response SHORT (under 400 words). Use bullet points, not paragraphs.

## 🔍 Competitor Analysis
For each competitor: 2-3 strengths, 2-3 weaknesses (bullet points only).

## 📊 Comparison
| Aspect | Competitor 1 | Competitor 2 |
(4-5 rows: Pricing, Features, Target Market, Strengths, Weaknesses)

## 🎯 Key Insights & Recommendations
- 3-4 bullet points: gaps, opportunities, what to do

## 📝 Conclusion
2-3 sentences only. End here, nothing after this."""
            else:
                prompt = f"""{base_prompt}
Keep response SHORT (under 400 words). Use bullet points, not paragraphs.

## 🔍 Key Competitors
- 3 competitors with 1-line description each

## 📊 Comparison
| Competitor | Strategy | Strengths | Weaknesses |
(3 rows max)

## 🎯 Recommendations
1-3 actionable positioning strategies (1 line each)

## 📝 Conclusion
2-3 sentences only. End here, nothing after this."""
        
        elif research_type == 'customer_behavior':
            has_specific_competitors = additional_context and ('competitors' in additional_context or 'competitor' in additional_context)

            if has_specific_competitors:
                prompt = f"""{base_prompt}
Keep response SHORT (under 400 words). Use bullet points, not paragraphs.

## 👥 Customer Behavior per Competitor
For each competitor: segments, buying patterns, pain points (2-3 bullets each).

## 📊 Comparison
| Aspect | Competitor 1 | Competitor 2 |
(4 rows: Segments, Engagement, Pain Points, Loyalty)

## 🎯 Marketing Recommendations
- 3 bullet points on messaging strategies

## 📝 Conclusion
2-3 sentences only. End here, nothing after this."""
            else:
                prompt = f"""{base_prompt}
Keep response SHORT (under 400 words). Use bullet points, not paragraphs.

## 👥 Customer Segments
- 2-3 key segments (1 line each)

## 🛒 Buying Patterns & Pain Points
- 3-4 bullet points

## 🎯 Marketing Recommendations
1-3 actionable recommendations (1 line each)

## 📝 Conclusion
2-3 sentences only. End here, nothing after this."""
        
        elif research_type == 'opportunity':
            has_specific_competitors = additional_context and ('competitors' in additional_context or 'competitor' in additional_context)

            if has_specific_competitors:
                prompt = f"""{base_prompt}
Keep response SHORT (under 400 words). Use bullet points, not paragraphs.

## 💡 Gaps per Competitor
For each competitor: 2-3 gaps/missing features (bullet points only).

## 📊 Opportunities
| Opportunity | Gap | Impact | Priority |
(3-4 rows max)

## 🎯 Recommendations
- 3 prioritized actions (1 line each: High/Medium/Low priority)

## 📝 Conclusion
2-3 sentences only. End here, nothing after this."""
            else:
                prompt = f"""{base_prompt}
Keep response SHORT (under 400 words). Use bullet points, not paragraphs.

## 💡 Top Opportunities
| Opportunity | Gap/Need | Potential | Priority |
(3-4 rows max)

## 🎯 Recommendations
- 3 prioritized actions (High/Medium/Low)

## 📝 Conclusion
2-3 sentences only. End here, nothing after this."""
        
        elif research_type == 'threat':
            has_specific_competitors = additional_context and ('competitors' in additional_context or 'competitor' in additional_context)

            if has_specific_competitors:
                prompt = f"""{base_prompt}
Keep response SHORT (under 400 words). Use bullet points, not paragraphs.

## ⚠️ Threats from Competitors
For each competitor: 2-3 threats they pose (bullet points only).

## 📊 Threat Assessment
| Threat | Severity | Probability | Mitigation |
(3-4 rows max)

## 🎯 Mitigation Actions
- 3 prioritized actions (1 line each)

## 📝 Conclusion
2-3 sentences only. End here, nothing after this."""
            else:
                prompt = f"""{base_prompt}
Keep response SHORT (under 400 words). Use bullet points, not paragraphs.

## ⚠️ Key Threats
| Threat | Severity | Probability | Impact |
(3-4 rows max)

## 🛡️ Mitigation Strategies
- 3 actions with expected impact (1 line each)

## 📝 Conclusion
2-3 sentences only. End here, nothing after this."""
        
        else:
            prompt = f"""{base_prompt}
Keep response SHORT (under 400 words). Use bullet points, not paragraphs.

## 🔍 Key Findings
- 3-4 key findings (1 line each)

## 💡 Opportunities & Threats
- 2 opportunities, 2 threats (1 line each)

## 🎯 Recommendations
1-3 actionable next steps (1 line each)

## 📝 Conclusion
2-3 sentences only. End here, nothing after this."""
        
        return prompt
    
    def _parse_research_response(self, research_type: str, response: str, 
                                 additional_context: Optional[Dict] = None) -> Dict:
        """
        Parse AI research response into structured findings
        
        Args:
            research_type (str): Type of research
            response (str): AI-generated research text
            additional_context (Dict): Additional context
            
        Returns:
            Dict: Structured findings
        """
        # Extract key information from response
        findings = {
            'raw_response': response,
            'research_type': research_type,
            'analyzed_at': datetime.now().isoformat()
        }
        
        # Use the full formatted response as insights (already includes all sections, conclusion, etc.)
        # Trim response to end at conclusion section to avoid duplicate content after conclusion
        insights = response
        
        # Find the conclusion section and ensure we stop there (or shortly after if conclusion content exists)
        conclusion_markers = [
            '## 📝 CONCLUSION & SUMMARY',
            '## 📝 CONCLUSION',
            '## CONCLUSION & SUMMARY',
            '## CONCLUSION'
        ]
        
        for marker in conclusion_markers:
            if marker in insights:
                # Find the position of the conclusion marker
                conclusion_index = insights.find(marker)
                if conclusion_index != -1:
                    # Extract everything from start to conclusion section
                    # Then look for where conclusion ends - it should be the last section
                    conclusion_section = insights[conclusion_index:]
                    lines = conclusion_section.split('\n')
                    
                    # Find where conclusion content ends (look for next major section or excessive content)
                    # Conclusion should typically be 2-4 paragraphs, so limit to ~1000 chars after marker
                    # or until we hit another ## section (not ###)
                    end_index = len(conclusion_section)
                    
                    for i, line in enumerate(lines):
                        # Skip the conclusion header and a few lines after it
                        if i > 10:
                            line_stripped = line.strip()
                            # If we hit another major section header, stop there
                            if line_stripped.startswith('## ') and not line_stripped.startswith('### '):
                                end_index = len('\n'.join(lines[:i]))
                                break
                            # If we've gone too far (more than ~1500 chars), stop
                            if len('\n'.join(lines[:i])) > 1500:
                                end_index = len('\n'.join(lines[:i-5]))  # Back up a few lines
                                break
                    
                    # Trim to conclusion only
                    insights = insights[:conclusion_index] + conclusion_section[:end_index].rstrip()
                    break
        
        # Return empty arrays for backwards compatibility, but these won't be displayed
        # since the frontend uses the insights field which contains the full formatted response
        opportunities = []
        risks = []
        recommendations = []
        
        return {
            'findings': findings,
            'insights': insights,
            'opportunities': opportunities[:10],  # Limit to top 10
            'risks': risks[:10],  # Limit to top 10
            'recommendations': recommendations[:10],  # Limit to top 10
            'source_urls': []  # Can be populated if we add web scraping/API integration
        }
    
    def research_market_trends(self, topic: str, user_id: int, 
                              industry: Optional[str] = None) -> Dict:
        """
        Research market trends for a specific topic
        
        Args:
            topic (str): Topic to research (e.g., "AI marketing tools", "e-commerce trends")
            user_id (int): User ID
            industry (str): Optional industry context
            
        Returns:
            Dict: Market trend research findings
        """
        context = {}
        if industry:
            context['industry'] = industry
        
        return self.process('market_trend', topic, user_id, context)
    
    def analyze_competitors(self, topic: str, user_id: int, 
                           competitor_names: Optional[List[str]] = None) -> Dict:
        """
        Analyze competitors for a specific topic/market
        
        Args:
            topic (str): Market/product category to analyze
            user_id (int): User ID
            competitor_names (List[str]): Optional list of specific competitors
            
        Returns:
            Dict: Competitive analysis findings
        """
        context = {}
        if competitor_names:
            context['competitors'] = competitor_names
        
        return self.process('competitor', topic, user_id, context)
    
    def analyze_customer_behavior(self, topic: str, user_id: int,
                                 customer_segments: Optional[List[str]] = None) -> Dict:
        """
        Analyze customer behavior patterns
        
        Args:
            topic (str): Behavior topic (e.g., "purchasing behavior", "product preferences")
            user_id (int): User ID
            customer_segments (List[str]): Optional customer segments
            
        Returns:
            Dict: Customer behavior analysis findings
        """
        context = {}
        if customer_segments:
            context['customer_segments'] = customer_segments
        
        return self.process('customer_behavior', topic, user_id, context)
    
    def identify_opportunities(self, topic: str, user_id: int,
                              market_context: Optional[Dict] = None) -> Dict:
        """
        Identify market opportunities
        
        Args:
            topic (str): Opportunity area to explore
            user_id (int): User ID
            market_context (Dict): Optional market context (industry, region, etc.)
            
        Returns:
            Dict: Opportunity analysis findings
        """
        return self.process('opportunity', topic, user_id, market_context)
    
    def identify_risks(self, topic: str, user_id: int,
                      market_context: Optional[Dict] = None) -> Dict:
        """
        Identify market risks and threats
        
        Args:
            topic (str): Risk area to analyze
            user_id (int): User ID
            market_context (Dict): Optional market context
            
        Returns:
            Dict: Risk analysis findings
        """
        return self.process('threat', topic, user_id, market_context)

