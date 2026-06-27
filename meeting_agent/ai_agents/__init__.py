from .agents_registry import ExecAgentRegistry
from .meeting_scheduling_agent import MeetingSchedulingAgent
from .meeting_notetaker_agent import MeetingNotetakerAgent
from .task_prioritization_agent import TaskPrioritizationAgent
from .calendar_planner_agent import CalendarPlannerAgent
from .document_authoring_agent import DocumentAuthoringAgent
from .proactive_notification_agent import ProactiveNotificationAgent

ExecAgentRegistry.register('meeting_scheduling', MeetingSchedulingAgent)
ExecAgentRegistry.register('meeting_notetaker', MeetingNotetakerAgent)
ExecAgentRegistry.register('task_prioritization', TaskPrioritizationAgent)
ExecAgentRegistry.register('calendar_planner', CalendarPlannerAgent)
ExecAgentRegistry.register('document_authoring', DocumentAuthoringAgent)
ExecAgentRegistry.register('proactive_notification', ProactiveNotificationAgent)

__all__ = [
    'ExecAgentRegistry',
    'MeetingSchedulingAgent',
    'MeetingNotetakerAgent',
    'TaskPrioritizationAgent',
    'CalendarPlannerAgent',
    'DocumentAuthoringAgent',
    'ProactiveNotificationAgent',
]
