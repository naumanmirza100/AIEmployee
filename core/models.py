from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


class Project(models.Model):
    """Project model for managing projects"""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_projects')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planning')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class Task(models.Model):
    """Task model for managing individual tasks"""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('review', 'Review'),
        ('done', 'Done'),
        ('blocked', 'Blocked'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    due_date = models.DateTimeField(null=True, blank=True)
    estimated_hours = models.FloatField(null=True, blank=True)
    actual_hours = models.FloatField(null=True, blank=True)
    progress_percentage = models.IntegerField(null=True, blank=True, default=None, help_text="Manual progress percentage (0-100)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Dependencies
    depends_on = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='dependent_tasks')
    
    class Meta:
        ordering = ['priority', 'due_date', 'created_at']
    
    def __str__(self):
        return f"{self.title} - {self.project.name}"
    
    def mark_complete(self):
        """Mark task as complete"""
        self.status = 'done'
        self.completed_at = timezone.now()
        self.save()


class Subtask(models.Model):
    """Subtask model for breaking down tasks into smaller actionable items"""
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
    ]
    
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, help_text="Detailed explanation of what needs to be done")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='subtasks')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    order = models.IntegerField(default=0, help_text="Order/sequence of subtask within the task")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = 'Subtask'
        verbose_name_plural = 'Subtasks'
    
    def __str__(self):
        return f"{self.title} - {self.task.title}"
    
    def mark_complete(self):
        """Mark subtask as complete"""
        self.status = 'done'
        self.completed_at = timezone.now()
        self.save()


class TeamMember(models.Model):
    """Team member model for project teams"""
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('manager', 'Manager'),
        ('member', 'Member'),
        ('viewer', 'Viewer'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='team_memberships')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='team_members')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'project']
    
    def __str__(self):
        return f"{self.user.username} - {self.project.name}"


class Meeting(models.Model):
    """Meeting model for storing meeting information"""
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='meetings', null=True, blank=True)
    organizer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organized_meetings')
    participants = models.ManyToManyField(User, related_name='meetings')
    scheduled_at = models.DateTimeField()
    duration_minutes = models.IntegerField(default=60)
    notes = models.TextField(blank=True)
    transcript = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-scheduled_at']
    
    def __str__(self):
        return f"{self.title} - {self.scheduled_at}"


class ActionItem(models.Model):
    """Action items from meetings"""
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='action_items', null=True, blank=True)
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True, related_name='action_items')
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='action_items')
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return self.title


class Workflow(models.Model):
    """Workflow/SOP model"""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='workflows', null=True, blank=True)
    is_template = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_workflows')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class WorkflowStep(models.Model):
    """Individual steps in a workflow"""
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='steps')
    step_number = models.IntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_required = models.BooleanField(default=True)
    estimated_time_minutes = models.IntegerField(null=True, blank=True)
    
    class Meta:
        ordering = ['step_number']
        unique_together = ['workflow', 'step_number']
    
    def __str__(self):
        return f"{self.workflow.name} - Step {self.step_number}: {self.title}"


class WorkflowExecution(models.Model):
    """Track workflow executions"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='executions')
    executed_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workflow_executions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    context_data = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"{self.workflow.name} - {self.executed_by.username}"


class Analytics(models.Model):
    """Store analytics data for projects"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='analytics')
    metric_name = models.CharField(max_length=100)
    metric_value = models.FloatField()
    metric_data = models.JSONField(default=dict, blank=True)
    calculated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-calculated_at']
    
    def __str__(self):
        return f"{self.project.name} - {self.metric_name}"


class UserProfile(models.Model):
    """User profile with role information"""
    ROLE_CHOICES = [
        ('project_manager', 'Project Manager'),
        ('team_member', 'Team Member'),
        ('developer', 'Developer'),
        ('viewer', 'Viewer'),
        ('recruitment_agent', 'Recruitment Agent'),
        ('marketing_agent', 'Marketing Agent'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='team_member')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
    
    def is_project_manager(self):
        """Check if user is a project manager"""
        return self.role == 'project_manager'
    
    def is_recruitment_agent(self):
        """Check if user is a recruitment agent"""
        return self.role == 'recruitment_agent'
    
    def is_marketing_agent(self):
        """Check if user is a marketing agent"""
        return self.role == 'marketing_agent'
    
    def is_developer(self):
        """Check if user is a developer"""
        return self.role == 'developer'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a user profile when a new user is created"""
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save user profile when user is saved"""
    try:
        # Try to get the profile without triggering a query if it doesn't exist
        profile = UserProfile.objects.get(user=instance)
        profile.save()
    except UserProfile.DoesNotExist:
        # Profile doesn't exist yet, create it
        UserProfile.objects.get_or_create(user=instance)
    except Exception:
        # If there's any other error (like table doesn't exist), just pass
        # This can happen during initial migrations
        pass
