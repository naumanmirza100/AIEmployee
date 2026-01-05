"""
AI Reply Analyzer
Analyzes email replies to determine if the lead is interested (positive) or not interested (negative)
"""
import logging
from typing import Dict, Optional
from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent

logger = logging.getLogger(__name__)


class ReplyAnalyzer(MarketingBaseAgent):
    """AI agent for analyzing email reply sentiment and interest level"""
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are an expert email reply analyzer for marketing campaigns. 
Your job is to analyze email replies from leads and determine:
1. Whether the reply is POSITIVE (lead is interested) or NEGATIVE (lead is not interested)
2. The sentiment of the reply
3. Key indicators of interest or disinterest

Return your analysis in a structured format."""
    
    def analyze_reply(self, reply_subject: str, reply_content: str, campaign_name: str = '') -> Dict:
        """
        Analyze an email reply to determine if the lead is interested or not.
        
        Args:
            reply_subject: Subject line of the reply
            reply_content: Full content of the reply email
            campaign_name: Name of the campaign (for context)
            
        Returns:
            Dict with:
                - interest_level: 'positive', 'negative', or 'neutral'
                - analysis: Detailed explanation of the analysis
                - confidence: Confidence score (0-100)
        """
        if not reply_content and not reply_subject:
            return {
                'interest_level': 'neutral',
                'analysis': 'No reply content provided for analysis.',
                'confidence': 0
            }
        
        # Build analysis prompt
        prompt = f"""Analyze this email reply from a lead in a marketing campaign.

CAMPAIGN: {campaign_name or 'Marketing Campaign'}

REPLY SUBJECT: {reply_subject or '(No subject)'}

REPLY CONTENT:
{reply_content or '(No content)'}

TASK:
Determine if this reply indicates the lead is INTERESTED (positive) or NOT INTERESTED (negative).

CLASSIFICATION OPTIONS:
1. "positive" - Lead is INTERESTED:
   - Expresses interest, asks questions, requests more information
   - Agrees to a meeting, call, or demo
   - Shows enthusiasm, excitement, or curiosity
   - Asks about pricing, features, or next steps
   - Positive language: "interested", "sounds good", "let's do it", "I'd like to", "tell me more"

2. "negative" - Lead is NOT INTERESTED:
   - Explicitly declines or says "no thanks"
   - Negative language: "not interested", "don't contact me", "spam"
   - Complaints or criticism
   - Very short dismissive replies: "no", "not interested"

3. "neutral" - NEUTRAL/Acknowledgment:
   - Simple acknowledgments: "thanks", "received", "ok"
   - Questions that don't show clear interest or disinterest
   - Requests for clarification only

4. "requested_info" - REQUESTED MORE INFORMATION:
   - Asks specific questions about features, pricing, capabilities
   - Wants detailed information, case studies, examples
   - Requests documentation, demos, or samples
   - Language: "tell me more about", "what are the features", "how much does it cost", "can you send"

5. "objection" - HAS OBJECTION/CONCERN:
   - Raises concerns, objections, or doubts
   - Questions about value, ROI, or fit
   - Mentions competitors or alternatives
   - Language: "but", "however", "concerned about", "worried", "not sure if"

6. "unsubscribe" - UNSUBSCRIBE REQUEST:
   - Explicit unsubscribe requests: "unsubscribe", "remove me", "stop emailing"
   - Opt-out language: "remove from list", "don't email me", "opt out"

Return your analysis in this EXACT JSON format (no markdown, just JSON):
{{
    "interest_level": "positive" or "negative" or "neutral" or "requested_info" or "objection" or "unsubscribe",
    "analysis": "Detailed explanation of why you classified it this way, including key phrases or indicators",
    "confidence": 0-100 (how confident you are in the classification)
}}

Be specific and cite the actual words/phrases from the reply that led to your decision."""
        
        try:
            # Use Groq for analysis (faster and cheaper)
            response = self._call_groq_qa(
                prompt,
                self.system_prompt,
                temperature=0.3,  # Lower temperature for more consistent analysis
                max_tokens=500
            )
            
            # Parse JSON response
            import json
            import re
            
            # Try to extract JSON from response (may have markdown formatting)
            json_match = re.search(r'\{[^{}]*"interest_level"[^{}]*\}', response, re.DOTALL)
            if json_match:
                analysis_data = json.loads(json_match.group())
            else:
                # Try to parse entire response as JSON
                analysis_data = json.loads(response.strip())
            
            # Validate and return
            interest_level = analysis_data.get('interest_level', 'neutral').lower()
            valid_levels = ['positive', 'negative', 'neutral', 'requested_info', 'objection', 'unsubscribe']
            if interest_level not in valid_levels:
                # Fallback: map to closest valid level
                if 'unsubscribe' in interest_level or 'remove' in interest_level or 'stop' in interest_level:
                    interest_level = 'unsubscribe'
                elif 'objection' in interest_level or 'concern' in interest_level or 'worried' in interest_level:
                    interest_level = 'objection'
                elif 'info' in interest_level or 'more' in interest_level or 'details' in interest_level:
                    interest_level = 'requested_info'
                elif interest_level in ['positive', 'interested', 'yes']:
                    interest_level = 'positive'
                elif interest_level in ['negative', 'not interested', 'no']:
                    interest_level = 'negative'
                else:
                    interest_level = 'neutral'
            
            return {
                'interest_level': interest_level,
                'analysis': analysis_data.get('analysis', 'Analysis completed.'),
                'confidence': int(analysis_data.get('confidence', 50))
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing AI analysis JSON: {str(e)}. Response: {response[:200]}")
            # Fallback: try to determine from keywords
            return self._fallback_analysis(reply_subject, reply_content)
        except Exception as e:
            logger.error(f"Error analyzing reply: {str(e)}")
            return self._fallback_analysis(reply_subject, reply_content)
    
    def _fallback_analysis(self, reply_subject: str, reply_content: str) -> Dict:
        """Fallback keyword-based analysis if AI fails"""
        combined_text = f"{reply_subject} {reply_content}".lower()
        
        # Check for unsubscribe first (highest priority)
        unsubscribe_keywords = ['unsubscribe', 'remove me', 'stop emailing', 'opt out', 'remove from list', 'don\'t email']
        if any(keyword in combined_text for keyword in unsubscribe_keywords):
            return {
                'interest_level': 'unsubscribe',
                'analysis': 'Detected unsubscribe request keywords',
                'confidence': 85
            }
        
        # Check for objections/concerns
        objection_keywords = ['concerned', 'worried', 'not sure', 'but', 'however', 'objection', 'doubt', 'question about']
        if any(keyword in combined_text for keyword in objection_keywords):
            return {
                'interest_level': 'objection',
                'analysis': 'Detected objection or concern keywords',
                'confidence': 70
            }
        
        # Check for info requests
        info_keywords = ['tell me more', 'more information', 'details about', 'what are', 'how much', 'pricing', 'features', 'can you send']
        if any(keyword in combined_text for keyword in info_keywords):
            return {
                'interest_level': 'requested_info',
                'analysis': 'Detected information request keywords',
                'confidence': 75
            }
        
        # Check positive/negative
        positive_keywords = ['interested', 'yes', 'sounds good', 'schedule', 'meeting', 'call', 'demo', 'like to', 'would like']
        negative_keywords = ['not interested', 'no thanks', 'don\'t contact', 'spam', 'delete']
        
        positive_count = sum(1 for keyword in positive_keywords if keyword in combined_text)
        negative_count = sum(1 for keyword in negative_keywords if keyword in combined_text)
        
        if negative_count > positive_count:
            interest_level = 'negative'
            analysis = f"Detected {negative_count} negative indicators"
        elif positive_count > negative_count:
            interest_level = 'positive'
            analysis = f"Detected {positive_count} positive indicators"
        else:
            interest_level = 'neutral'
            analysis = "Could not determine clear interest level from keywords."
        
        return {
            'interest_level': interest_level,
            'analysis': analysis,
            'confidence': 60  # Lower confidence for fallback
        }

