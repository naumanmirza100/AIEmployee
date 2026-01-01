"""
Intent Detection for Frontline AI Customer Support
Simple keyword-based intent detection (can be upgraded to ML later)
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class IntentDetector:
    """
    Detects user intent from messages.
    Uses keyword-based detection (simple and reliable).
    Can be upgraded to ML-based detection later without breaking existing functionality.
    """
    
    def __init__(self):
        """Initialize intent detector"""
        self.intent_keywords = {
            'answer_question': [
                'how', 'what', 'why', 'when', 'where', 'who', 'explain', 'tell me',
                'question', 'help', 'information', 'know', 'understand'
            ],
            'create_ticket': [
                'ticket', 'issue', 'problem', 'bug', 'error', 'broken', 'not working',
                'report', 'complain', 'support', 'help me', 'fix'
            ],
            'get_tickets': [
                'my tickets', 'open tickets', 'ticket status', 'list tickets',
                'show tickets', 'tickets', 'my issues'
            ],
            'get_notifications': [
                'notifications', 'alerts', 'messages', 'updates', 'reminders',
                'show notifications', 'my notifications'
            ],
            'check_notifications': [
                'check notifications', 'send notifications', 'monitor'
            ],
            'execute_workflow': [
                'workflow', 'sop', 'procedure', 'process', 'run workflow',
                'execute', 'follow steps'
            ],
            'schedule_meeting': [
                'schedule', 'meeting', 'call', 'appointment', 'book',
                'set up meeting', 'arrange call'
            ],
            'get_documents': [
                'documents', 'files', 'policies', 'manuals', 'show documents',
                'get documents', 'download'
            ],
            'get_analytics': [
                'analytics', 'dashboard', 'statistics', 'metrics', 'report',
                'insights', 'performance', 'show analytics'
            ]
        }
    
    def detect_intent(self, message: str) -> Dict:
        """
        Detect intent from user message.
        
        Args:
            message: User message
            
        Returns:
            Dictionary with detected intent and confidence
        """
        message_lower = message.lower().strip()
        
        if not message_lower:
            return {
                'intent': 'answer_question',
                'confidence': 0.5,
                'message': 'Please provide more details.'
            }
        
        # Score each intent based on keyword matches
        intent_scores = {}
        for intent, keywords in self.intent_keywords.items():
            score = 0
            matches = []
            for keyword in keywords:
                if keyword in message_lower:
                    score += 1
                    matches.append(keyword)
            intent_scores[intent] = {
                'score': score,
                'matches': matches
            }
        
        # Find intent with highest score
        if not intent_scores or max(s['score'] for s in intent_scores.values()) == 0:
            # Default to answer_question if no matches
            return {
                'intent': 'answer_question',
                'confidence': 0.5,
                'message': message
            }
        
        best_intent = max(intent_scores.items(), key=lambda x: x[1]['score'])
        intent_name = best_intent[0]
        intent_data = best_intent[1]
        
        # Calculate confidence (simple: based on number of matches)
        max_possible_score = len(self.intent_keywords[intent_name])
        confidence = min(intent_data['score'] / max(max_possible_score, 1), 1.0)
        
        logger.info(f"Intent detected: {intent_name} (confidence: {confidence:.2f}, matches: {intent_data['matches']})")
        
        return {
            'intent': intent_name,
            'confidence': confidence,
            'matches': intent_data['matches'],
            'message': message
        }

