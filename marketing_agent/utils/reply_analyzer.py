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

        combined_lower = f"{reply_subject or ''} {reply_content or ''}".lower()
        # First line / content before quoted "On ... wrote" (so "no" + quote still counts as "no")
        content_only = (reply_content or '').strip().lower()
        first_line = content_only.split('\n')[0].strip() if content_only else ''
        before_quote = content_only.split('on ')[0].strip() if ' on ' in content_only or content_only.startswith('on ') else content_only
        short_content = (first_line or before_quote or content_only).strip()

        # Early rule: short dismissive "no" / "not interested" = negative (not objection)
        if short_content in ('no', 'no.', 'nope', 'nah') or short_content in ('not interested', 'no thanks', 'no thank you'):
            return {
                'interest_level': 'negative',
                'analysis': 'Short dismissive reply (e.g. "no", "not interested"). Classified as Not Interested.',
                'confidence': 92
            }

        # Early rule: "eager to meet" / "egar to meet" (typo) = positive (warm interest), NOT negative
        if any(phrase in combined_lower for phrase in [
            'eager to meet', 'egar to meet', 'eager to meet you', 'egar to meet you',
            'looking forward to meet', 'looking forward to meeting'
        ]) and not any(phrase in combined_lower for phrase in ["dont send", "don't send", "unsubscribe"]):
            return {
                'interest_level': 'positive',
                'analysis': 'Reply expresses eagerness to meet (e.g. "eager to meet you"). Classified as Interested.',
                'confidence': 95
            }
        # Early rule: "send more/new information" / "more info" / "so i can analyze" / "further requirements" = requested_info (wants details)
        if any(phrase in combined_lower for phrase in [
            'send more information', 'send more info', 'send new information', 'send new info',
            'more information', 'more info', 'need more information', 'need more info',
            'awesome send more information', 'send more information now',
            'good send new information', 'send new information so that',
            'so that i can analyze', 'so that i can analyse', 'so i can analyze', 'so i can analyse',
            'information so that i can analyze', 'information so i can analyze',
            'send me further requirements', 'send further requirements', 'further requirements',
            'send me the requirements', 'send the requirements', 'send me requirements',
            'share the requirements', 'share further requirements', 'share me the requirements',
            'send me further details', 'send further details', 'further details',
            'send me the details', 'send the details', 'send me details',
            'share the details', 'share further details', 'share me the details'
        ]) and not any(phrase in combined_lower for phrase in ["dont send", "don't send", "unsubscribe"]):
            return {
                'interest_level': 'requested_info',
                'analysis': 'Reply asks for more/new information or requirements (e.g. "send new information", "send me further requirements"). Classified as Requested More Information.',
                'confidence': 95
            }
        # Early rule: short positive agreement = positive (e.g. "yes thanks", "yes", "thanks")
        if short_content in (
            'yes', 'yes.', 'yes thanks', 'yes thank you', 'thanks', 'thank you', 'sure', 'ok', 'okay',
            'sounds good', 'great thanks', 'perfect thanks', 'ok thanks', 'okay thanks'
        ) and not any(phrase in combined_lower for phrase in ["dont send", "don't send", "unsubscribe", "not interested", "no thanks"]):
            return {
                'interest_level': 'positive',
                'analysis': 'Short positive agreement (e.g. "yes thanks"). Classified as Interested.',
                'confidence': 92
            }
        # Early rule: "lets meet" / "meet again" / "thanks lets meet" = positive (interested), NOT requested_info
        if any(phrase in combined_lower for phrase in [
            "lets meet", "let's meet", "let us meet", "meet again", "lets meet again", "let's meet again",
            "thanks lets meet", "thank you lets meet", "awesome thanks lets meet", "sounds good lets meet"
        ]) and not any(phrase in combined_lower for phrase in ["dont send", "don't send", "unsubscribe", "not interested"]):
            return {
                'interest_level': 'positive',
                'analysis': 'Reply agrees to meet or meet again (e.g. "awesome thanks lets meet again"). Classified as Interested.',
                'confidence': 95
            }

        # Early rule: unsubscribe / stop sending = unsubscribe (never "not interested")
        if any(phrase in combined_lower for phrase in [
            "don't send again", "dont send again", "do not send again", "stop sending", "stop sending me",
            "unsubscribe", "remove me", "stop emailing", "opt out", "don't email me", "remove from list"
        ]):
            return {
                'interest_level': 'unsubscribe',
                'analysis': 'Reply asks to stop receiving emails (e.g. "dont send again", "unsubscribe"). Classified as Unsubscribe Request.',
                'confidence': 95
            }

        # Early rule: objection / "don't think it can be done" or "not the correct way" / "do in some other way" = objection (not "not interested")
        if any(phrase in combined_lower for phrase in [
            "don't think it can be done", "dont think it can be done", "can't be done like this",
            "cant be done like this", "can not be done", "don't think this can work", "dont think this can work"
        ]):
            return {
                'interest_level': 'objection',
                'analysis': 'Reply expresses doubt or objection about the approach (e.g. "I dont think it can be done like this"). Classified as Has Objection/Concern.',
                'confidence': 90
            }
        # Early rule: polite brush-off / "we'll keep you in mind" / busy = negative (not interested)
        if any(phrase in combined_lower for phrase in [
            "we'll keep you in mind", "we will keep you in mind", "keep you in mind",
            "we're quite busy", "we are quite busy", "haven't allocated time", "havent allocated time",
            "priorities change", "checking back in a few months", "check back in a few months",
            "passed this along", "passed along to our team", "we're all set for now", "we are all set for now",
            "not looking at the moment", "not evaluating new tools", "stick with what we have",
            "budget and bandwidth are tight", "not planning to switch", "decided to stick with"
        ]):
            return {
                'interest_level': 'negative',
                'analysis': 'Polite brush-off or "not right now" (e.g. we\'ll keep you in mind, we\'re quite busy, stick with what we have). Classified as Not Interested.',
                'confidence': 90
            }

        # Early rule: asking for pricing / integration / timeline before committing = requested_info
        if any(phrase in combined_lower for phrase in [
            'ballpark pricing', 'pricing and whether', 'different tiers', 'integrate with',
            'implementation timeline', 'before we take this further', 'before we take it further',
            'need to understand a few things', 'typical implementation'
        ]) and not any(phrase in combined_lower for phrase in ["dont send", "don't send", "unsubscribe", "not interested", "no thanks"]):
            return {
                'interest_level': 'requested_info',
                'analysis': 'Reply asks for pricing, integration, or timeline before committing. Classified as Requested More Information.',
                'confidence': 92
            }

        # Early rule: "not the correct way" / "do in some other way" = objection (feedback about approach, willing to engage differently)
        if any(phrase in combined_lower for phrase in [
            "not the correct way", "not the right way", "isn't the correct way", "isnt the correct way",
            "do in some other way", "do it in some other way", "in some other way", "some other way",
            "do it another way", "try another way", "different way"
        ]) and not any(phrase in combined_lower for phrase in ["unsubscribe", "stop sending", "don't send", "dont send"]):
            return {
                'interest_level': 'objection',
                'analysis': 'Reply suggests the approach is wrong or should be done differently (e.g. "not the correct way", "do in some other way"). Classified as Has Objection/Concern.',
                'confidence': 90
            }
        # Early rule: "not right" / "should be different" = objection (feedback about approach, not flat rejection)
        if any(phrase in combined_lower for phrase in [
            "not right", "is not right", "it's not right", "its not right",
            "should be different", "should be a little different", "ought to be different",
            "doing this way", "this way it should", "wrong way"
        ]) and not any(phrase in combined_lower for phrase in ["unsubscribe", "stop sending", "don't send", "dont send"]):
            return {
                'interest_level': 'objection',
                'analysis': 'Reply expresses that the approach is not right or should be different (feedback/concern about method). Classified as Has Objection/Concern.',
                'confidence': 88
            }

        # Early rule: obvious "clarification / make it clear" = requested_info (never call AI for these)
        if any(phrase in combined_lower for phrase in [
            'make it more clear', 'make it clearer', 'make it mroe clear', 'make it clear',
            'please clarify', 'could you clarify', 'can you clarify', 'can you explain',
            'clarify please', 'more clear please'
        ]):
            return {
                'interest_level': 'requested_info',
                'analysis': 'Reply asks for clarification or clearer information (e.g. "make it more clear", "please clarify"). Classified as Requested More Information.',
                'confidence': 95
            }
        # Flexible: "make it" + "clear" or "clarif" (catches typos like "mroe clear")
        if 'make it' in combined_lower and ('clear' in combined_lower or 'clarif' in combined_lower):
            return {
                'interest_level': 'requested_info',
                'analysis': 'Reply asks for clarification ("make it clear" / "make it clearer" or similar). Classified as Requested More Information.',
                'confidence': 90
            }

        # Build analysis prompt
        prompt = f"""Analyze this email reply from a lead in a marketing campaign.

CAMPAIGN: {campaign_name or 'Marketing Campaign'}

REPLY SUBJECT: {reply_subject or '(No subject)'}

REPLY CONTENT:
{reply_content or '(No content)'}

TASK:
Determine if this reply indicates the lead is INTERESTED (positive) or NOT INTERESTED (negative).
You MUST choose exactly ONE of the six categories below. Use the definitions and examples to pick the best match.

CLASSIFICATION OPTIONS (use these exact labels):
1. "positive" - Lead is INTERESTED:
   - Expresses interest, asks questions, requests more information
   - Agrees to a meeting, call, or demo (include brief agreement: "yes", "yes okay", "sure", "okay", "sounds good", "let's do it")
   - Shows enthusiasm, excitement, or curiosity
   - Asks about pricing, features, or next steps
   - Forward-looking or warm sign-off: "see you soon", "thank you and see you soon", "looking forward to", "talk soon", "thanks, let's connect"
   - Positive language: "interested", "sounds good", "I'd like to", "tell me more"
   - When in doubt between neutral and positive for short replies, prefer "positive" if there is any agreement or warmth (e.g. "Yes okay" = positive; "Thank you and see you soon!" = positive).
   - CRITICAL: Any reply that contains BOTH a thank-you ("thank you", "thanks") AND a forward-looking phrase ("see you soon", "talk soon", "looking forward", "catch you later") MUST be "positive", never "neutral".
   - CRITICAL: "Thanks and same to you!" / "Thank you, same to you" = positive (warm reciprocation of goodwill). Do NOT classify as neutral.
   - "We will update you soon" / "will update you" / "get back to you" = still engaged, prefer "positive" (they are staying in the conversation).

2. "negative" - Lead is NOT INTERESTED:
   - Explicitly declines or says "no thanks"
   - Negative language: "not interested", "don't contact me", "spam"
   - Complaints or criticism
   - Very short dismissive replies: "no", "not interested" (without agreement or warmth)

3. "neutral" - NEUTRAL/Acknowledgment only (no clear interest or disinterest):
   - Purely informational: "received", "got it", "noted"
   - Vague or minimal: "ok" alone with no other context, "thanks" with no forward-looking or agreeing tone
   - Do NOT use neutral for: "yes okay", "thank you and see you soon", "sure", "sounds good" — these are positive.
   - Do NOT use neutral for: "make it more clear", "please clarify", "can you explain" — these are requested_info.

4. "requested_info" - REQUESTED MORE INFORMATION:
   - Asks specific questions about features, pricing, capabilities
   - Wants detailed information, case studies, examples, or clarification
   - Requests documentation, demos, samples, or REQUIREMENTS (e.g. "send me further requirements", "send me the requirements")
   - Asks to make something clearer or to clarify: "make it more clear", "make it clearer", "please clarify", "could you clarify", "can you explain"
   - Language: "tell me more about", "what are the features", "how much does it cost", "can you send", "send me requirements", "further requirements"
   - CRITICAL: "make it more clear please" / "please clarify" = requested_info (they want clearer info), NOT neutral.
   - CRITICAL: If the reply is PRIMARILY asking for more information, details, or requirements (e.g. "Send me further requirements", "Send further details"), use "requested_info", NOT "positive".

5. "objection" - HAS OBJECTION/CONCERN:
   - Raises concerns, objections, or doubts about the approach or feasibility
   - "I don't think it can be done like this" / "dont think it can be done" = objection (they have a concern about how it works), NOT "negative"
   - Questions about value, ROI, or fit
   - Mentions competitors or alternatives
   - Language: "but", "however", "concerned about", "worried", "not sure if", "don't think it can"

6. "unsubscribe" - UNSUBSCRIBE REQUEST:
   - Explicit unsubscribe requests: "unsubscribe", "remove me", "stop emailing", "don't send again", "dont send again"
   - Opt-out language: "remove from list", "don't email me", "opt out", "stop sending"
   - CRITICAL: "dont send again" / "don't send again" = unsubscribe (they want to stop receiving emails), NOT just "negative".

Return your analysis in this EXACT JSON format (no markdown, just JSON):
{{
    "interest_level": "positive" or "negative" or "neutral" or "requested_info" or "objection" or "unsubscribe",
    "analysis": "Detailed explanation of why you classified it this way, including key phrases or indicators",
    "confidence": 0-100 (how confident you are in the classification)
}}

Be specific and cite the actual words/phrases from the reply that led to your decision.

REMINDER: "Thank you and see you soon!" = positive. "Thanks and same to you!" = positive. "We will update you soon" = positive. "Make it more clear please" / "please clarify" = requested_info (not neutral)."""
        
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
            
            # Post-process: override AI when reply clearly matches our rules (AI sometimes returns neutral for these)
            combined = f"{reply_subject or ''} {reply_content or ''}".lower()
            overridden = self._apply_rule_overrides(combined, interest_level)
            if overridden is not None:
                interest_level = overridden
                logger.info(f"Reply analyzer: overridden to '{interest_level}' based on rule match")
            
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
    
    def _apply_rule_overrides(self, combined_text_lower: str, ai_level: str):
        """
        Override AI result when reply clearly matches rules (avoids AI returning neutral for clear positives).
        Returns new interest_level or None if no override.
        """
        # Clear positive: thank-you + forward-looking
        has_thanks = 'thank you' in combined_text_lower or 'thanks' in combined_text_lower
        has_forward = any(
            p in combined_text_lower for p in
            ['see you soon', 'talk soon', 'looking forward', 'catch you later', 'see you', 'speak soon']
        )
        if has_thanks and has_forward:
            return 'positive'
        # Clear positive: thank-you + warm reciprocation ("same to you")
        if has_thanks and 'same to you' in combined_text_lower:
            return 'positive'
        # Clear positive: will get back / update you
        if any(p in combined_text_lower for p in ['will update you', 'update you soon', 'get back to you', 'we will update']):
            return 'positive'
        # Short agreement
        if any(p in combined_text_lower for p in ['yes okay', 'yes ok', 'sure', 'sounds good', 'lets have a meeting', "let's have a meeting"]):
            return 'positive'
        # Clear unsubscribe: stop sending / don't send again (override AI if it returned "negative")
        if any(p in combined_text_lower for p in ["don't send again", "dont send again", "do not send again", "stop sending", "stop sending me"]):
            return 'unsubscribe'
        # Clear requested_info: asking for pricing, details, clarification, requirements (override AI if it returned neutral/positive)
        if any(p in combined_text_lower for p in [
            'how much', 'what is the price', 'what is the cost', 'can you send me', 'send me more', 'send me details',
            'more details', 'pricing information', 'more information about', 'tell me more about', 'what are the features',
            'make it more clear', 'make it clearer', 'make it mroe clear', 'make it clear',
            'please clarify', 'could you clarify', 'can you clarify', 'can you explain',
            'send me further requirements', 'send further requirements', 'further requirements',
            'send me the requirements', 'send me requirements', 'share the requirements',
            'send me further details', 'send further details', 'further details',
            'send me the details', 'send me details', 'share the details'
        ]):
            return 'requested_info'
        if 'make it' in combined_text_lower and ('clear' in combined_text_lower or 'clarif' in combined_text_lower):
            return 'requested_info'
        # Clear objection: concern, worry, doubt, "don't think it can be done", "not right / should be different" (override AI if it returned neutral/negative)
        if any(p in combined_text_lower for p in [
            'concerned about', 'worried that', 'worried about', 'not sure if this', 'my concern', 'have a concern',
            'however the', 'however i', 'but i\'m not sure', 'but im not sure', 'have doubts', 'not convinced',
            "don't think it can be done", "dont think it can be done", "can't be done like this", "cant be done like this",
            "don't think this can work", "dont think this can work",
            'not right', 'is not right', "it's not right", "its not right",
            'should be different', 'should be a little different', 'doing this way', 'wrong way'
        ]):
            return 'objection'
        return None
    
    def _fallback_analysis(self, reply_subject: str, reply_content: str) -> Dict:
        """Fallback keyword-based analysis if AI fails"""
        combined_text = f"{reply_subject} {reply_content}".lower()
        
        # Check for unsubscribe first (highest priority)
        unsubscribe_keywords = [
            'unsubscribe', 'remove me', 'stop emailing', 'opt out', 'remove from list', "don't email",
            "don't send again", 'dont send again', 'do not send again', 'stop sending', 'stop sending me'
        ]
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
        
        # Check for info requests (including clarification; include typo "mroe"; requirements)
        info_keywords = [
            'tell me more', 'more information', 'details about', 'what are', 'how much', 'pricing', 'features', 'can you send',
            'make it more clear', 'make it clearer', 'make it mroe clear', 'make it clear',
            'please clarify', 'could you clarify', 'can you clarify', 'can you explain',
            'send me further requirements', 'further requirements', 'send me requirements', 'send the requirements',
            'send me further details', 'send further details', 'further details', 'send me details', 'send the details'
        ]
        if 'make it' in combined_text and ('clear' in combined_text or 'clarif' in combined_text):
            return {'interest_level': 'requested_info', 'analysis': 'Asks for clarification.', 'confidence': 85}
        if any(keyword in combined_text for keyword in info_keywords):
            return {
                'interest_level': 'requested_info',
                'analysis': 'Detected information request keywords',
                'confidence': 75
            }
        
        # Check positive/negative (include short agreement and warm sign-offs)
        positive_keywords = [
            'interested', 'yes', 'sounds good', 'schedule', 'meeting', 'call', 'demo', 'like to', 'would like',
            'yes okay', 'yes ok', 'sure', 'okay', 'see you soon', 'talk soon', 'looking forward', 'thank you and',
            'thanks and', 'same to you', 'let\'s do it', 'let\'s connect', 'sounds great', 'perfect',
            'will update you', 'update you soon', 'get back to you'
        ]
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

