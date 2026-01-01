"""
Frontline AI Customer Support Orchestrator
Fully functional ChatGPT-like AI agent for PayPerProject
Intelligently analyzes real database and provides comprehensive, professional responses
Handles typos and natural language understanding
"""
import logging
from typing import Dict, Any, List, Optional, List
from django.contrib.auth.models import User
from django.conf import settings
import json
import re

try:
    from groq import Groq
except ImportError:
    Groq = None

from .database_service import PayPerProjectDatabaseService
from .services import KnowledgeService, TicketAutomationService
from .prompts import (
    FRONTLINE_SYSTEM_PROMPT,
    FRONTLINE_DATABASE_ANALYSIS_PROMPT,
    FRONTLINE_GENERAL_QUERY_PROMPT,
    FRONTLINE_STATISTICS_PROMPT,
    FRONTLINE_PLATFORM_INFO_PROMPT
)
from .models import Ticket, Notification

logger = logging.getLogger(__name__)


class FrontlineAICustomerSupport:
    """
    Professional Frontline AI Customer Support for PayPerProject.
    
    Features:
    - ChatGPT-like professional communication
    - Intelligent database analysis with real data
    - Natural language understanding (handles typos)
    - Comprehensive PayPerProject insights
    - Friendly yet authoritative responses
    """
    
    def __init__(self):
        logger.info("=" * 70)
        logger.info("Initializing Professional Frontline AI Customer Support...")
        logger.info("=" * 70)
        
        # Initialize database service
        try:
            self.db_service = PayPerProjectDatabaseService()
            logger.info("✅ PayPerProject Database Service initialized")
        except Exception as e:
            logger.error(f"❌ Database service initialization failed: {e}")
            self.db_service = None
        
        # Initialize other services
        try:
            self.knowledge_service = KnowledgeService()
            logger.info("✅ Knowledge Service initialized")
        except Exception as e:
            logger.warning(f"⚠️ Knowledge Service: {e}")
            self.knowledge_service = None
        
        try:
            self.ticket_service = TicketAutomationService()
            logger.info("✅ Ticket Service initialized")
        except Exception as e:
            logger.warning(f"⚠️ Ticket Service: {e}")
            self.ticket_service = None
        
        # Initialize Groq AI client
        self.api_key = getattr(settings, "GROQ_API_KEY", None)
        self.model = getattr(settings, "GROQ_MODEL", "llama-3.1-8b-instant")
        
        if not self.api_key:
            # Try to get from environment
            import os
            self.api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API")
        
        if Groq and self.api_key:
            try:
                self.client = Groq(api_key=self.api_key)
                    # Don't test on init to avoid delays - test will happen on first use
                logger.info(f"✅ Groq AI Client initialized (Model: {self.model})")
                logger.info(f"   API Key: {self.api_key[:10]}...{self.api_key[-10:] if len(self.api_key) > 20 else '***'}")
            except Exception as e:
                logger.error(f"❌ Groq client initialization failed: {e}")
                logger.error(f"   Error type: {type(e).__name__}")
                self.client = None
        else:
            self.client = None
            if not self.api_key:
                logger.warning("⚠️ GROQ_API_KEY not found in settings or environment")
            if not Groq:
                logger.warning("⚠️ Groq library not installed. Run: pip install groq")
        
        logger.info("=" * 70)
        logger.info("✅ Frontline AI Customer Support initialized successfully!")
        logger.info("=" * 70)
    
    def _normalize_query(self, message: str) -> str:
        """Normalize query for better matching (handle typos, variations)"""
        # Convert to lowercase
        normalized = message.lower().strip()
        
        # Common typo corrections
        corrections = {
            'payperproject': 'payperproject',
            'pay per project': 'payperproject',
            'pay-per-project': 'payperproject',
            'projekt': 'project',
            'proje': 'project',
            'proj': 'project',
            'runing': 'running',
            'runing': 'running',
            'activ': 'active',
            'tiket': 'ticket',
            'tikcet': 'ticket',
            'how many': 'how many',
            'howmuch': 'how many',
            'wat': 'what',
            'wht': 'what',
            'whut': 'what'
        }
        
        for typo, correct in corrections.items():
            normalized = normalized.replace(typo, correct)
        
        return normalized
    
    def _detect_intent(self, message: str) -> str:
        """Detect user intent with typo tolerance"""
        normalized = self._normalize_query(message)
        
        # Platform information queries (including purpose)
        if any(phrase in normalized for phrase in [
            'what is payperproject', 'what payperproject', 'tell me about payperproject',
            'explain payperproject', 'describe payperproject', 'payperproject is',
            'whats payperproject', 'what\'s payperproject', 'purpose of payperproject',
            'what is the purpose', 'what is the purpose of payperproject', 'why payperproject',
            'what does payperproject do', 'payperproject purpose', 'payperproject used for'
        ]):
            return 'platform_info'
        
        # Statistics queries
        if any(phrase in normalized for phrase in [
            'how many', 'how much', 'count', 'total', 'number of',
            'statistics', 'stats', 'summary', 'overview'
        ]):
            if any(word in normalized for word in ['project', 'projekt', 'proje']):
                if any(word in normalized for word in ['running', 'active', 'current', 'now']):
                    return 'running_projects_count'
                return 'project_statistics'
            elif any(word in normalized for word in ['ticket', 'issue']):
                return 'ticket_statistics'
            return 'statistics'
        
        # Project queries
        if any(word in normalized for word in ['project', 'projekt', 'proje']):
            return 'project_query'
        
        # Ticket queries
        if any(word in normalized for word in ['ticket', 'issue', 'problem', 'support', 'help']):
            return 'ticket_query'
        
        # Database analysis queries (but prioritize project/ticket queries if they contain those keywords)
        if any(word in normalized for word in ['show', 'list', 'get', 'find', 'search', 'analyze']):
            # If it's about projects or tickets, route to specific handler
            if any(word in normalized for word in ['project', 'projekt', 'proje']):
                return 'project_query'
            if any(word in normalized for word in ['ticket', 'issue']):
                return 'ticket_query'
            return 'database_query'
        
        return 'general_query'
    
    def process(self, user: User, message: str, **kwargs) -> Dict[str, Any]:
        """
        Main processing method - intelligently handles user queries.
        Provides ChatGPT-like professional responses based on real PayPerProject data.
        """
        message_lower = message.lower().strip()
        
        # ============================================
        # GREETINGS
        # ============================================
        greetings = ["hi", "hello", "hey", "salam", "assalam", "good morning", "good afternoon", "good evening"]
        if message_lower in greetings or any(g in message_lower for g in greetings):
            return self._generate_greeting_response()
        
        # Detect intent (with typo tolerance)
        intent = self._detect_intent(message)
        logger.info(f"Detected intent: {intent} for query: {message}")
        
        # ============================================
        # PLATFORM INFORMATION QUERIES
        # ============================================
        if intent == 'platform_info':
            return self._handle_platform_info_query(message)
        
        # ============================================
        # RUNNING PROJECTS COUNT (Specific Query)
        # ============================================
        if intent == 'running_projects_count':
            return self._handle_running_projects_count(message)
        
        # ============================================
        # STATISTICS QUERIES
        # ============================================
        if intent == 'statistics' or intent == 'project_statistics' or intent == 'ticket_statistics':
            return self._handle_statistics_query(user, message, intent)
        
        # ============================================
        # DATABASE ANALYSIS QUERIES
        # ============================================
        if intent == 'database_query':
            return self._handle_database_query(user, message)
        
        # ============================================
        # PROJECT QUERIES
        # ============================================
        if intent == 'project_query':
            return self._handle_project_query(user, message)
        
        # ============================================
        # TICKET QUERIES
        # ============================================
        if intent == 'ticket_query':
            return self._handle_ticket_query(user, message, **kwargs)
        
        # ============================================
        # GENERAL QUERIES (with intelligent analysis)
        # ============================================
        return self._handle_intelligent_query(user, message)
    
    def _generate_greeting_response(self) -> Dict[str, Any]:
        """Generate professional greeting response"""
        greeting = """Hello! I'm your Frontline AI Customer Support Assistant for PayPerProject.

I'm here to help you with:
• Analyzing PayPerProject data and providing insights
• Answering questions about projects, tickets, users, and more
• Providing statistics and reports
• Assisting with platform features and functionality

How can I assist you today?"""
        
        return {
            "success": True,
            "message": greeting,
            "answer": greeting
        }
    
    def _handle_platform_info_query(self, message: str) -> Dict[str, Any]:
        """Handle 'what is payperproject' and 'purpose' queries with deep database analysis"""
        if not self.db_service:
            # Direct response without database
            response = """PayPerProject is an enterprise project management platform that helps organizations:
• Manage and track projects throughout their lifecycle
• Handle support tickets and customer issues
• Coordinate teams and resources
• Generate analytics and performance reports
• Manage users, companies, and organizational data

I can help you with questions about your projects, tickets, users, and more. What would you like to know?"""
            return {
                "success": True,
                "message": response,
                "answer": response
            }
        
        try:
            logger.info("🔍 Performing deep database analysis for platform purpose query...")
            
            # ============================================
            # COMPREHENSIVE DATABASE ANALYSIS
            # ============================================
            
            # 1. Get all tables and their structures
            all_tables = self.db_service.get_all_tables()
            logger.info(f"Found {len(all_tables)} tables in database")
            
            # 2. Analyze table structures to understand functionality
            table_analysis = {}
            key_tables = []
            
            for table_name in all_tables[:30]:  # Analyze first 30 tables
                try:
                    schema = self.db_service.get_table_schema(table_name)
                    sample_data = self.db_service.get_table_data_sample(table_name, limit=3)
                    
                    # Identify key columns
                    columns = [col.get('COLUMN_NAME', '') for col in schema]
                    column_types = {col.get('COLUMN_NAME', ''): col.get('DATA_TYPE', '') for col in schema}
                    
                    # Determine table purpose based on columns
                    table_purpose = self._analyze_table_purpose(table_name, columns, sample_data)
                    
                    table_analysis[table_name] = {
                        'columns': columns,
                        'column_count': len(columns),
                        'sample_rows': len(sample_data),
                        'purpose': table_purpose,
                        'key_columns': columns[:10]  # First 10 columns
                    }
                    
                    if table_purpose:
                        key_tables.append(table_name)
                        
                except Exception as e:
                    logger.warning(f"Error analyzing table {table_name}: {e}")
                    continue
            
            # 3. Get comprehensive statistics
            project_stats = self.db_service.get_project_statistics()
            ticket_stats = self.db_service.get_ticket_statistics()
            
            # 4. Get sample data from key entities
            projects = self.db_service.get_all_projects()[:5]  # Sample projects
            tickets = []
            users = []
            companies = []
            
            # Try to get sample tickets
            ticket_table = self.db_service._find_table_by_keyword('ticket')
            if ticket_table:
                try:
                    tickets = self.db_service._execute_query(f"SELECT TOP 5 * FROM [{ticket_table}]")
                except:
                    pass
            
            # Try to get sample users
            user_table = self.db_service._find_table_by_keyword('user')
            if user_table:
                try:
                    users = self.db_service._execute_query(f"SELECT TOP 5 * FROM [{user_table}]")
                except:
                    pass
            
            # Try to get sample companies
            company_table = self.db_service._find_table_by_keyword('company')
            if company_table:
                try:
                    companies = self.db_service._execute_query(f"SELECT TOP 5 * FROM [{company_table}]")
                except:
                    pass
            
            # ============================================
            # BUILD COMPREHENSIVE ANALYSIS DATA
            # ============================================
            
            analysis_data = {
                'database_structure': {
                    'total_tables': len(all_tables),
                    'key_tables': key_tables[:15],
                    'table_analysis': {k: v for k, v in list(table_analysis.items())[:15]}
                },
                'current_data': {
                    'projects': {
                        'total': project_stats.get('total_projects', 0),
                        'running': project_stats.get('running_projects', 0),
                        'completed': project_stats.get('completed_projects', 0),
                        'by_status': project_stats.get('by_status', {}),
                        'sample': projects
                    },
                    'tickets': {
                        'total': ticket_stats.get('total_tickets', 0),
                        'open': ticket_stats.get('open_tickets', 0),
                        'resolved': ticket_stats.get('resolved_tickets', 0),
                        'sample': tickets[:3]
                    },
                    'users': {
                        'sample_count': len(users),
                        'sample': users[:3]
                    },
                    'companies': {
                        'sample_count': len(companies),
                        'sample': companies[:3]
                    }
                },
                'functionality_identified': self._identify_functionality_from_tables(table_analysis, key_tables)
            }
            
            # Convert to JSON for AI processing
            analysis_text = json.dumps(analysis_data, indent=2, default=str)
            
            logger.info(f"✅ Database analysis complete. Found {len(key_tables)} key tables, {project_stats.get('total_projects', 0)} projects, {ticket_stats.get('total_tickets', 0)} tickets")
            
            # ============================================
            # GENERATE AI-POWERED RESPONSE
            # ============================================
            
            prompt = f"""Based on a comprehensive analysis of the PayPerProject database, explain the purpose and functionality of PayPerProject.

DATABASE ANALYSIS RESULTS:
{analysis_text}

USER QUESTION: "{message}"

Please provide a detailed, professional answer about PayPerProject's purpose based on:
1. The actual database structure (tables, columns, relationships)
2. Current data in the system (projects, tickets, users, companies)
3. Identified functionality from the database schema
4. Real statistics and usage patterns

Make the answer:
- Based on REAL data from the database
- Professional and clear
- Specific about what PayPerProject actually does
- Include concrete examples from the database
- Explain the purpose in a way that reflects the actual system capabilities

RESPONSE:"""
            
            # Generate AI response with comprehensive context
            ai_result = self._generate_ai_response(prompt, analysis_text)
            
            # If AI worked, use it; otherwise provide detailed fallback
            if ai_result.get('success') and 'error' not in ai_result.get('message', '').lower():
                return ai_result
            
            # Fallback: Build detailed response from analysis
            return self._build_purpose_response_from_analysis(analysis_data, project_stats, ticket_stats)
            
        except Exception as e:
            logger.error(f"Platform info query error: {e}", exc_info=True)
            # Fallback response
            response = """PayPerProject is an enterprise project management platform that helps organizations manage projects, track tickets, and coordinate teams effectively.

I can help you with questions about your projects, tickets, users, and more. What would you like to know?"""
            return {
                "success": True,
                "message": response,
                "answer": response
            }
    
    def _analyze_table_purpose(self, table_name: str, columns: List[str], sample_data: List[Dict]) -> str:
        """Analyze a table to determine its purpose"""
        table_lower = table_name.lower()
        columns_lower = [c.lower() for c in columns]
        
        # Project-related
        if 'project' in table_lower or any('project' in c for c in columns_lower):
            return "Project Management"
        
        # Ticket-related
        if 'ticket' in table_lower or any('ticket' in c for c in columns_lower):
            return "Support Ticket Management"
        
        # User-related
        if 'user' in table_lower or 'account' in table_lower or any('user' in c or 'email' in c for c in columns_lower):
            return "User Management"
        
        # Company-related
        if 'company' in table_lower or 'organization' in table_lower or 'client' in table_lower:
            return "Company/Organization Management"
        
        # Payment/Financial
        if 'payment' in table_lower or 'invoice' in table_lower or 'billing' in table_lower or any('payment' in c or 'amount' in c for c in columns_lower):
            return "Payment & Billing"
        
        # Task-related
        if 'task' in table_lower or 'todo' in table_lower:
            return "Task Management"
        
        # Document-related
        if 'document' in table_lower or 'file' in table_lower or 'attachment' in table_lower:
            return "Document Management"
        
        # Notification
        if 'notification' in table_lower or 'alert' in table_lower:
            return "Notifications & Alerts"
        
        # Analytics
        if 'analytics' in table_lower or 'metric' in table_lower or 'report' in table_lower:
            return "Analytics & Reporting"
        
        # Meeting/Scheduling
        if 'meeting' in table_lower or 'schedule' in table_lower or 'calendar' in table_lower:
            return "Meeting & Scheduling"
        
        return "Data Storage"
    
    def _identify_functionality_from_tables(self, table_analysis: Dict, key_tables: List[str]) -> List[str]:
        """Identify PayPerProject functionality based on table analysis"""
        functionality = []
        purposes_found = set()
        
        for table_name, analysis in table_analysis.items():
            purpose = analysis.get('purpose', '')
            if purpose and purpose not in purposes_found:
                purposes_found.add(purpose)
                functionality.append(purpose)
        
        return functionality
    
    def _build_purpose_response_from_analysis(self, analysis_data: Dict, project_stats: Dict, ticket_stats: Dict) -> Dict[str, Any]:
        """Build a detailed purpose response from database analysis"""
        db_structure = analysis_data.get('database_structure', {})
        current_data = analysis_data.get('current_data', {})
        functionality = analysis_data.get('functionality_identified', [])
        
        total_tables = db_structure.get('total_tables', 0)
        key_tables = db_structure.get('key_tables', [])
        
        projects_data = current_data.get('projects', {})
        tickets_data = current_data.get('tickets', {})
        
        response_lines = [
            "=" * 70,
            "🎯 PAYPERPROJECT - PURPOSE & FUNCTIONALITY",
            "=" * 70,
            "",
            "Based on comprehensive analysis of the PayPerProject database, here's what the platform does:",
            ""
        ]
        
        # Core Purpose
        response_lines.extend([
            "📋 **CORE PURPOSE:**",
            "PayPerProject is an enterprise project management and business operations platform designed to:",
            ""
        ])
        
        # Functionality based on database
        if functionality:
            response_lines.append("🔧 **KEY FUNCTIONALITY (from database analysis):**")
            for idx, func in enumerate(functionality, 1):
                response_lines.append(f"   {idx}. {func}")
            response_lines.append("")
        
        # Database Structure
        response_lines.extend([
            "🗄️ **DATABASE STRUCTURE:**",
            f"   • Total Database Tables: {total_tables}",
            f"   • Key Functional Areas: {len(key_tables)}",
            ""
        ])
        
        if key_tables:
            response_lines.append("   Key Tables Identified:")
            for table in key_tables[:10]:
                response_lines.append(f"      - {table}")
            response_lines.append("")
        
        # Current System Status
        response_lines.extend([
            "📊 **CURRENT SYSTEM STATUS (Real Data):**",
            ""
        ])
        
        if projects_data.get('total', 0) > 0:
            response_lines.extend([
                f"   📈 Projects:",
                f"      • Total Projects: {projects_data.get('total', 0)}",
                f"      • Running/Active: {projects_data.get('running', 0)}",
                f"      • Completed: {projects_data.get('completed', 0)}",
                ""
            ])
        
        if tickets_data.get('total', 0) > 0:
            response_lines.extend([
                f"   🎫 Support Tickets:",
                f"      • Total Tickets: {tickets_data.get('total', 0)}",
                f"      • Open Tickets: {tickets_data.get('open', 0)}",
                f"      • Resolved: {tickets_data.get('resolved', 0)}",
                ""
            ])
        
        # What PayPerProject Enables
        response_lines.extend([
            "💡 **WHAT PAYPERPROJECT ENABLES:**",
            "   • Comprehensive project lifecycle management",
            "   • Support ticket tracking and resolution",
            "   • Team and resource coordination",
            "   • Business analytics and reporting",
            "   • Organizational data management",
            "",
            "=" * 70,
            "",
            "This analysis is based on the actual database structure and current data in your PayPerProject system.",
            ""
        ])
        
        response_text = "\n".join(response_lines)
        
        return {
            "success": True,
            "message": response_text,
            "answer": response_text
        }
    
    def _handle_running_projects_count(self, message: str) -> Dict[str, Any]:
        """Handle 'how many projects currently running' queries"""
        if not self.db_service:
            return {
                "success": True,
                "message": "I'm currently unable to access the project database. Please try again in a moment.",
                "answer": "Database temporarily unavailable"
            }
        
        try:
            project_stats = self.db_service.get_project_statistics()
            running_count = project_stats.get('running_projects', 0)
            total_count = project_stats.get('total_projects', 0)
            by_status = project_stats.get('by_status', {})
            
            # Build direct response from real data
            response = f"""**Currently Running/Active Projects: {running_count}**

Total Projects in System: {total_count}

**Status Breakdown:**"""
            
            if by_status:
                for status, count in by_status.items():
                    response += f"\n• {status}: {count}"
            else:
                response += "\n• Status information not available"
            
            response += "\n\nWould you like more details about any specific projects or their status?"
            
            # Try AI enhancement, but use direct response as fallback
            try:
                stats_data = {
                    'running_projects': running_count,
                    'total_projects': total_count,
                    'status_breakdown': by_status
                }
                
                stats_text = json.dumps(stats_data, indent=2, default=str)
                
                prompt = FRONTLINE_STATISTICS_PROMPT.format(
                    statistics_data=stats_text,
                    user_question=message
                )
                
                ai_result = self._generate_ai_response(prompt, stats_text)
                # If AI worked, use it; otherwise use direct response
                if ai_result.get('success') and 'error' not in ai_result.get('message', '').lower():
                    return ai_result
            except Exception as e:
                logger.warning(f"AI enhancement failed, using direct response: {e}")
            
            # Return direct response from database
            return {
                "success": True,
                "message": response,
                "answer": response
            }
            
        except Exception as e:
            logger.error(f"Running projects count error: {e}", exc_info=True)
            return {
                "success": True,
                "message": f"I encountered an error retrieving project information: {str(e)}. Please try again.",
                "answer": "Error retrieving project data"
            }
    
    def _handle_statistics_query(self, user: User, message: str, intent: str) -> Dict[str, Any]:
        """Handle statistics queries"""
        if not self.db_service:
            return self._fallback_response("Database service is not available.")
        
        try:
            stats_data = {}
            
            if 'project' in intent or 'project' in message.lower():
                project_stats = self.db_service.get_project_statistics()
                stats_data['projects'] = project_stats
            
            if 'ticket' in intent or 'ticket' in message.lower():
                ticket_stats = self.db_service.get_ticket_statistics()
                stats_data['tickets'] = ticket_stats
            
            if not stats_data:
                # Get all statistics
                stats_data = {
                    'projects': self.db_service.get_project_statistics(),
                    'tickets': self.db_service.get_ticket_statistics()
                }
            
            stats_text = json.dumps(stats_data, indent=2, default=str)
            
            prompt = FRONTLINE_STATISTICS_PROMPT.format(
                statistics_data=stats_text,
                user_question=message
            )
            
            return self._generate_ai_response(prompt, stats_text)
            
        except Exception as e:
            logger.error(f"Statistics query error: {e}")
            return self._fallback_response(f"I encountered an error gathering statistics: {str(e)}")
    
    def _handle_database_query(self, user: User, message: str) -> Dict[str, Any]:
        """Handle database analysis queries"""
        if not self.db_service:
            return self._fallback_response("Database service is not available.")
        
        try:
            # Search database intelligently
            search_results = self.db_service.search_payperproject_data(message)
            
            # Format results for AI analysis
            analysis_text = self._format_analysis_results(search_results)
            
            if not analysis_text or analysis_text.strip() == "No relevant data found.":
                return self._generate_ai_response(
                    FRONTLINE_GENERAL_QUERY_PROMPT.format(user_question=message),
                    "I couldn't find specific data matching your query. Could you provide more details about what you're looking for?"
                )
            
            # Generate professional response using AI
            prompt = FRONTLINE_DATABASE_ANALYSIS_PROMPT.format(
                analysis_results=analysis_text,
                user_question=message
            )
            
            return self._generate_ai_response(prompt, analysis_text)
            
        except Exception as e:
            logger.error(f"Database query error: {e}")
            return self._fallback_response(f"I encountered an error analyzing the database: {str(e)}")
    
    def _handle_project_query(self, user: User, message: str) -> Dict[str, Any]:
        """Handle project-related queries"""
        if not self.db_service:
            return self._fallback_response("Database service is not available.")
        
        message_lower = message.lower()
        
        # Check if user wants to list all projects
        is_list_query = any(phrase in message_lower for phrase in [
            'list', 'show', 'display', 'all projects', 'every project', 
            'get all', 'see all', 'view all'
        ])
        
        try:
            # Get project data
            projects = self.db_service.get_all_projects()
            project_stats = self.db_service.get_project_statistics()
            
            # If it's a list query, provide beautifully formatted list directly
            if is_list_query and projects:
                # Header with summary
                response_lines = [
                    "=" * 70,
                    f"📊 PAYPERPROJECT - ALL PROJECTS OVERVIEW",
                    "=" * 70,
                    "",
                    f"📈 **Total Projects in System: {len(projects)}**",
                    ""
                ]
                
                # Add quick statistics
                total = project_stats.get('total_projects', len(projects))
                running = project_stats.get('running_projects', 0)
                completed = project_stats.get('completed_projects', 0)
                by_status = project_stats.get('by_status', {})
                
                response_lines.extend([
                    "📊 **QUICK STATISTICS:**",
                    f"   ✅ Running/Active Projects: {running}",
                    f"   ✔️  Completed Projects: {completed}",
                    f"   📋 Total Projects: {total}",
                    ""
                ])
                
                # Group by status for better organization
                projects_by_status = {}
                for project in projects:
                    status = str(project.get('status') or project.get('Status') or 'Unknown').strip()
                    if status not in projects_by_status:
                        projects_by_status[status] = []
                    projects_by_status[status].append(project)
                
                # Status icons mapping
                status_icons = {
                    'running': '🟢',
                    'active': '🟢',
                    'in_progress': '🟡',
                    'in progress': '🟡',
                    'completed': '✅',
                    'done': '✅',
                    'finished': '✅',
                    'pending': '⏳',
                    'on hold': '⏸️',
                    'cancelled': '❌',
                    'cancelled': '❌',
                    'new': '🆕',
                    'planning': '📝'
                }
                
                # Display projects grouped by status with beautiful formatting
                status_order = ['running', 'active', 'in_progress', 'in progress', 'new', 'planning', 'pending', 'on hold', 'completed', 'done', 'finished', 'cancelled']
                
                # Sort statuses: prioritize common statuses, then alphabetically
                sorted_statuses = sorted(
                    projects_by_status.keys(),
                    key=lambda s: (
                        status_order.index(s.lower()) if s.lower() in status_order else 999,
                        s.lower()
                    )
                )
                
                for status in sorted_statuses:
                    status_projects = projects_by_status[status]
                    status_lower = status.lower()
                    icon = status_icons.get(status_lower, '📌')
                    
                    response_lines.extend([
                        "",
                        "-" * 70,
                        f"{icon} **{status.upper().replace('_', ' ')}** ({len(status_projects)} projects)",
                        "-" * 70,
                        ""
                    ])
                    
                    # Display projects with clear formatting
                    for idx, project in enumerate(status_projects[:25], 1):  # Show up to 25 per status
                        title = project.get('title') or project.get('Title') or project.get('name') or 'Untitled Project'
                        project_id = project.get('id') or project.get('Id') or 'N/A'
                        
                        # Get budget information
                        budget_min = project.get('budget_min') or project.get('BudgetMin') or project.get('budget') or None
                        budget_max = project.get('budget_max') or project.get('BudgetMax') or None
                        budget_str = ""
                        if budget_min:
                            if budget_max and str(budget_max) != str(budget_min):
                                budget_str = f"💰 Budget: ${budget_min:,} - ${budget_max:,}"
                            else:
                                budget_str = f"💰 Budget: ${budget_min:,}"
                        
                        # Get deadline information
                        deadline = project.get('deadline') or project.get('Deadline') or project.get('due_date') or None
                        deadline_str = ""
                        if deadline:
                            # Format date nicely
                            try:
                                if isinstance(deadline, str):
                                    deadline_str = f"📅 Deadline: {deadline}"
                                else:
                                    deadline_str = f"📅 Deadline: {deadline}"
                            except:
                                deadline_str = f"📅 Deadline: {deadline}"
                        
                        # Get manager information
                        manager_id = project.get('project_manager_id') or project.get('ProjectManagerId') or project.get('manager_id') or None
                        manager_str = f"👤 Manager ID: {manager_id}" if manager_id else ""
                        
                        # Get description (truncated)
                        description = project.get('description') or project.get('Description') or ''
                        desc_preview = ""
                        if description:
                            desc_short = description[:60] + "..." if len(description) > 60 else description
                            desc_preview = f"📄 {desc_short}"
                        
                        # Build project entry
                        project_entry = [
                            f"   {idx}. **{title}**",
                            f"      🆔 Project ID: {project_id}"
                        ]
                        
                        if budget_str:
                            project_entry.append(f"      {budget_str}")
                        if deadline_str:
                            project_entry.append(f"      {deadline_str}")
                        if manager_str:
                            project_entry.append(f"      {manager_str}")
                        if desc_preview:
                            project_entry.append(f"      {desc_preview}")
                        
                        response_lines.extend(project_entry)
                        response_lines.append("")  # Empty line between projects
                    
                    if len(status_projects) > 25:
                        response_lines.append(f"   ... and {len(status_projects) - 25} more {status} projects")
                        response_lines.append("")
                
                # Footer with summary and next steps
                response_lines.extend([
                    "",
                    "=" * 70,
                    "📋 **SUMMARY:**",
                    f"   • Total Projects: **{len(projects)}**",
                    f"   • Active Statuses: **{len(projects_by_status)}**",
                    f"   • Running/Active: **{running}**",
                    f"   • Completed: **{completed}**",
                    "",
                    "💡 **What would you like to do next?**",
                    "   • Ask about a specific project by ID or name",
                    "   • Get detailed statistics",
                    "   • Filter projects by status or criteria",
                    "   • View project details",
                    "",
                    "=" * 70
                ])
                
                if len(projects) > 100:
                    response_lines.insert(3, f"*Note: Showing first 100 projects. Total: {len(projects)} projects in system.*")
                
                response_text = "\n".join(response_lines)
                
                return {
                    "success": True,
                    "message": response_text,
                    "answer": response_text,
                    "projects": projects[:50],  # Include first 50 in response
                    "total_count": len(projects)
                }
            
            # For other project queries, use AI analysis
            analysis_data = {
                "total_projects": len(projects),
                "statistics": project_stats,
                "sample_projects": projects[:10]  # First 10 projects
            }
            
            analysis_text = json.dumps(analysis_data, indent=2, default=str)
            
            prompt = FRONTLINE_DATABASE_ANALYSIS_PROMPT.format(
                analysis_results=analysis_text,
                user_question=message
            )
            
            return self._generate_ai_response(prompt, analysis_text)
            
        except Exception as e:
            logger.error(f"Project query error: {e}", exc_info=True)
            # Provide helpful fallback
            if is_list_query:
                return {
                    "success": True,
                    "message": "I encountered an error retrieving the project list. Please try again in a moment, or ask me about a specific project.",
                    "answer": "Error retrieving projects"
                }
            return self._fallback_response(f"I encountered an error retrieving project information: {str(e)}")
    
    def _handle_ticket_query(self, user: User, message: str, **kwargs) -> Dict[str, Any]:
        """Handle ticket-related queries"""
        message_lower = message.lower()
        
        # Create ticket
        if "create" in message_lower:
            if self.ticket_service:
                try:
                    ticket = self.ticket_service.create_ticket(user, kwargs.get("description", message))
                    return {
                        "success": True,
                        "message": f"✅ I've successfully created ticket #{ticket.id} for you.\n\nA support agent will review your request and get back to you soon.",
                        "answer": f"Ticket #{ticket.id} created successfully."
                    }
                except Exception as e:
                    logger.error(f"Ticket creation error: {e}")
        
        # View tickets
        if any(word in message_lower for word in ["view", "my tickets", "list", "show"]):
            if self.db_service:
                try:
                    user_id = user.id
                    tickets = self.db_service.get_tickets(user_id=user_id, limit=20)
                    
                    if not tickets:
                        return {
                            "success": True,
                            "message": "You currently have no tickets in the system.",
                            "answer": "No tickets found."
                        }
                    
                    # Format tickets for AI analysis
                    tickets_text = json.dumps(tickets, indent=2, default=str)
                    
                    prompt = f"""A user asked: "{message}"

TICKET DATA:
{tickets_text}

Provide a professional summary of the user's tickets, including:
- Total number of tickets
- Status breakdown
- Recent tickets
- Any notable patterns or insights

RESPONSE:"""
                    
                    return self._generate_ai_response(prompt, tickets_text)
                except Exception as e:
                    logger.error(f"Ticket retrieval error: {e}")
        
        # General ticket query
        return self._handle_intelligent_query(user, message)
    
    def _handle_intelligent_query(self, user: User, message: str) -> Dict[str, Any]:
        """Handle queries with intelligent database search and AI analysis"""
        if not self.db_service:
            return self._generate_ai_response(
                FRONTLINE_GENERAL_QUERY_PROMPT.format(user_question=message)
            )
        
        try:
            # Intelligent search
            search_results = self.db_service.search_payperproject_data(message)
            
            # Check if we found relevant data
            has_data = any(
                search_results.get('projects') or
                search_results.get('tickets') or
                search_results.get('users') or
                search_results.get('companies')
            )
            
            if has_data:
                analysis_text = self._format_analysis_results(search_results)
                prompt = FRONTLINE_DATABASE_ANALYSIS_PROMPT.format(
                    analysis_results=analysis_text,
                    user_question=message
                )
                return self._generate_ai_response(prompt, analysis_text)
            else:
                # No specific data found, use general AI response
                return self._generate_ai_response(
                    FRONTLINE_GENERAL_QUERY_PROMPT.format(user_question=message)
                )
        except Exception as e:
            logger.error(f"Intelligent query error: {e}")
            return self._generate_ai_response(
                FRONTLINE_GENERAL_QUERY_PROMPT.format(user_question=message)
            )
    
    def _format_analysis_results(self, results: Dict[str, List]) -> str:
        """Format database results for AI analysis"""
        formatted = []
        
        if results.get('projects'):
            projects = results['projects']
            formatted.append(f"\nPROJECTS ({len(projects)} found):")
            for proj in projects[:10]:  # Top 10
                title = proj.get('title') or proj.get('name') or proj.get('Title') or 'N/A'
                status = proj.get('status') or proj.get('Status') or 'N/A'
                formatted.append(f"  - {title} (Status: {status})")
        
        if results.get('tickets'):
            tickets = results['tickets']
            formatted.append(f"\nTICKETS ({len(tickets)} found):")
            for ticket in tickets[:10]:  # Top 10
                title = ticket.get('title') or ticket.get('Title') or 'N/A'
                status = ticket.get('status') or ticket.get('Status') or 'N/A'
                formatted.append(f"  - {title} (Status: {status})")
        
        if results.get('users'):
            users = results['users']
            formatted.append(f"\nUSERS ({len(users)} found):")
            for user in users[:10]:  # Top 10
                name = user.get('name') or user.get('username') or user.get('email') or 'N/A'
                formatted.append(f"  - {name}")
        
        if results.get('companies'):
            companies = results['companies']
            formatted.append(f"\nCOMPANIES ({len(companies)} found):")
            for company in companies[:10]:  # Top 10
                name = company.get('name') or company.get('Name') or 'N/A'
                formatted.append(f"  - {name}")
        
        if not formatted:
            return "No relevant data found."
        
        return "\n".join(formatted)
    
    def _generate_ai_response(self, prompt: str, context: str = None) -> Dict[str, Any]:
        """Generate professional AI response using Groq with intelligent fallback"""
        if not self.client:
            logger.warning("Groq client not available, using intelligent fallback")
            return self._generate_fallback_from_context(prompt, context or "")
        
        try:
            messages = [
                {"role": "system", "content": FRONTLINE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            
            logger.debug(f"Calling Groq API with model: {self.model}")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1500
            )
            
            ai_response = response.choices[0].message.content
            logger.info(f"✅ Successfully generated AI response ({len(ai_response)} characters)")
            
            return {
                "success": True,
                "message": ai_response,
                "answer": ai_response
            }
            
        except Exception as e:
            logger.error(f"❌ AI response generation error: {type(e).__name__}: {e}")
            # Use intelligent fallback that extracts info from context
            return self._generate_fallback_from_context(prompt, context or "")
    
    def _generate_fallback_from_context(self, prompt: str, context: str = None) -> Dict[str, Any]:
        """Generate intelligent fallback response from context data"""
        try:
            # Try to extract information from context or prompt
            prompt_lower = prompt.lower()
            
            # Handle "what is payperproject"
            if "what is payperproject" in prompt_lower or "tell me about payperproject" in prompt_lower:
                if context and self.db_service:
                    try:
                        project_stats = self.db_service.get_project_statistics()
                        total = project_stats.get('total_projects', 0)
                        running = project_stats.get('running_projects', 0)
                        
                        response = f"""PayPerProject is an enterprise project management platform designed to help organizations manage projects, track support tickets, coordinate teams, and streamline business operations.

Based on the current database:
• Total Projects: {total}
• Currently Running/Active Projects: {running}

Key Features:
• Project Management - Create, track, and manage projects
• Ticket System - Support ticket tracking and resolution
• User & Company Management - Organize teams and organizations
• Analytics & Reporting - Track performance and insights

I can help you analyze your PayPerProject data, answer questions about projects and tickets, and provide statistics. What would you like to know more about?"""
                        return {
                            "success": True,
                            "message": response,
                            "answer": response
                        }
                    except:
                        pass
                
                # Fallback without database
                response = """PayPerProject is an enterprise project management platform that helps organizations:
• Manage and track projects
• Handle support tickets
• Coordinate teams and resources
• Generate analytics and reports

I can help you with questions about your projects, tickets, users, and more. What would you like to know?"""
                return {
                    "success": True,
                    "message": response,
                    "answer": response
                }
            
            # Handle "how many projects running"
            if "how many" in prompt_lower and "project" in prompt_lower and ("running" in prompt_lower or "active" in prompt_lower):
                if self.db_service:
                    try:
                        project_stats = self.db_service.get_project_statistics()
                        running_count = project_stats.get('running_projects', 0)
                        total_count = project_stats.get('total_projects', 0)
                        by_status = project_stats.get('by_status', {})
                        
                        response = f"""Based on the PayPerProject database:

**Currently Running/Active Projects: {running_count}**

Total Projects: {total_count}

Status Breakdown:"""
                        for status, count in by_status.items():
                            response += f"\n• {status}: {count}"
                        
                        response += "\n\nWould you like more details about any specific projects?"
                        
                        return {
                            "success": True,
                            "message": response,
                            "answer": response
                        }
                    except Exception as e:
                        logger.error(f"Error getting project stats: {e}")
                
                return {
                    "success": True,
                    "message": "I'm currently unable to access the project database. Please try again in a moment.",
                    "answer": "Database temporarily unavailable"
                }
            
            # Generic fallback
            return self._fallback_response("I'm here to help! Could you rephrase your question? I can assist with PayPerProject questions, project statistics, tickets, and more.")
            
        except Exception as e:
            logger.error(f"Fallback generation error: {e}")
            return self._fallback_response("I'm here to help! Please ask me about PayPerProject, projects, tickets, or statistics.")
    
    def _fallback_response(self, message: str) -> Dict[str, Any]:
        """Fallback response when services are unavailable"""
        return {
            "success": True,
            "message": message,
            "answer": message
        }
