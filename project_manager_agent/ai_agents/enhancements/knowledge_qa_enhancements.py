"""
Knowledge QA Agent Enhancements
Implements conversational memory, answer quality enhancement, proactive insights, semantic search
"""

from typing import Dict, List, Optional, Tuple
from django.core.cache import cache
from datetime import datetime, timedelta
import json
import logging
import math

logger = logging.getLogger(__name__)

# OpenAI embeddings are resolved per-company through the key service, not env vars.
# This module-level client is intentionally None; callers that need embeddings
# must pass their own company-resolved client.
try:
    from openai import OpenAI  # noqa: F401 — import check only
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
openai_client = None  # Never pre-created from env; always resolved per-company at runtime.


class KnowledgeQAEnhancements:
    """Enhancement methods for Knowledge QA Agent"""
    
    CACHE_PREFIX = "qa_conversation_"
    CACHE_TIMEOUT = 3600  # 1 hour
    
    @staticmethod
    def get_conversation_history(session_id: str, limit: int = 10) -> List[Dict]:
        """
        Get conversation history for a session.
        
        Args:
            session_id (str): Session identifier
            limit (int): Maximum number of messages to retrieve
            
        Returns:
            List[Dict]: Conversation history
        """
        cache_key = f"{KnowledgeQAEnhancements.CACHE_PREFIX}{session_id}"
        history = cache.get(cache_key, [])
        return history[-limit:] if len(history) > limit else history
    
    @staticmethod
    def add_to_conversation(session_id: str, question: str, answer: str, context: Dict = None):
        """
        Add question-answer pair to conversation history.
        
        Args:
            session_id (str): Session identifier
            question (str): User's question
            answer (str): Agent's answer
            context (Dict): Optional context
        """
        cache_key = f"{KnowledgeQAEnhancements.CACHE_PREFIX}{session_id}"
        history = cache.get(cache_key, [])
        
        history.append({
            'timestamp': datetime.now().isoformat(),
            'question': question,
            'answer': answer[:500],  # Limit answer length
            'context_summary': {
                'project_id': context.get('project', {}).get('id') if context else None,
                'task_count': len(context.get('tasks', [])) if context else 0,
            } if context else None
        })
        
        # Keep only last 20 messages
        if len(history) > 20:
            history = history[-20:]
        
        cache.set(cache_key, history, KnowledgeQAEnhancements.CACHE_TIMEOUT)
    
    @staticmethod
    def build_conversation_context(session_id: str) -> str:
        """
        Build conversation context string for LLM.
        
        Args:
            session_id (str): Session identifier
            
        Returns:
            str: Formatted conversation context
        """
        history = KnowledgeQAEnhancements.get_conversation_history(session_id, limit=5)
        
        if not history:
            return ""
        
        context_str = "\n\nPrevious Conversation:\n"
        for i, msg in enumerate(history, 1):
            context_str += f"{i}. Q: {msg['question']}\n"
            context_str += f"   A: {msg['answer'][:200]}...\n\n"
        
        return context_str
    
    @staticmethod
    def enhance_answer_quality(question: str, answer: str, context: Dict) -> Dict:
        """
        Enhance answer with structure, citations, and recommendations.
        
        Args:
            question (str): Original question
            answer (str): Base answer
            context (Dict): Project context
            
        Returns:
            Dict: Enhanced answer with metadata
        """
        # Extract sources from context
        sources = []
        if context.get('project'):
            sources.append({
                'type': 'project',
                'id': context['project'].get('id'),
                'name': context['project'].get('name', ''),
            })
        
        if context.get('tasks'):
            relevant_tasks = []
            question_lower = question.lower()
            for task in context['tasks'][:5]:  # Limit to 5 most relevant
                task_title = task.get('title', '').lower()
                if any(word in task_title for word in question_lower.split()[:3]):
                    relevant_tasks.append({
                        'type': 'task',
                        'id': task.get('id'),
                        'title': task.get('title', ''),
                    })
            sources.extend(relevant_tasks)
        
        # Calculate confidence (simple heuristic)
        confidence = 0.8
        if len(answer) < 50:
            confidence = 0.5  # Short answers might be uncertain
        elif '?' in answer or 'unclear' in answer.lower():
            confidence = 0.6
        
        # Generate related questions
        related_questions = KnowledgeQAEnhancements._generate_related_questions(question, context)
        
        # Extract actionable recommendations
        recommendations = KnowledgeQAEnhancements._extract_recommendations(answer)
        
        return {
            'answer': answer,
            'confidence': round(confidence, 2),
            'sources': sources,
            'related_questions': related_questions,
            'recommendations': recommendations,
            'timestamp': datetime.now().isoformat(),
        }
    
    @staticmethod
    def _generate_related_questions(question: str, context: Dict) -> List[str]:
        """Generate related questions user might ask"""
        related = []
        
        question_lower = question.lower()
        
        # Project-related questions
        if 'project' in question_lower:
            related.append("What is the current status of this project?")
            related.append("What tasks are remaining in this project?")
        
        # Task-related questions
        if 'task' in question_lower:
            related.append("What is the priority of these tasks?")
            related.append("Who is assigned to these tasks?")
        
        # Status-related questions
        if 'status' in question_lower or 'progress' in question_lower:
            related.append("What tasks are blocking progress?")
            related.append("What is the completion rate?")
        
        return related[:3]  # Limit to 3
    
    @staticmethod
    def _extract_recommendations(answer: str) -> List[str]:
        """Extract actionable recommendations from answer"""
        recommendations = []
        
        # Look for action verbs and recommendations
        answer_lower = answer.lower()
        
        if 'should' in answer_lower or 'recommend' in answer_lower:
            # Extract sentences with recommendations
            sentences = answer.split('.')
            for sentence in sentences:
                if any(word in sentence.lower() for word in ['should', 'recommend', 'suggest', 'consider']):
                    recommendations.append(sentence.strip())
        
        return recommendations[:3]  # Limit to 3
    
    @staticmethod
    def generate_proactive_insights(context: Dict) -> List[Dict]:
        """
        Generate proactive insights without being asked.
        
        Args:
            context (Dict): Project context
            
        Returns:
            List[Dict]: Proactive insights
        """
        insights = []
        
        if not context.get('tasks'):
            return insights
        
        tasks = context['tasks']
        
        # 1. Detect overdue tasks
        overdue_tasks = []
        now = datetime.now()
        for task in tasks:
            if task.get('status') in ['todo', 'in_progress', 'review']:
                due_date = task.get('due_date')
                if due_date:
                    try:
                        if isinstance(due_date, str):
                            due = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                        else:
                            due = due_date
                        
                        if due < now:
                            overdue_tasks.append(task)
                    except Exception:
                        pass
        
        if overdue_tasks:
            insights.append({
                'type': 'warning',
                'title': 'Overdue Tasks Detected',
                'message': f'You have {len(overdue_tasks)} overdue task(s)',
                'details': [t.get('title', '') for t in overdue_tasks[:5]],
                'priority': 'high'
            })
        
        # 2. Detect blocked tasks
        blocked_tasks = [t for t in tasks if t.get('status') == 'blocked']
        if blocked_tasks:
            insights.append({
                'type': 'warning',
                'title': 'Blocked Tasks',
                'message': f'You have {len(blocked_tasks)} blocked task(s) that may need attention',
                'details': [t.get('title', '') for t in blocked_tasks[:5]],
                'priority': 'medium'
            })
        
        # 3. Detect high workload
        assignee_counts = {}
        for task in tasks:
            if task.get('status') in ['todo', 'in_progress', 'review']:
                assignee_id = task.get('assignee_id')
                if assignee_id:
                    assignee_counts[assignee_id] = assignee_counts.get(assignee_id, 0) + 1
        
        overloaded_users = {uid: count for uid, count in assignee_counts.items() if count >= 8}
        if overloaded_users:
            insights.append({
                'type': 'suggestion',
                'title': 'High Workload Detected',
                'message': f'Some team members have {max(overloaded_users.values())} active tasks',
                'priority': 'medium'
            })
        
        # 4. Completion rate analysis
        completed = sum(1 for t in tasks if t.get('status') == 'done')
        total = len(tasks)
        if total > 0:
            completion_rate = (completed / total) * 100
            if completion_rate < 30 and total > 5:
                insights.append({
                    'type': 'info',
                    'title': 'Low Completion Rate',
                    'message': f'Project completion is at {completion_rate:.1f}%. Consider reviewing priorities.',
                    'priority': 'low'
                })
        
        return insights

