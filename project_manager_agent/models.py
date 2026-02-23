from django.db import models
from django.utils import timezone


class PMKnowledgeQAChat(models.Model):
    """Knowledge Q&A chat sessions for project manager. Each chat contains multiple messages."""
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='pm_knowledge_qa_chats',
        help_text='Company user who owns this chat',
    )
    title = models.CharField(max_length=255, default='Chat', help_text='Chat title (e.g. first question snippet)')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['-updated_at']
        verbose_name = 'PM Knowledge QA Chat'
        verbose_name_plural = 'PM Knowledge QA Chats'

    def __str__(self):
        return f"PM QA Chat: {self.title[:40]}... ({self.id})"


class PMKnowledgeQAChatMessage(models.Model):
    """Individual messages in a PM Knowledge QA chat."""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    chat = models.ForeignKey(
        PMKnowledgeQAChat,
        on_delete=models.CASCADE,
        related_name='messages',
        help_text='Chat this message belongs to',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(help_text='Message content')
    response_data = models.JSONField(
        null=True,
        blank=True,
        help_text='For assistant: { answer, project_id, project_title }',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['created_at']
        verbose_name = 'PM Knowledge QA Chat Message'
        verbose_name_plural = 'PM Knowledge QA Chat Messages'

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class PMProjectPilotChat(models.Model):
    """Project Pilot chat sessions for project manager. Each chat contains multiple messages."""
    company_user = models.ForeignKey(
        'core.CompanyUser',
        on_delete=models.CASCADE,
        related_name='pm_project_pilot_chats',
        help_text='Company user who owns this chat',
    )
    title = models.CharField(max_length=255, default='Chat', help_text='Chat title (e.g. first request snippet)')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['-updated_at']
        verbose_name = 'PM Project Pilot Chat'
        verbose_name_plural = 'PM Project Pilot Chats'

    def __str__(self):
        return f"PM Pilot Chat: {self.title[:40]}... ({self.id})"


class PMProjectPilotChatMessage(models.Model):
    """Individual messages in a PM Project Pilot chat."""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    chat = models.ForeignKey(
        PMProjectPilotChat,
        on_delete=models.CASCADE,
        related_name='messages',
        help_text='Chat this message belongs to',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(help_text='Message content (user request or assistant answer)')
    response_data = models.JSONField(
        null=True,
        blank=True,
        help_text='For assistant: { answer, action_results, cannot_do, project_id, project_title, from_file, file_name }',
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'project_manager_agent'
        ordering = ['created_at']
        verbose_name = 'PM Project Pilot Chat Message'
        verbose_name_plural = 'PM Project Pilot Chat Messages'

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."
