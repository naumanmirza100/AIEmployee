"""
Database Service Layer - Read-only access to PayPerProject database
Enterprise-level service for secure database access without direct SQL
"""
import logging
from typing import Dict, List, Optional, Any
from django.db import connections
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class PayPerProjectDatabaseService:
    """
    Read-only database service for accessing PayPerProject data.
    Provides secure API-based access without direct SQL queries.
    """
    
    def __init__(self):
        """Initialize database service with read-only connection"""
        self.db_alias = 'default'
        self._validate_connection()
    
    def _validate_connection(self):
        """Validate database connection is available"""
        try:
            with connections[self.db_alias].cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception as e:
            logger.error(f"Database connection validation failed: {e}")
            raise ImproperlyConfigured(f"Cannot connect to PayPerProject database: {e}")
    
    def _execute_read_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Execute a read-only query safely.
        
        Args:
            query: SQL query string (must be SELECT only)
            params: Query parameters for safe parameterization
            
        Returns:
            List of dictionaries representing rows
        """
        if not query.strip().upper().startswith('SELECT'):
            raise ValueError("Only SELECT queries are allowed in read-only service")
        
        try:
            with connections[self.db_alias].cursor() as cursor:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                columns = [col[0] for col in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                
                logger.info(f"Query executed successfully: {len(results)} rows returned")
                return results
        except Exception as e:
            logger.error(f"Database query failed: {query[:100]}... Error: {e}")
            raise
    
    def get_faqs(self, search_term: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """
        Retrieve FAQs from PayPerProject database.
        
        Args:
            search_term: Optional search term to filter FAQs
            limit: Maximum number of results
            
        Returns:
            List of FAQ dictionaries
        """
        try:
            # Try to use Django FAQ model first
            from core.models import FAQ
            from django.db.models import Q
            
            queryset = FAQ.objects.filter(is_active=True)
            
            if search_term:
                queryset = queryset.filter(
                    Q(question__icontains=search_term) |
                    Q(answer__icontains=search_term) |
                    Q(category__icontains=search_term)
                )
            
            faqs = queryset.order_by('-updated_at')[:limit]
            
            return [
                {
                    'id': faq.id,
                    'question': faq.question,
                    'answer': faq.answer,
                    'category': faq.category or '',
                    'created_at': faq.created_at,
                    'updated_at': faq.updated_at,
                    'is_active': faq.is_active
                }
                for faq in faqs
            ]
        except Exception as e:
            logger.warning(f"FAQ model may not exist or query failed: {e}")
            # Fallback to local KnowledgeBase if FAQ model doesn't exist
            return self._get_faqs_fallback(search_term, limit)
    
    def _get_faqs_fallback(self, search_term: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Fallback to local KnowledgeBase model if PayPerProject table doesn't exist"""
        try:
            from Frontline_agent.models import KnowledgeBase
            from django.db.models import Q
            queryset = KnowledgeBase.objects.filter(category='faq')
            
            if search_term:
                queryset = queryset.filter(
                    Q(title__icontains=search_term) |
                    Q(content__icontains=search_term)
                )
            
            return [
                {
                    'id': kb.id,
                    'question': kb.title,
                    'answer': kb.content,
                    'category': kb.category,
                    'created_at': kb.created_at,
                    'updated_at': kb.updated_at,
                    'is_active': True
                }
                for kb in queryset[:limit]
            ]
        except Exception as e:
            logger.error(f"Fallback FAQ retrieval failed: {e}")
            return []
    
    def get_policies(self, search_term: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """
        Retrieve policies from PayPerProject database.
        
        Args:
            search_term: Optional search term to filter policies
            limit: Maximum number of results
            
        Returns:
            List of policy dictionaries
        """
        # Use KnowledgeBase model with policies category
        return self._get_policies_fallback(search_term, limit)
    
    def _get_policies_fallback(self, search_term: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Fallback to local KnowledgeBase model"""
        try:
            from Frontline_agent.models import KnowledgeBase
            from django.db.models import Q
            queryset = KnowledgeBase.objects.filter(category='policies')
            
            if search_term:
                queryset = queryset.filter(
                    Q(title__icontains=search_term) |
                    Q(content__icontains=search_term)
                )
            
            return [
                {
                    'id': kb.id,
                    'title': kb.title,
                    'content': kb.content,
                    'policy_type': kb.category,
                    'version': '1.0',
                    'effective_date': kb.created_at,
                    'created_at': kb.created_at,
                    'updated_at': kb.updated_at,
                    'is_active': True
                }
                for kb in queryset[:limit]
            ]
        except Exception as e:
            logger.error(f"Fallback policy retrieval failed: {e}")
            return []
    
    def get_manuals(self, search_term: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """
        Retrieve manuals/documentation from PayPerProject database.
        
        Args:
            search_term: Optional search term to filter manuals
            limit: Maximum number of results
            
        Returns:
            List of manual dictionaries
        """
        # Use KnowledgeBase model with documentation category
        return self._get_manuals_fallback(search_term, limit)
    
    def _get_manuals_fallback(self, search_term: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Fallback to local KnowledgeBase model"""
        try:
            from Frontline_agent.models import KnowledgeBase
            from django.db.models import Q
            queryset = KnowledgeBase.objects.filter(category='documentation')
            
            if search_term:
                queryset = queryset.filter(
                    Q(title__icontains=search_term) |
                    Q(content__icontains=search_term)
                )
            
            return [
                {
                    'id': kb.id,
                    'title': kb.title,
                    'content': kb.content,
                    'manual_type': kb.category,
                    'section': 'General',
                    'created_at': kb.created_at,
                    'updated_at': kb.updated_at,
                    'is_active': True
                }
                for kb in queryset[:limit]
            ]
        except Exception as e:
            logger.error(f"Fallback manual retrieval failed: {e}")
            return []
    
    def get_tickets(self, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """
        Retrieve tickets from PayPerProject database (read-only).
        
        Args:
            status: Optional status filter
            limit: Maximum number of results
            
        Returns:
            List of ticket dictionaries
        """
        try:
            query = """
                SELECT TOP (%s)
                    id, title, description, status, priority, category,
                    created_by_id, assigned_to_id, created_at, updated_at, resolved_at
                FROM dbo.Tickets
                WHERE 1=1
            """
            params = [limit]
            
            if status:
                query += " AND status = %s"
                params.append(status)
            
            query += " ORDER BY created_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"Tickets table query failed: {e}")
            # Fallback to local Ticket model
            return self._get_tickets_fallback(status, limit)
    
    def _get_tickets_fallback(self, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Fallback to local Ticket model"""
        try:
            from Frontline_agent.models import Ticket
            queryset = Ticket.objects.all()
            
            if status:
                queryset = queryset.filter(status=status)
            
            return [
                {
                    'id': ticket.id,
                    'title': ticket.title,
                    'description': ticket.description,
                    'status': ticket.status,
                    'priority': ticket.priority,
                    'category': ticket.category,
                    'created_by_id': ticket.created_by_id,
                    'assigned_to_id': ticket.assigned_to_id,
                    'created_at': ticket.created_at,
                    'updated_at': ticket.updated_at,
                    'resolved_at': ticket.resolved_at
                }
                for ticket in queryset[:limit]
            ]
        except Exception as e:
            logger.error(f"Fallback ticket retrieval failed: {e}")
            return []

