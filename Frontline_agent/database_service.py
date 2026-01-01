"""
PayPerProject Database Service
Fully functional database access with intelligent querying
"""
import pyodbc
import logging
from typing import Dict, List, Optional, Any
from django.conf import settings
import re

logger = logging.getLogger(__name__)


class PayPerProjectDatabaseService:
    """
    Comprehensive database service for PayPerProject.
    Dynamically discovers tables and provides intelligent querying.
    """
    
    def __init__(self):
        """Initialize database connection with credentials from settings"""
        db_config = getattr(settings, 'DATABASES', {}).get('default', {})
        
        db_host = db_config.get('HOST', '127.0.0.1')
        db_port = db_config.get('PORT', '1433')
        db_name = db_config.get('NAME', 'payPerProject')
        db_user = db_config.get('USER', 'Agent')
        db_password = db_config.get('PASSWORD', 'Agent@766')
        
        if not db_user:
            db_user = getattr(settings, 'DB_USER', 'Agent')
        if not db_password:
            db_password = getattr(settings, 'DB_PASSWORD', 'Agent@766')
        
        server = f"{db_host},{db_port}" if db_port != '1433' else db_host
        
        self.connection_string = (
            'DRIVER={ODBC Driver 18 for SQL Server};'
            f'SERVER={server};'
            f'DATABASE={db_name};'
            f'UID={db_user};'
            f'PWD={db_password};'
            'TrustServerCertificate=Yes;'
        )
        
        logger.info(f"Connecting to PayPerProject database: {db_name} on {server}")
        try:
            self.conn = pyodbc.connect(self.connection_string)
            self.cursor = self.conn.cursor()
            logger.info("✅ Successfully connected to PayPerProject database")
            # Discover available tables
            self._discover_tables()
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            logger.error(f"Connection string: DRIVER={{ODBC Driver 18 for SQL Server}}; SERVER={server}; DATABASE={db_name}; UID={db_user}; PWD=***;")
            # Don't raise - allow lazy connection
            self.conn = None
            self.cursor = None
            self.available_tables = []
            logger.warning("Database connection failed. Will retry on first query.")
    
    def _discover_tables(self):
        """Discover all tables in the database"""
        try:
            query = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"
            self.cursor.execute(query)
            self.available_tables = [row[0] for row in self.cursor.fetchall()]
            logger.info(f"Discovered {len(self.available_tables)} tables: {', '.join(self.available_tables[:10])}...")
        except Exception as e:
            logger.warning(f"Could not discover tables: {e}")
            self.available_tables = []
    
    def _ensure_connection(self):
        """Ensure database connection is active"""
        if self.conn is None or self.cursor is None:
            try:
                self.conn = pyodbc.connect(self.connection_string)
                self.cursor = self.conn.cursor()
                if not self.available_tables:
                    self._discover_tables()
                logger.info("✅ Database connection re-established")
            except Exception as e:
                logger.error(f"Failed to re-establish connection: {e}")
                raise
    
    def _execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute a SELECT query and return results as list of dictionaries"""
        try:
            # Ensure connection is active
            self._ensure_connection()
            
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            
            if not self.cursor.description:
                return []
            
            columns = [col[0] for col in self.cursor.description]
            rows = self.cursor.fetchall()
            
            results = []
            for row in rows:
                row_dict = {}
                for idx, col_name in enumerate(columns):
                    value = row[idx]
                    if hasattr(value, 'isoformat'):
                        row_dict[col_name] = value.isoformat()
                    elif value is None:
                        row_dict[col_name] = None
                    else:
                        row_dict[col_name] = str(value) if isinstance(value, (bytes, bytearray)) else value
                results.append(row_dict)
            
            return results
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            logger.error(f"Query: {query[:200]}")
            if params:
                logger.error(f"Params: {params}")
            return []
    
    def _find_table_by_keyword(self, keyword: str) -> Optional[str]:
        """Find table name by keyword (fuzzy matching)"""
        keyword_lower = keyword.lower()
        
        # Common mappings
        mappings = {
            'project': ['project', 'projekt', 'proje'],
            'ticket': ['ticket', 'issue', 'support'],
            'user': ['user', 'users', 'account'],
            'company': ['company', 'companies', 'client'],
            'task': ['task', 'tasks', 'todo'],
            'payment': ['payment', 'payments', 'invoice'],
            'document': ['document', 'documents', 'file']
        }
        
        for table_type, keywords in mappings.items():
            if any(k in keyword_lower for k in keywords):
                # Try to find matching table
                for table in self.available_tables:
                    table_lower = table.lower()
                    if table_type in table_lower or any(k in table_lower for k in keywords):
                        return table
        
        # Direct match
        for table in self.available_tables:
            if keyword_lower in table.lower() or table.lower() in keyword_lower:
                return table
        
        return None
    
    # ============================================
    # PROJECTS - Real Database Queries
    # ============================================
    def get_all_projects(self, status: Optional[str] = None) -> List[Dict]:
        """Get all projects from database - tries multiple table names"""
        # Try multiple possible table names
        possible_tables = ['projects', 'Projects', 'project', 'Project', 'ppp_projects', 'PayPerProject_Projects']
        
        project_table = None
        for table_name in possible_tables:
            if table_name in self.available_tables:
                project_table = table_name
                break
        
        # If not found, try fuzzy matching
        if not project_table:
            project_table = self._find_table_by_keyword('project')
        
        if not project_table:
            logger.warning(f"Project table not found. Available tables: {self.available_tables[:10]}")
            return []
        
        try:
            if status:
                # Try different status column names and status values
                status_variations = [status, status.lower(), status.upper(), status.capitalize()]
                query = f"SELECT TOP 100 * FROM [{project_table}] WHERE status IN (?,?,?,?) OR Status IN (?,?,?,?) OR state IN (?,?,?,?)"
                params = tuple(status_variations * 3)
                return self._execute_query(query, params)
            else:
                query = f"SELECT TOP 100 * FROM [{project_table}]"
                return self._execute_query(query)
        except Exception as e:
            logger.error(f"Error getting projects from {project_table}: {e}")
            # Try without WHERE clause if status filter fails
            try:
                query = f"SELECT TOP 100 * FROM [{project_table}]"
                return self._execute_query(query)
            except Exception as e2:
                logger.error(f"Error getting all projects: {e2}")
                return []
    
    def get_project_by_id(self, project_id: int) -> Optional[Dict]:
        """Get a single project by ID"""
        project_table = self._find_table_by_keyword('project')
        if not project_table:
            return None
        
        try:
            query = f"SELECT * FROM [{project_table}] WHERE id = ?"
            results = self._execute_query(query, (project_id,))
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting project {project_id}: {e}")
            return None
    
    def get_project_statistics(self) -> Dict[str, Any]:
        """Get comprehensive project statistics"""
        # Try multiple possible table names
        possible_tables = ['projects', 'Projects', 'project', 'Project', 'ppp_projects', 'PayPerProject_Projects']
        
        project_table = None
        for table_name in possible_tables:
            if table_name in self.available_tables:
                project_table = table_name
                break
        
        if not project_table:
            project_table = self._find_table_by_keyword('project')
        
        if not project_table:
            logger.warning("Project table not found for statistics")
            return {'total_projects': 0, 'by_status': {}, 'running_projects': 0}
        
        stats = {}
        
        try:
            # Total projects
            query = f"SELECT COUNT(*) as total FROM [{project_table}]"
            result = self._execute_query(query)
            stats['total_projects'] = result[0].get('total', 0) if result else 0
            
            # Projects by status - try multiple column name variations
            status_results = []
            status_queries = [
                f"SELECT status, COUNT(*) as count FROM [{project_table}] GROUP BY status",
                f"SELECT Status, COUNT(*) as count FROM [{project_table}] GROUP BY Status",
                f"SELECT state, COUNT(*) as count FROM [{project_table}] GROUP BY state",
                f"SELECT State, COUNT(*) as count FROM [{project_table}] GROUP BY State"
            ]
            
            for query in status_queries:
                try:
                    status_results = self._execute_query(query)
                    if status_results:
                        break
                except:
                    continue
            
            if status_results:
                stats['by_status'] = {}
                for row in status_results:
                    status_key = row.get('status') or row.get('Status') or row.get('state') or row.get('State') or 'unknown'
                    count = row.get('count', 0)
                    stats['by_status'][str(status_key)] = count
            else:
                stats['by_status'] = {}
            
            # Running/Active projects - count projects with running/active status
            running_keywords = ['running', 'active', 'in_progress', 'in progress', 'ongoing']
            running_count = 0
            for status, count in stats['by_status'].items():
                status_lower = str(status).lower()
                if any(keyword in status_lower for keyword in running_keywords):
                    running_count += count
            
            # If no running found in status breakdown, try direct query
            if running_count == 0:
                for keyword in running_keywords:
                    try:
                        query = f"SELECT COUNT(*) as count FROM [{project_table}] WHERE LOWER(status) LIKE ? OR LOWER(Status) LIKE ?"
                        result = self._execute_query(query, (f'%{keyword}%', f'%{keyword}%'))
                        if result and result[0].get('count', 0) > 0:
                            running_count = result[0].get('count', 0)
                            break
                    except:
                        continue
            
            stats['running_projects'] = running_count
            
            # Recent projects - try multiple date column names
            recent_queries = [
                f"SELECT TOP 10 * FROM [{project_table}] ORDER BY created_at DESC",
                f"SELECT TOP 10 * FROM [{project_table}] ORDER BY CreatedAt DESC",
                f"SELECT TOP 10 * FROM [{project_table}] ORDER BY created_date DESC",
                f"SELECT TOP 10 * FROM [{project_table}]"
            ]
            
            for query in recent_queries:
                try:
                    stats['recent_projects'] = self._execute_query(query)
                    if stats['recent_projects']:
                        break
                except:
                    continue
            
            if 'recent_projects' not in stats:
                stats['recent_projects'] = []
        
        except Exception as e:
            logger.error(f"Error getting project statistics: {e}", exc_info=True)
            stats = {'total_projects': 0, 'by_status': {}, 'running_projects': 0}
        
        return stats
    
    # ============================================
    # TICKETS - Real Database Queries
    # ============================================
    def get_tickets(self, user_id: Optional[int] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get tickets from database"""
        ticket_table = self._find_table_by_keyword('ticket')
        if not ticket_table:
            return []
        
        try:
            query = f"SELECT TOP (?) * FROM [{ticket_table}] WHERE 1=1"
            params = [limit]
            
            if user_id:
                # Try different user column names
                query += " AND (user_id = ? OR userId = ? OR created_by_id = ? OR created_by = ?)"
                params.extend([user_id, user_id, user_id, user_id])
            
            if status:
                query += " AND (status = ? OR Status = ?)"
                params.extend([status, status])
            
            # Try to order by date
            try:
                query += " ORDER BY created_at DESC"
            except:
                try:
                    query += " ORDER BY CreatedAt DESC"
                except:
                    pass
            
            return self._execute_query(query, tuple(params))
        except Exception as e:
            logger.error(f"Error getting tickets: {e}")
            return []
    
    def get_ticket_statistics(self) -> Dict[str, Any]:
        """Get ticket statistics"""
        ticket_table = self._find_table_by_keyword('ticket')
        if not ticket_table:
            return {'total_tickets': 0, 'by_status': {}}
        
        stats = {}
        
        try:
            query = f"SELECT COUNT(*) as total FROM [{ticket_table}]"
            result = self._execute_query(query)
            stats['total_tickets'] = result[0].get('total', 0) if result else 0
            
            try:
                query = f"SELECT status, COUNT(*) as count FROM [{ticket_table}] GROUP BY status"
                results = self._execute_query(query)
                stats['by_status'] = {row.get('status', 'unknown'): row.get('count', 0) for row in results}
            except:
                try:
                    query = f"SELECT Status, COUNT(*) as count FROM [{ticket_table}] GROUP BY Status"
                    results = self._execute_query(query)
                    stats['by_status'] = {row.get('Status', 'unknown'): row.get('count', 0) for row in results}
                except:
                    stats['by_status'] = {}
        except Exception as e:
            logger.error(f"Error getting ticket statistics: {e}")
            stats = {'total_tickets': 0, 'by_status': {}}
        
        return stats
    
    # ============================================
    # USERS & COMPANIES
    # ============================================
    def get_user_company_id(self, user_id: int) -> Optional[int]:
        """Get company ID for a user"""
        queries = [
            "SELECT company_id FROM users WHERE id = ?",
            "SELECT company_id FROM user_profiles WHERE user_id = ?",
            "SELECT company_id FROM company_users WHERE user_id = ?",
            "SELECT CompanyId FROM Users WHERE Id = ?"
        ]
        
        for query in queries:
            try:
                result = self._execute_query(query, (user_id,))
                if result and result[0].get('company_id'):
                    return result[0]['company_id']
                if result and result[0].get('CompanyId'):
                    return result[0]['CompanyId']
            except:
                continue
        
        return None
    
    def get_all_users(self, limit: int = 100) -> List[Dict]:
        """Get all users"""
        user_table = self._find_table_by_keyword('user')
        if not user_table:
            return []
        
        try:
            query = f"SELECT TOP (?) * FROM [{user_table}]"
            return self._execute_query(query, (limit,))
        except:
            return []
    
    def get_all_companies(self, limit: int = 100) -> List[Dict]:
        """Get all companies"""
        company_table = self._find_table_by_keyword('company')
        if not company_table:
            return []
        
        try:
            query = f"SELECT TOP (?) * FROM [{company_table}]"
            return self._execute_query(query, (limit,))
        except:
            return []
    
    # ============================================
    # INTELLIGENT SEARCH
    # ============================================
    def search_payperproject_data(self, query_text: str) -> Dict[str, Any]:
        """Intelligently search across PayPerProject database"""
        query_lower = query_text.lower()
        results = {
            'projects': [],
            'tickets': [],
            'users': [],
            'companies': []
        }
        
        # Search projects
        if any(word in query_lower for word in ['project', 'projekt', 'proje', 'proj']):
            results['projects'] = self.get_all_projects()
        
        # Search tickets
        if any(word in query_lower for word in ['ticket', 'issue', 'problem', 'support', 'help']):
            results['tickets'] = self.get_tickets(limit=20)
        
        # Search users
        if any(word in query_lower for word in ['user', 'users', 'account', 'member']):
            results['users'] = self.get_all_users(limit=20)
        
        # Search companies
        if any(word in query_lower for word in ['company', 'companies', 'client', 'customer', 'organization']):
            results['companies'] = self.get_all_companies(limit=20)
        
        return results
    
    def get_table_schema(self, table_name: str) -> List[Dict]:
        """Get schema/columns for a specific table"""
        try:
            self._ensure_connection()
            query = """
                SELECT 
                    COLUMN_NAME,
                    DATA_TYPE,
                    IS_NULLABLE,
                    CHARACTER_MAXIMUM_LENGTH
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
            """
            self.cursor.execute(query, (table_name,))
            columns = [col[0] for col in self.cursor.description]
            rows = self.cursor.fetchall()
            
            results = []
            for row in rows:
                row_dict = {}
                for idx, col_name in enumerate(columns):
                    row_dict[col_name] = row[idx]
                results.append(row_dict)
            
            return results
        except Exception as e:
            logger.error(f"Error getting schema for {table_name}: {e}")
            return []
    
    def get_table_data_sample(self, table_name: str, limit: int = 3) -> List[Dict]:
        """Get sample data from a table"""
        try:
            self._ensure_connection()
            query = f"SELECT TOP {limit} * FROM [{table_name}]"
            return self._execute_query(query)
        except Exception as e:
            logger.error(f"Error getting sample data from {table_name}: {e}")
            return []
    
    def get_database_summary(self) -> Dict[str, Any]:
        """Get comprehensive database summary"""
        return {
            'tables': self.available_tables,
            'project_stats': self.get_project_statistics(),
            'ticket_stats': self.get_ticket_statistics()
        }
    
    def close(self):
        """Close database connection"""
        if hasattr(self, 'cursor'):
            self.cursor.close()
        if hasattr(self, 'conn'):
            self.conn.close()
