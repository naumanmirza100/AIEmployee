"""
Database Service Layer - Read-only access to PayPerProject database
Enterprise-level service for secure database access without direct SQL
"""
import logging
import pyodbc
import os
from typing import Dict, List, Optional, Any
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings

logger = logging.getLogger(__name__)


class PayPerProjectDatabaseService:
    """
    Read-only database service for accessing PayPerProject data.
    Provides secure API-based access without direct SQL queries.
    Uses direct pyodbc connection with credentials from .env file.
    """
    
    def __init__(self):
        """Initialize database service with read-only connection to PayPerProject database"""
        # Get credentials from Django settings.py (which loads from .env or uses defaults)
        # Priority: settings.py > environment variables > defaults
        self.DB_DRIVER = getattr(settings, 'DB_DRIVER', 'ODBC Driver 18 for SQL Server')
        self.DB_SERVER = getattr(settings, 'DB_HOST', 'localhost')
        self.DB_DATABASE = getattr(settings, 'DB_NAME', 'payperproject')
        self.DB_UID = getattr(settings, 'DB_USER', 'FrontlineAgent')
        self.DB_PWD = getattr(settings, 'DB_PASSWORD', 'Frontline@1')
        self.DB_PORT = getattr(settings, 'DB_PORT', '1433')
        self.DB_TRUST_SERVER_CERT = 'yes'
        
        # Debug logging to see what credentials are being used
        logger.info(f"PayPerProject Database Connection:")
        logger.info(f"  Server: {self.DB_SERVER}:{self.DB_PORT}")
        logger.info(f"  Database: {self.DB_DATABASE}")
        logger.info(f"  User: {self.DB_UID}")
        logger.info(f"  Driver: {self.DB_DRIVER}")
        
        # Validate credentials are available
        if not self.DB_UID or not self.DB_PWD:
            error_msg = f"Database credentials (DB_USER and DB_PASSWORD) not found in settings.py"
            logger.error(error_msg)
            raise ImproperlyConfigured(f"{error_msg}. Please set DB_USER and DB_PASSWORD in project_manager_ai/settings.py")
        
        # Build connection string (for SQL Server, if port is 1433, it's usually optional)
        if self.DB_PORT and self.DB_PORT != '1433':
            server = f'{self.DB_SERVER},{self.DB_PORT}'
        else:
            server = self.DB_SERVER
            
        self.connection_string = (
            f'DRIVER={{{self.DB_DRIVER}}};'
            f'SERVER={server};'
            f'DATABASE={self.DB_DATABASE};'
            f'UID={self.DB_UID};'
            f'PWD={self.DB_PWD};'
            f'TrustServerCertificate={self.DB_TRUST_SERVER_CERT};'
        )
        
        logger.info(f"Initializing PayPerProject database service connection...")
        logger.info(f"  Connection will be validated on first use")
        
        # Validate connection on initialization
        try:
            self._validate_connection()
            logger.info("✅ PayPerProject database connection validated successfully!")
        except Exception as e:
            logger.error(f"❌ PayPerProject database connection validation failed: {e}")
            logger.error("Please check:")
            logger.error(f"  1. SQL Server is running on {self.DB_SERVER}:{self.DB_PORT}")
            logger.error(f"  2. Database '{self.DB_DATABASE}' exists")
            logger.error(f"  3. User '{self.DB_UID}' has access to the database")
            logger.error(f"  4. Credentials in settings.py are correct")
            # Don't raise here - allow lazy connection on first use
            logger.warning("Connection will be retried on first database query")
    
    def _get_connection(self):
        """Get pyodbc connection"""
        try:
            return pyodbc.connect(self.connection_string)
        except Exception as e:
            logger.error(f"Failed to connect to PayPerProject database: {e}")
            raise ImproperlyConfigured(f"Cannot connect to PayPerProject database: {e}")
    
    def _validate_connection(self):
        """Validate database connection is available"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            logger.info("PayPerProject database connection validated successfully")
        except Exception as e:
            logger.error(f"Database connection validation failed: {e}")
            raise ImproperlyConfigured(f"Cannot connect to PayPerProject database: {e}")
    
    def _execute_read_query(self, query: str, params: Optional[List] = None) -> List[Dict]:
        """
        Execute a read-only query safely.
        
        Args:
            query: SQL query string (must be SELECT only)
            params: Query parameters for safe parameterization (list for pyodbc)
            
        Returns:
            List of dictionaries representing rows
        """
        if not query.strip().upper().startswith('SELECT'):
            raise ValueError("Only SELECT queries are allowed in read-only service")
        
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # Get column names
            columns = [column[0] for column in cursor.description]
            
            # Fetch all results
            rows = cursor.fetchall()
            results = []
            for row in rows:
                results.append(dict(zip(columns, row)))
            
            cursor.close()
            conn.close()
            
            logger.info(f"Query executed successfully: {len(results)} rows returned")
            return results
        except Exception as e:
            if conn:
                try:
                    conn.close()
                except:
                    pass
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
            # Try to query from PayPerProject database tables
            # Adjust table names based on actual PayPerProject schema
            query = """
                SELECT TOP (?)
                    id, question, answer, category, 
                    created_at, updated_at, is_active
                FROM dbo.FAQs
                WHERE is_active = 1
            """
            params = [limit]
            
            if search_term:
                query += " AND (question LIKE ? OR answer LIKE ? OR category LIKE ?)"
                search_pattern = f"%{search_term}%"
                params.extend([search_pattern, search_pattern, search_pattern])
            
            query += " ORDER BY updated_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"FAQs table may not exist or query failed: {e}")
            # Fallback to local KnowledgeBase if PayPerProject table doesn't exist
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
        try:
            query = """
                SELECT TOP (?)
                    id, title, content, policy_type, 
                    version, effective_date, created_at, updated_at, is_active
                FROM dbo.Policies
                WHERE is_active = 1
            """
            params = [limit]
            
            if search_term:
                query += " AND (title LIKE ? OR content LIKE ? OR policy_type LIKE ?)"
                search_pattern = f"%{search_term}%"
                params.extend([search_pattern, search_pattern, search_pattern])
            
            query += " ORDER BY updated_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"Policies table may not exist or query failed: {e}")
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
        try:
            query = """
                SELECT TOP (?)
                    id, title, content, manual_type, 
                    section, created_at, updated_at, is_active
                FROM dbo.Manuals
                WHERE is_active = 1
            """
            params = [limit]
            
            if search_term:
                query += " AND (title LIKE ? OR content LIKE ? OR manual_type LIKE ?)"
                search_pattern = f"%{search_term}%"
                params.extend([search_pattern, search_pattern, search_pattern])
            
            query += " ORDER BY updated_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"Manuals table may not exist or query failed: {e}")
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
                SELECT TOP (?)
                    id, title, description, status, priority, category,
                    created_by_id, assigned_to_id, created_at, updated_at, resolved_at
                FROM dbo.ppp_tickets
                WHERE 1=1
            """
            params = [limit]
            
            if status:
                query += " AND status = ?"
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
    
    def get_company_users(self, company_id: Optional[int] = None, user_id: Optional[int] = None, limit: int = 100) -> List[Dict]:
        """
        Retrieve company users from PayPerProject database.
        
        Args:
            company_id: Optional company ID filter
            user_id: Optional user ID filter
            limit: Maximum number of results
            
        Returns:
            List of company user dictionaries
        """
        try:
            query = """
                SELECT TOP (?)
                    id, company_id, user_id, role, status,
                    created_at, updated_at
                FROM dbo.ppp_company_users
                WHERE 1=1
            """
            params = [limit]
            
            if company_id:
                query += " AND company_id = ?"
                params.append(company_id)
            
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            
            query += " ORDER BY created_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"Company users query failed: {e}")
            return []
    
    def get_projects(self, company_id: Optional[int] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """
        Retrieve projects from PayPerProject database.
        
        Args:
            company_id: Optional company ID filter
            status: Optional status filter
            limit: Maximum number of results
            
        Returns:
            List of project dictionaries
        """
        try:
            query = """
                SELECT TOP (?)
                    id, company_id, name, description, status, priority,
                    start_date, end_date, created_at, updated_at
                FROM dbo.ppp_projects
                WHERE 1=1
            """
            params = [limit]
            
            if company_id:
                query += " AND company_id = ?"
                params.append(company_id)
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            query += " ORDER BY created_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"Projects query failed: {e}")
            return []
    
    def get_companies(self, company_id: Optional[int] = None, limit: int = 50) -> List[Dict]:
        """
        Retrieve companies from PayPerProject database.
        
        Args:
            company_id: Optional company ID filter
            limit: Maximum number of results
            
        Returns:
            List of company dictionaries
        """
        try:
            query = """
                SELECT TOP (?)
                    id, name, email, phone, address,
                    status, created_at, updated_at
                FROM dbo.ppp_companies
                WHERE 1=1
            """
            params = [limit]
            
            if company_id:
                query += " AND id = ?"
                params.append(company_id)
            
            query += " ORDER BY created_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"Companies query failed: {e}")
            return []
    
    def get_documents(self, company_id: Optional[int] = None, document_type: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """
        Retrieve documents from PayPerProject database.
        
        Args:
            company_id: Optional company ID filter
            document_type: Optional document type filter
            limit: Maximum number of results
            
        Returns:
            List of document dictionaries
        """
        try:
            query = """
                SELECT TOP (?)
                    id, company_id, title, document_type, file_path,
                    file_size, uploaded_by_id, created_at, updated_at
                FROM dbo.ppp_documents
                WHERE 1=1
            """
            params = [limit]
            
            if company_id:
                query += " AND company_id = ?"
                params.append(company_id)
            
            if document_type:
                query += " AND document_type = ?"
                params.append(document_type)
            
            query += " ORDER BY created_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"Documents query failed: {e}")
            return []
    
    def get_payments(self, company_id: Optional[int] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """
        Retrieve payments from PayPerProject database.
        
        Args:
            company_id: Optional company ID filter
            status: Optional payment status filter
            limit: Maximum number of results
            
        Returns:
            List of payment dictionaries
        """
        try:
            query = """
                SELECT TOP (?)
                    id, company_id, amount, currency, status,
                    payment_method, transaction_id, created_at, updated_at
                FROM dbo.ppp_payments
                WHERE 1=1
            """
            params = [limit]
            
            if company_id:
                query += " AND company_id = ?"
                params.append(company_id)
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            query += " ORDER BY created_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"Payments query failed: {e}")
            return []
    
    def get_workflows(self, workflow_name: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """
        Retrieve workflows from PayPerProject database.
        
        Args:
            workflow_name: Optional workflow name filter
            limit: Maximum number of results
            
        Returns:
            List of workflow dictionaries
        """
        try:
            query = """
                SELECT TOP (?)
                    id, name, description, steps_json, is_active,
                    created_at, updated_at
                FROM dbo.ppp_workflows
                WHERE is_active = 1
            """
            params = [limit]
            
            if workflow_name:
                query += " AND name LIKE ?"
                params.append(f"%{workflow_name}%")
            
            query += " ORDER BY created_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"Workflows query failed: {e}")
            return []
    
    def get_sops(self, sop_name: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """
        Retrieve SOPs from PayPerProject database.
        
        Args:
            sop_name: Optional SOP name filter
            limit: Maximum number of results
            
        Returns:
            List of SOP dictionaries
        """
        try:
            query = """
                SELECT TOP (?)
                    id, name, description, steps_json, category,
                    is_active, created_at, updated_at
                FROM dbo.ppp_sops
                WHERE is_active = 1
            """
            params = [limit]
            
            if sop_name:
                query += " AND name LIKE ?"
                params.append(f"%{sop_name}%")
            
            query += " ORDER BY created_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"SOPs query failed: {e}")
            return []
    
    def get_activity_logs(self, company_id: Optional[int] = None, user_id: Optional[int] = None, limit: int = 100) -> List[Dict]:
        """
        Retrieve activity logs from PayPerProject database.
        
        Args:
            company_id: Optional company ID filter
            user_id: Optional user ID filter
            limit: Maximum number of results
            
        Returns:
            List of activity log dictionaries
        """
        try:
            query = """
                SELECT TOP (?)
                    id, company_id, user_id, action, entity_type,
                    entity_id, details_json, created_at
                FROM dbo.ppp_activity_logs
                WHERE 1=1
            """
            params = [limit]
            
            if company_id:
                query += " AND company_id = ?"
                params.append(company_id)
            
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            
            query += " ORDER BY created_at DESC"
            
            return self._execute_read_query(query, params)
        except Exception as e:
            logger.warning(f"Activity logs query failed: {e}")
            return []
    
    def get_user_company_id(self, user_id: int) -> Optional[int]:
        """
        Get company ID for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Company ID if found, None otherwise
        """
        try:
            company_users = self.get_company_users(user_id=user_id, limit=1)
            if company_users:
                return company_users[0].get('company_id')
            return None
        except Exception as e:
            logger.error(f"Failed to get company ID for user {user_id}: {e}")
            return None

