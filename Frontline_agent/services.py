"""
Frontline Agent Services
Knowledge Service and Ticket Automation Service
"""
import logging
from typing import List, Dict, Optional
from django.contrib.auth.models import User

from .database_service import PayPerProjectDatabaseService

logger = logging.getLogger(__name__)


class KnowledgeService:
    """
    Knowledge Service for answering user questions using PayPerProject database.
    Provides intelligent search and analysis capabilities.
    """
    
    def __init__(self):
        try:
            self.db = PayPerProjectDatabaseService()
            logger.info("✅ KnowledgeService initialized")
        except Exception as e:
            logger.error(f"❌ KnowledgeService initialization failed: {e}")
            self.db = None
    
    def get_all_projects(self) -> List[Dict]:
        """Fetch all projects from database"""
        if not self.db:
            return []
        try:
            return self.db.get_all_projects()
        except Exception as e:
            logger.error(f"Error fetching all projects: {e}")
            return []
    
    def get_project_info(self, project_id: int) -> Optional[Dict]:
        """Fetch a single project by ID"""
        if not self.db:
            return None
        try:
            return self.db.get_project_by_id(project_id)
        except Exception as e:
            logger.error(f"Error fetching project {project_id}: {e}")
            return None
    
    def search(self, question: str) -> Optional[str]:
        """
        Search and answer questions about PayPerProject.
        Returns None if no relevant answer found (so orchestrator can handle it).
        """
        if not self.db:
            return None
        
        question_lower = question.lower()
        
        try:
            # Get all projects
            projects = self.get_all_projects()
            if not projects:
                return None
            
            # Try to find project ID in question
            project_id = None
            for word in question_lower.split():
                if word.isdigit():
                    try:
                        project_id = int(word)
                        break
                    except ValueError:
                        continue
            
            # If project ID found, get specific project info
            if project_id:
                project = self.get_project_info(project_id)
                if not project:
                    return None
                
                # Answer based on keywords
                if "status" in question_lower:
                    return f"Project '{project.get('title', 'N/A')}' status: {project.get('status', 'N/A')}"
                
                if "budget" in question_lower:
                    budget_min = project.get('budget_min', 'N/A')
                    budget_max = project.get('budget_max', 'N/A')
                    return f"Project '{project.get('title', 'N/A')}' budget: {budget_min} - {budget_max}"
                
                if "deadline" in question_lower:
                    return f"Project '{project.get('title', 'N/A')}' deadline: {project.get('deadline', 'N/A')}"
                
                if "priority" in question_lower:
                    return f"Project '{project.get('title', 'N/A')}' priority: {project.get('priority', 'N/A')}"
                
                if "manager" in question_lower:
                    return f"Project '{project.get('title', 'N/A')}' manager ID: {project.get('project_manager_id', 'N/A')}"
                
                if "description" in question_lower:
                    return project.get("description", "No description available.")
            
            # If no project ID, give summary for general project questions
            if "project" in question_lower or "payperproject" in question_lower:
                total_count = len(projects)
                running_count = sum(1 for p in projects if p.get("status") == "running" or p.get("status") == "active")
                return f"PayPerProject has {total_count} total projects; {running_count} are currently running/active."
            
            # No relevant answer found
            return None
            
        except Exception as e:
            logger.error(f"Error in KnowledgeService.search: {e}")
            return None


class TicketAutomationService:
    """
    Ticket Automation Service for creating and managing support tickets.
    """
    
    def __init__(self):
        logger.info("✅ TicketAutomationService initialized")
    
    def create_ticket(self, user: User, description: str):
        """
        Create a ticket for the user.
        Returns a simple Ticket object with ID.
        """
        logger.info(f"Creating ticket for user {user.id} | {description}")
        
        # Try to use Django Ticket model if available
        try:
            from .models import Ticket
            ticket = Ticket.objects.create(
                created_by=user,
                title=description[:100] if len(description) > 100 else description,
                description=description,
                status='new',
                priority='medium'
            )
            logger.info(f"✅ Ticket #{ticket.id} created successfully")
            return ticket
        except Exception as e:
            logger.warning(f"Could not create ticket via Django model: {e}")
            # Fallback: return a simple object
            class SimpleTicket:
                def __init__(self, ticket_id):
                    self.id = ticket_id
            
            return SimpleTicket(ticket_id=1)
