"""
Ticket Classification Rules Engine
Enterprise-level rule-based classification for tickets
"""
import re
import logging
from typing import Tuple, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class TicketCategory(Enum):
    """Ticket categories"""
    TECHNICAL = "technical"
    BILLING = "billing"
    ACCOUNT = "account"
    FEATURE_REQUEST = "feature_request"
    BUG = "bug"
    OTHER = "other"


class TicketPriority(Enum):
    """Ticket priorities"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketClassificationRules:
    """
    Rule-based ticket classification engine.
    Uses pattern matching and keyword analysis to classify tickets.
    """
    
    # Category keywords and patterns
    CATEGORY_PATTERNS = {
        TicketCategory.TECHNICAL: [
            r'\b(technical|tech|system|server|database|api|integration|connection|error|bug|issue|problem|not working|broken|down)\b',
            r'\b(cannot|can\'t|unable|failed|failure|crash|freeze|slow|performance)\b',
            r'\b(login|log in|sign in|authentication|access|permission|credential)\b',
        ],
        TicketCategory.BILLING: [
            r'\b(billing|payment|invoice|charge|fee|cost|price|subscription|plan|renewal|refund|credit)\b',
            r'\b(pay|paid|payment method|card|credit card|debit|transaction)\b',
            r'\b(bill|invoice|receipt|statement|balance|amount|due)\b',
        ],
        TicketCategory.ACCOUNT: [
            r'\b(account|profile|user|username|email|password|reset|change|update|delete|deactivate)\b',
            r'\b(sign up|register|registration|verify|verification|activate|activation)\b',
            r'\b(settings|preferences|personal information|contact info)\b',
        ],
        TicketCategory.FEATURE_REQUEST: [
            r'\b(feature|request|suggest|suggestion|add|new|enhancement|improve|improvement|wish|want|need)\b',
            r'\b(can you|could you|would it be possible|it would be great)\b',
        ],
        TicketCategory.BUG: [
            r'\b(bug|defect|error|exception|crash|freeze|glitch|malfunction|broken|not working)\b',
            r'\b(wrong|incorrect|incorrectly|unexpected|unexpectedly|should be|shouldn\'t)\b',
        ],
    }
    
    # Priority keywords
    PRIORITY_KEYWORDS = {
        TicketPriority.URGENT: [
            'urgent', 'critical', 'emergency', 'asap', 'immediately', 'now',
            'down', 'outage', 'broken', 'cannot access', 'blocked', 'stuck'
        ],
        TicketPriority.HIGH: [
            'important', 'high priority', 'soon', 'quickly', 'issue', 'problem',
            'not working', 'error', 'failed', 'unable', 'cannot'
        ],
        TicketPriority.MEDIUM: [
            'question', 'help', 'how to', 'wondering', 'curious', 'information'
        ],
        TicketPriority.LOW: [
            'suggestion', 'feature', 'enhancement', 'improvement', 'nice to have'
        ],
    }
    
    # Auto-resolvable patterns (low complexity issues)
    AUTO_RESOLVABLE_PATTERNS = [
        {
            'pattern': r'\b(reset|forgot|forget)\s+(password|pwd|pass)\b',
            'category': TicketCategory.ACCOUNT,
            'priority': TicketPriority.MEDIUM,
            'auto_resolvable': True,
            'resolution_template': 'Password reset instructions have been sent to your registered email address. Please check your inbox and follow the instructions to reset your password.'
        },
        {
            'pattern': r'\b(payment|invoice|billing)\s+(status|status of|information|details)\b',
            'category': TicketCategory.BILLING,
            'priority': TicketPriority.LOW,
            'auto_resolvable': True,
            'resolution_template': 'Your payment status can be viewed in your account dashboard under the Billing section. All recent transactions are listed there with their current status.'
        },
        {
            'pattern': r'\b(how to|how do i|how can i|tutorial|guide|instructions)\b',
            'category': TicketCategory.TECHNICAL,
            'priority': TicketPriority.LOW,
            'auto_resolvable': True,
            'resolution_template': None  # Will be filled from knowledge base
        },
        {
            'pattern': r'\b(what is|what are|explain|definition|meaning)\b',
            'category': TicketCategory.OTHER,
            'priority': TicketPriority.LOW,
            'auto_resolvable': True,
            'resolution_template': None  # Will be filled from knowledge base
        },
    ]
    
    # Complex issue indicators (should be escalated)
    COMPLEX_INDICATORS = [
        r'\b(data loss|lost data|deleted|removed|missing|gone)\b',
        r'\b(security|breach|hacked|compromised|unauthorized|suspicious)\b',
        r'\b(legal|law|compliance|regulation|violation)\b',
        r'\b(money|refund|chargeback|dispute|fraud)\b',
        r'\b(critical|urgent|emergency|asap|immediately|now)\b',
        r'\b(cannot|unable|failed|broken|down|outage)\b',
    ]
    
    @classmethod
    def classify_ticket(cls, description: str, title: Optional[str] = None) -> Dict:
        """
        Classify a ticket based on description and title.
        
        Args:
            description: Ticket description text
            title: Optional ticket title
            
        Returns:
            Dictionary with category, priority, and classification metadata
        """
        if not description:
            return {
                'category': TicketCategory.OTHER.value,
                'priority': TicketPriority.LOW.value,
                'confidence': 0.0,
                'auto_resolvable': False,
                'should_escalate': False,
                'reasoning': 'Empty description'
            }
        
        text = f"{title} {description}".lower() if title else description.lower()
        
        # Check for auto-resolvable patterns first
        for pattern_config in cls.AUTO_RESOLVABLE_PATTERNS:
            if re.search(pattern_config['pattern'], text, re.IGNORECASE):
                logger.info(f"Matched auto-resolvable pattern: {pattern_config['pattern']}")
                return {
                    'category': pattern_config['category'].value,
                    'priority': pattern_config['priority'].value,
                    'confidence': 0.9,
                    'auto_resolvable': True,
                    'should_escalate': False,
                    'resolution_template': pattern_config.get('resolution_template'),
                    'reasoning': f"Matched auto-resolvable pattern: {pattern_config['pattern']}"
                }
        
        # Check for complex indicators (escalation needed)
        is_complex = any(re.search(indicator, text, re.IGNORECASE) for indicator in cls.COMPLEX_INDICATORS)
        
        # Classify category
        category_scores = {}
        for category, patterns in cls.CATEGORY_PATTERNS.items():
            score = sum(1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE))
            if score > 0:
                category_scores[category] = score
        
        if category_scores:
            category = max(category_scores, key=category_scores.get)
            category_confidence = category_scores[category] / sum(category_scores.values())
        else:
            category = TicketCategory.OTHER
            category_confidence = 0.5
        
        # Classify priority
        priority_scores = {}
        for priority, keywords in cls.PRIORITY_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                priority_scores[priority] = score
        
        if priority_scores:
            priority = max(priority_scores, key=priority_scores.get)
        else:
            # Default priority based on complexity
            if is_complex:
                priority = TicketPriority.HIGH
            else:
                priority = TicketPriority.MEDIUM
        
        # Determine if auto-resolvable (only low complexity, low/medium priority)
        auto_resolvable = (
            not is_complex and
            priority in [TicketPriority.LOW, TicketPriority.MEDIUM] and
            category_confidence > 0.6
        )
        
        return {
            'category': category.value,
            'priority': priority.value,
            'confidence': category_confidence,
            'auto_resolvable': auto_resolvable,
            'should_escalate': is_complex or priority == TicketPriority.URGENT,
            'reasoning': f"Category: {category.value} (confidence: {category_confidence:.2f}), Priority: {priority.value}, Complex: {is_complex}"
        }
    
    @classmethod
    def is_low_complexity(cls, description: str) -> bool:
        """
        Determine if an issue is low complexity and can be auto-resolved.
        
        Args:
            description: Ticket description
            
        Returns:
            True if low complexity, False otherwise
        """
        text = description.lower()
        
        # Check for complex indicators
        has_complex_indicators = any(
            re.search(indicator, text, re.IGNORECASE) 
            for indicator in cls.COMPLEX_INDICATORS
        )
        
        if has_complex_indicators:
            return False
        
        # Check for auto-resolvable patterns
        has_auto_resolvable = any(
            re.search(pattern['pattern'], text, re.IGNORECASE)
            for pattern in cls.AUTO_RESOLVABLE_PATTERNS
        )
        
        return has_auto_resolvable
    
    @classmethod
    def should_escalate(cls, description: str, classification: Optional[Dict] = None) -> bool:
        """
        Determine if a ticket should be escalated to human agent.
        
        Args:
            description: Ticket description
            classification: Optional pre-computed classification
            
        Returns:
            True if should escalate, False otherwise
        """
        if classification:
            return classification.get('should_escalate', False)
        
        text = description.lower()
        
        # Urgent keywords
        if any(keyword in text for keyword in ['urgent', 'critical', 'emergency', 'asap']):
            return True
        
        # Complex issues
        if any(re.search(indicator, text, re.IGNORECASE) for indicator in cls.COMPLEX_INDICATORS):
            return True
        
        return False
