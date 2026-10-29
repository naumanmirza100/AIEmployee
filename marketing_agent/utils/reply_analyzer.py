"""
AI Reply Analyzer
Analyzes email replies to determine if the lead is interested (positive) or not interested (negative)
"""
import json
import logging
import re
from typing import Dict, Optional
from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent

logger = logging.getLogger(__name__)

# Markers where the quoted original email begins in a reply body (Gmail, Outlook,
# Apple Mail, etc.). Everything from the first marker onward is the OLD thread, not
# what the lead just wrote.
_QUOTE_MARKERS = [
    r'\bon\s.+\bwrote:',                 # "On Mon, 20 Jul 2026 at 21:54, <x> wrote:"
    r'-{2,}\s*original message\s*-{2,}',  # "----- Original Message -----"
    r'^_{5,}',                            # "________" separator line
    r'^from:\s',                          # Outlook "From: ..." header block
    r'^sent:\s',
]
_QUOTE_RE = re.compile('|'.join(_QUOTE_MARKERS), re.IGNORECASE | re.MULTILINE)


def strip_quoted_thread(text: str) -> str:
    """Return only the NEW reply text — everything before the quoted original.

    Rule-based classification (e.g. "dont send again" = unsubscribe) must look at
    what the lead actually wrote, NOT the quoted history. Without this, one reply's
    phrase leaks into another reply on the same thread (e.g. a "Sure lets discuss"
    reply was misread as Unsubscribe because the quoted thread contained an earlier
    "dont send again"). Also drops leading '>' quote markers per line.
    """
    if not text:
        return ''
    m = _QUOTE_RE.search(text)
    head = text[:m.start()] if m else text
    # Drop any residual quoted lines (lines starting with '>').
    lines = [ln for ln in head.splitlines() if not ln.lstrip().startswith('>')]
    return '\n'.join(lines).strip()


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
    
    def analyze_reply(self, reply_subject: str, reply_content: str, campaign_name: str = '', company_id=None) -> Dict:
        """
        Analyze an email reply to determine if the lead is interested or not.

        Args:
            reply_subject: Subject line of the reply
            reply_content: Full content of the reply email
            campaign_name: Name of the campaign (for context)
            company_id: Company the reply belongs to. Required for the AI (Groq)
                path — the platform key service resolves the LLM key from
                (company_id, agent_key_name). Without it, the AI call raises
                "No API key available" and we fall back to keyword rules only.

        Returns:
            Dict with:
                - interest_level: 'positive', 'negative', or 'neutral'
                - analysis: Detailed explanation of the analysis
                - confidence: Confidence score (0-100)
        """
        # Let the base agent resolve this company's managed LLM key.
        if company_id:
            self.company_id = company_id
            self.agent_key_name = 'marketing_agent'

        if not reply_content and not reply_subject:
            return {
                'interest_level': 'neutral',
                'analysis': 'No reply content provided for analysis.',
                'confidence': 0
            }

        # Use only the NEW reply text (strip the quoted original thread) for all
        # keyword/rule matching, so one reply's phrases don't leak into another.
        new_reply_only = strip_quoted_thread(reply_content or '')
        combined_lower = f"{reply_subject or ''} {new_reply_only}".lower()
        # The AI reads the reply. Keyword rules answered first and overrode it, and they read the company's own
        # subject line too ("Re: ... unsubscribe anytime"), so replies were filed wrongly and people were put on the
        # do-not-email list by mistake (CO-128). Only an explicit request to stop, in the reply's own words, is
        # taken as one whatever the AI says (_asks_to_stop); keywords alone are used only when the AI cannot be.

        # Build analysis prompt
        prompt = f"""Analyze this email reply from a lead in a marketing campaign.

CAMPAIGN: {campaign_name or 'Marketing Campaign'}

REPLY SUBJECT: {reply_subject or '(No subject)'}
(The subject usually repeats the company's own email's subject. Judge the reply by what the lead wrote below.)

REPLY CONTENT:
{new_reply_only or reply_content or '(No content)'}

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
            
            # Parse JSON response (json/re imported at module top so the
            # `except json.JSONDecodeError` below can never hit an unbound name).

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
            # Strip the quoted original email first — rule overrides must fire on
            # what the lead just wrote, not on quoted history from the thread.
            if interest_level != 'unsubscribe' and self._asks_to_stop(new_reply_only):
                interest_level = 'unsubscribe'
                logger.info("Reply analyzer: an explicit request to stop, taken as unsubscribe")
            
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
            # Note WHY the AI path was skipped so it shows in the reply's analysis
            # (not a silent drop to keywords). Token/quota exhaustion is the common
            # case — surface it plainly.
            from core.api_key_service import QuotaExhausted, NoKeyAvailable, NotSubscribed
            if isinstance(e, NotSubscribed):
                note = 'The Marketing agent is not active for this company, so the reply was analyzed with keyword rules instead.'
            elif isinstance(e, QuotaExhausted):
                note = 'AI tokens finished — analyzed with keyword rules instead. Top up the agent quota to re-enable AI analysis.'
            elif isinstance(e, NoKeyAvailable):
                note = 'No AI key available — analyzed with keyword rules instead. Assign an API key to enable AI analysis.'
            else:
                note = f'AI analysis unavailable ({e or "unknown error"}) — analyzed with keyword rules instead.'
            logger.warning(f"Reply analyzer falling back to keywords: {note}")
            result = self._fallback_analysis(reply_subject, reply_content)
            # Don't clutter every reply's analysis text with the reason — expose it
            # once via a flag + reason so the UI can show a single banner instead.
            result['ai_fallback'] = True
            result['ai_fallback_reason'] = note
            return result
    
    _STOP = re.compile(r"\b(unsubscribe|remove me|opt[- ]?out|stop (emailing|sending|contacting)( me| us)?|"
                       r"do(n['’]?t| not) (email|contact|send|message)( me| us)?)\b", re.IGNORECASE)

    def _asks_to_stop(self, new_reply_text: str) -> bool:
        """An explicit request to stop emailing, in the reply's own words (never its subject)."""
        return bool(self._STOP.search(new_reply_text or ''))

    def _apply_rule_overrides(self, combined_text_lower: str, ai_level: str):
        """Keyword rules, used only when the AI could not read the reply (_fallback_analysis)."""
        return self._keyword_level(combined_text_lower)

    def _keyword_level(self, combined_text_lower: str):
        """
        Override AI result when reply clearly matches rules (avoids AI returning neutral for clear positives).
        Returns new interest_level or None if no override.
        """
        # CHECK NEGATIVE/UNSUBSCRIBE FIRST — before any positive rule. A reply like
        # "dont send it again i deny from it" contains no positive words, but the
        # positive rules used to run first and a loose match could win. Opt-out
        # intent must always take priority over agreement phrases.
        # Match flexibly: "dont send again", "dont send it again", "do not send…" etc.
        if (
            re.search(r"\bdo(?:n['’]?t| not)\s+(?:send|email|contact|message)\b", combined_text_lower)
            or any(p in combined_text_lower for p in [
                "dont send", "don't send", "do not send", "stop sending", "stop sending me",
                "stop emailing", "unsubscribe", "remove me", "opt out", "opt-out",
                "remove from list", "dont email me", "don't email me", "dont contact me",
                "don't contact me", "i deny", "i decline", "leave me alone",
            ])                   # "not interested" is a no, not a request to stop emailing (CO-128)
        ):
            return 'unsubscribe'

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
        if (re.search(r'\bsure\b', combined_text_lower)        # a whole word: "ensure" and "measure" matched
                or any(p in combined_text_lower for p in ['yes okay', 'yes ok', 'sounds good', 'lets have a meeting', "let's have a meeting"])):
            return 'positive'
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
        """Fallback keyword-based analysis if AI fails."""
        # Strip the quoted original thread first — otherwise keyword counting runs
        # over the old email history and misclassifies (e.g. a "dont send it again"
        # reply was scored positive because quoted text contained positive words).
        new_reply_only = strip_quoted_thread(reply_content or '')
        combined_text = new_reply_only.lower()          # the lead's words, not the company's subject (CO-128)

        # Run the shared rule overrides first — they already handle opt-out/deny
        # intent flexibly ("dont send it again", "i deny", etc.). This keeps the
        # fallback consistent with the AI path's post-processing.
        forced = self._apply_rule_overrides(combined_text, 'neutral')
        if forced:
            return {'interest_level': forced, 'analysis': 'Matched a clear rule.', 'confidence': 85}

        # Check for unsubscribe first (highest priority)
        unsubscribe_keywords = [
            'unsubscribe', 'remove me', 'stop emailing', 'opt out', 'remove from list', "don't email",
            "don't send again", 'dont send again', 'do not send again', 'stop sending', 'stop sending me',
            'dont send it again', "don't send it again", 'i deny', 'i decline',
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

