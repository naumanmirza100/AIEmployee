from django.contrib import admin
from .models import (
    Project, Task, Subtask, TeamMember, Meeting, 
    ActionItem, Workflow, WorkflowStep, WorkflowExecution, Analytics, UserProfile
)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'status', 'priority', 'created_at']
    list_filter = ['status', 'priority', 'created_at']
    search_fields = ['name', 'description']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'project', 'assignee', 'status', 'priority', 'due_date']
    list_filter = ['status', 'priority', 'project']
    search_fields = ['title', 'description']


@admin.register(Subtask)
class SubtaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'task', 'status', 'order', 'created_at']
    list_filter = ['status', 'task__project']
    search_fields = ['title', 'description']
    ordering = ['task', 'order', 'created_at']


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ['user', 'project', 'role', 'joined_at']
    list_filter = ['role', 'project']


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ['title', 'organizer', 'scheduled_at', 'project']
    list_filter = ['scheduled_at', 'project']


@admin.register(ActionItem)
class ActionItemAdmin(admin.ModelAdmin):
    list_display = ['title', 'assignee', 'status', 'due_date']
    list_filter = ['status', 'meeting']


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'is_template', 'created_by']
    list_filter = ['is_template', 'project']


@admin.register(WorkflowStep)
class WorkflowStepAdmin(admin.ModelAdmin):
    list_display = ['workflow', 'step_number', 'title', 'is_required']
    list_filter = ['workflow', 'is_required']


@admin.register(WorkflowExecution)
class WorkflowExecutionAdmin(admin.ModelAdmin):
    list_display = ['workflow', 'executed_by', 'status', 'started_at']
    list_filter = ['status', 'workflow']


@admin.register(Analytics)
class AnalyticsAdmin(admin.ModelAdmin):
    list_display = ['project', 'metric_name', 'metric_value', 'calculated_at']
    list_filter = ['metric_name', 'project']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'created_at']
    list_filter = ['role', 'created_at']
    search_fields = ['user__username', 'user__email']
