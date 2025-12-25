"""
AI Agents module for Project Manager AI
Contains all AI agent implementations
"""

from .base_agent import BaseAgent
from .agents_registry import AgentRegistry
from .task_prioritization_agent import TaskPrioritizationAgent
from .knowledge_qa_agent import KnowledgeQAAgent
from .project_pilot_agent import ProjectPilotAgent
from .analytics_dashboard_agent import AnalyticsDashboardAgent
from .timeline_gantt_agent import TimelineGanttAgent
from .calendar_planner_agent import CalendarPlannerAgent
from .meeting_notetaker_agent import MeetingNotetakerAgent
from .workflow_sop_agent import WorkflowSOPAgent
from .subtask_generation_agent import SubtaskGenerationAgent

# Register all agents
AgentRegistry.register("task_prioritization", TaskPrioritizationAgent)
AgentRegistry.register("knowledge_qa", KnowledgeQAAgent)
AgentRegistry.register("project_pilot", ProjectPilotAgent)
AgentRegistry.register("analytics_dashboard", AnalyticsDashboardAgent)
AgentRegistry.register("timeline_gantt", TimelineGanttAgent)
AgentRegistry.register("calendar_planner", CalendarPlannerAgent)
AgentRegistry.register("meeting_notetaker", MeetingNotetakerAgent)
AgentRegistry.register("workflow_sop", WorkflowSOPAgent)
AgentRegistry.register("subtask_generation", SubtaskGenerationAgent)

__all__ = [
    'BaseAgent',
    'AgentRegistry',
    'TaskPrioritizationAgent',
    'KnowledgeQAAgent',
    'ProjectPilotAgent',
    'AnalyticsDashboardAgent',
    'TimelineGanttAgent',
    'CalendarPlannerAgent',
    'MeetingNotetakerAgent',
    'WorkflowSOPAgent',
    'SubtaskGenerationAgent',
]

