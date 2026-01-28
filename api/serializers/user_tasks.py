"""
Serializers for User Tasks
"""

from rest_framework import serializers
from core.models import Task, Project


class TaskSerializer(serializers.ModelSerializer):
    """Serializer for tasks with project info"""
    project_name = serializers.CharField(source='project.name', read_only=True)
    project_id = serializers.IntegerField(source='project.id', read_only=True)
    assignee_name = serializers.SerializerMethodField()
    subtasks = serializers.SerializerMethodField()
    
    assignee_id = serializers.IntegerField(source='assignee.id', read_only=True, allow_null=True)
    
    class Meta:
        model = Task
        fields = [
            'id',
            'title',
            'description',
            'project_id',
            'project_name',
            'status',
            'priority',
            'due_date',
            'estimated_hours',
            'actual_hours',
            'progress_percentage',
            'assignee_id',
            'assignee_name',
            'created_at',
            'updated_at',
            'completed_at',
            'blocker_reason',
            'ai_reasoning',
            'subtasks',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'completed_at']
    
    def get_assignee_name(self, obj):
        """Get assignee name"""
        if obj.assignee:
            if obj.assignee.first_name or obj.assignee.last_name:
                return f"{obj.assignee.first_name} {obj.assignee.last_name}".strip()
            return obj.assignee.username
        return None
    
    def get_subtasks(self, obj):
        """Get subtasks if they exist"""
        # Check if subtasks relationship exists
        if hasattr(obj, 'subtasks'):
            try:
                subtasks = obj.subtasks.all()
                return [
                    {
                        'id': st.id,
                        'title': st.title,
                        'description': getattr(st, 'description', ''),
                        'status': getattr(st, 'status', 'todo'),
                        'order': getattr(st, 'order', 0),
                        'created_at': st.created_at.isoformat() if hasattr(st, 'created_at') and st.created_at else None,
                        'updated_at': st.updated_at.isoformat() if hasattr(st, 'updated_at') and st.updated_at else None,
                        'completed_at': st.completed_at.isoformat() if hasattr(st, 'completed_at') and st.completed_at else None,
                    }
                    for st in subtasks
                ]
            except Exception:
                return []
        return []


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for projects with task counts"""
    task_count = serializers.SerializerMethodField()
    my_task_count = serializers.SerializerMethodField()
    completed_task_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Project
        fields = [
            'id',
            'name',
            'description',
            'status',
            'priority',
            'start_date',
            'end_date',
            'deadline',
            'created_at',
            'updated_at',
            'task_count',
            'my_task_count',
            'completed_task_count',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_task_count(self, obj):
        """Get total task count for project"""
        return obj.tasks.count()
    
    def get_my_task_count(self, obj):
        """Get task count assigned to current user"""
        request = self.context.get('request')
        if request and request.user:
            return obj.tasks.filter(assignee=request.user).count()
        return 0
    
    def get_completed_task_count(self, obj):
        """Get completed task count"""
        return obj.tasks.filter(status='done').count()

