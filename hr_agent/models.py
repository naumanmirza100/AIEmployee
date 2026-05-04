"""HR Support Agent — data model.

Design notes (why this isn't a copy of Frontline):
  * HR is **employee-centric**. Most rows are scoped by an `Employee` FK, not
    by a free-form contact email. Employees are first-class so we can join
    leave balances, performance reviews, and notifications onto them.
  * Documents have a `confidentiality` ladder (public / employee / manager /
    hr_only) and an optional `employee` FK for personal docs (offer letter,
    payslip). Retrieval gates on this — managers don't see hr_only docs,
    ICs don't see manager-comp docs, etc.
  * Workflow triggers are **lifecycle events** (`employee_hired`,
    `leave_request_submitted`, `probation_ending`, `review_due`) rather than
    Frontline's `ticket_created/updated`.
  * Meeting types are HR-specific (`performance_review`, `exit_interview`,
    `grievance_hearing`) and inherit confidentiality from the type.
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# ============================================================================
# Employee — first-class HR entity (not a Contact, not just a User)
# ============================================================================

class Employee(models.Model):
    """A person on the company's payroll. One row per (company, work_email).

    Linked optionally to a `CompanyUser` for self-service login. An employee
    can exist before their dashboard account does (offer signed → onboarding
    → account provisioned later).
    """
    EMPLOYMENT_STATUS_CHOICES = [
        ('candidate', 'Candidate (offer signed, not started)'),
        ('onboarding', 'Onboarding'),
        ('active', 'Active'),
        ('on_leave', 'On Leave'),
        ('probation', 'Probation'),
        ('notice', 'Serving Notice'),
        ('offboarded', 'Offboarded'),
    ]
    EMPLOYMENT_TYPE_CHOICES = [
        ('full_time', 'Full-time'),
        ('part_time', 'Part-time'),
        ('contract', 'Contractor'),
        ('intern', 'Intern'),
    ]

    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='employees')
    # Canonical link — every "real" employee is a Django auth.User belonging to this
    # company via UserProfile. The CompanyUser link below is kept for tenants that
    # only use dashboard logins (no separate User row).
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='hr_employee',
        help_text='Django auth.User row this employee corresponds to.',
    )
    company_user = models.OneToOneField(
        'core.CompanyUser', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hr_employee',
        help_text='Optional dashboard-login link for self-service.',
    )
    full_name = models.CharField(max_length=255)
    work_email = models.EmailField(help_text='Primary contact — unique per company.')
    personal_email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=40, blank=True, default='')

    job_title = models.CharField(max_length=160, blank=True, default='')
    department = models.CharField(max_length=120, blank=True, default='')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='direct_reports')

    employment_status = models.CharField(max_length=20, choices=EMPLOYMENT_STATUS_CHOICES, default='active')
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default='full_time')

    start_date = models.DateField(null=True, blank=True)
    probation_end_date = models.DateField(null=True, blank=True,
                                          help_text='Used by reminder agent to flag end-of-probation reviews.')
    end_date = models.DateField(null=True, blank=True, help_text='Last working day if offboarded.')
    date_of_birth = models.DateField(null=True, blank=True)
    work_anniversary_month_day = models.CharField(max_length=5, blank=True, default='',
                                                  help_text='MM-DD shortcut for the anniversary reminder agent.')

    timezone_name = models.CharField(max_length=64, default='UTC')
    custom_fields = models.JSONField(default=dict, blank=True,
                                     help_text='Tenant-specific attributes (location, cost center, etc.).')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['full_name']
        unique_together = [('company', 'work_email')]
        indexes = [
            models.Index(fields=['company', 'employment_status']),
            models.Index(fields=['company', 'department']),
            models.Index(fields=['company', 'manager']),
            models.Index(fields=['probation_end_date']),
        ]

    def __str__(self):
        return f"{self.full_name} <{self.work_email}>"


# ============================================================================
# Leave management — balance + request
# ============================================================================

class LeaveBalance(models.Model):
    """Per-(employee, leave_type) running balance. Updated by workflow steps
    on approved LeaveRequest changes; queried by Knowledge Q&A when a customer
    asks "how many vacation days do I have left?"."""
    LEAVE_TYPE_CHOICES = [
        ('vacation', 'Vacation / PTO'),
        ('sick', 'Sick'),
        ('parental', 'Parental'),
        ('bereavement', 'Bereavement'),
        ('unpaid', 'Unpaid'),
        ('other', 'Other'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_balances')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES)
    accrued_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    used_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    carried_over_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'hr_agent'
        unique_together = [('employee', 'leave_type', 'period_start')]
        indexes = [models.Index(fields=['employee', 'leave_type'])]

    @property
    def remaining(self):
        return float(self.accrued_days) + float(self.carried_over_days) - float(self.used_days)

    def __str__(self):
        return f"{self.employee_id}/{self.leave_type}: {self.remaining}"


class LeaveRequest(models.Model):
    """Employee-initiated leave request. Lifecycle: pending → approved /
    rejected / cancelled. The workflow runner reacts to status changes."""
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=20, choices=LeaveBalance.LEAVE_TYPE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    days_requested = models.DecimalField(max_digits=5, decimal_places=2)
    reason = models.TextField(blank=True, default='')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending', db_index=True)
    approver = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='leave_approvals_made')
    approval_note = models.TextField(blank=True, default='')
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['status', 'start_date']),
        ]

    def __str__(self):
        return f"{self.employee_id} · {self.leave_type} · {self.start_date}→{self.end_date} ({self.status})"


# ============================================================================
# Documents — handbooks, policies, contracts, payroll, etc.
# ============================================================================

class HRDocument(models.Model):
    """HR document (handbook, policy, offer letter, contract, payslip…).

    Confidentiality ladder enforces who can retrieve the doc via Knowledge Q&A:
      public      — anyone (e.g. job postings, code of conduct)
      employee    — any employee in the company
      manager     — managers + HR (e.g. comp grids, performance criteria)
      hr_only     — HR team only (sensitive payroll, grievance records)
    Personal documents (offer letter, payslip) link `employee` and are visible
    to that employee only, even at `confidentiality='employee'`.
    """
    DOCUMENT_TYPE_CHOICES = [
        ('handbook', 'Employee Handbook'),
        ('policy', 'Policy'),
        ('procedure', 'Procedure / SOP'),
        ('offer_letter', 'Offer Letter'),
        ('contract', 'Contract'),
        ('id_proof', 'ID / KYC Proof'),
        ('payslip', 'Payslip'),
        ('payroll', 'Payroll / Compensation'),
        ('performance_review', 'Performance Review'),
        ('leave_form', 'Leave Form'),
        ('training', 'Training Material'),
        ('benefits', 'Benefits Doc'),
        ('compliance', 'Compliance Doc'),
        ('other', 'Other'),
    ]
    FILE_FORMAT_CHOICES = [
        ('pdf', 'PDF'), ('docx', 'DOCX'), ('doc', 'DOC'),
        ('txt', 'TXT'), ('md', 'Markdown'), ('html', 'HTML'),
        ('other', 'Other'),
    ]
    PROCESSING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]
    CONFIDENTIALITY_CHOICES = [
        ('public', 'Public'),
        ('employee', 'All Employees'),
        ('manager', 'Managers + HR'),
        ('hr_only', 'HR Only'),
    ]

    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='hr_documents')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    document_type = models.CharField(max_length=24, choices=DOCUMENT_TYPE_CHOICES, default='policy')
    confidentiality = models.CharField(max_length=12, choices=CONFIDENTIALITY_CHOICES, default='employee', db_index=True)

    # Optional employee link for personal documents (offer letter, payslip).
    # When set, retrieval limits visibility to that employee + HR.
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, null=True, blank=True,
                                 related_name='personal_documents',
                                 help_text='Set when this is a per-employee document. Restricts visibility to the employee + HR.')

    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='hr_documents_uploaded')

    file_path = models.CharField(max_length=1000, help_text='Path under MEDIA_ROOT.')
    file_size = models.IntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, blank=True, default='')
    file_format = models.CharField(max_length=10, choices=FILE_FORMAT_CHOICES, default='other')
    file_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)

    document_content = models.TextField(blank=True, default='', help_text='Extracted plain text.')
    processing_status = models.CharField(max_length=20, choices=PROCESSING_STATUS_CHOICES, default='pending', db_index=True)
    processing_error = models.TextField(blank=True, default='')
    chunks_processed = models.IntegerField(default=0)
    chunks_total = models.IntegerField(default=0)
    is_indexed = models.BooleanField(default=False)
    embedding_model = models.CharField(max_length=100, blank=True, default='')

    # Auto-extracted structured fields (populated by the document agent)
    extracted_fields = models.JSONField(default=dict, blank=True,
                                        help_text='Auto-extracted key fields, e.g. {"salary": ..., "start_date": ...}.')

    # Retention — defaults vary by document_type at upload time
    # (e.g. payroll → 7 years).
    retention_days = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'document_type']),
            models.Index(fields=['company', 'confidentiality']),
            models.Index(fields=['employee', 'document_type']),
            models.Index(fields=['processing_status']),
        ]

    def __str__(self):
        return f"{self.title} [{self.document_type}]"


class HRDocumentChunk(models.Model):
    """One chunked slice of an HRDocument plus its embedding (JSON-encoded
    vector). Same shape as Frontline_agent.DocumentChunk so the same FAISS /
    JSON-scan search pipeline can be reused with minimal porting."""
    document = models.ForeignKey(HRDocument, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.IntegerField()
    chunk_text = models.TextField()
    embedding = models.TextField(null=True, blank=True,
                                 help_text='Vector embedding as JSON; nvarchar(max) on MSSQL.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['document', 'chunk_index']
        indexes = [models.Index(fields=['document', 'chunk_index'])]

    def __str__(self):
        return f"chunk {self.chunk_index} of doc {self.document_id}"


# ============================================================================
# Workflow / SOP runner — lifecycle-event-triggered automations
# ============================================================================

class HRWorkflow(models.Model):
    """Workflow definition. Trigger conditions key off HR lifecycle events
    rather than ticket events.

    Example trigger_conditions:
      {"on": "employee_hired"}
      {"on": "leave_request_submitted", "leave_type": "parental"}
      {"on": "probation_ending", "days_before": 7}
    """
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='hr_workflows')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    trigger_conditions = models.JSONField(default=dict, blank=True)
    steps = models.JSONField(default=list,
                             help_text='List of step dicts. HR-specific step types include '
                                       '`provision_account`, `assign_training`, `update_leave_balance`, '
                                       '`schedule_meeting`, plus the generic `send_email`, `branch`, `wait`.')
    requires_approval = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    timeout_seconds = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['-updated_at']

    def __str__(self):
        return self.name


class HRWorkflowExecution(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('paused', 'Paused (waiting)'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('awaiting_approval', 'Awaiting Approval'),
        ('rejected', 'Rejected'),
    ]
    workflow = models.ForeignKey(HRWorkflow, on_delete=models.SET_NULL, null=True, blank=True, related_name='executions')
    workflow_name = models.CharField(max_length=200)
    executed_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hr_workflow_executions')
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='hr_workflow_executions',
                                 help_text='The employee this execution is operating on, when applicable.')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    context_data = models.JSONField(default=dict, blank=True)
    result_data = models.JSONField(default=dict, blank=True)
    pause_state = models.JSONField(default=dict, blank=True)
    resume_at = models.DateTimeField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status', 'started_at']),
            models.Index(fields=['employee', 'status']),
        ]

    def __str__(self):
        return f"{self.workflow_name} ({self.status})"


# ============================================================================
# Meetings — typed, with confidentiality
# ============================================================================

class HRMeeting(models.Model):
    """Typed HR meeting. Some types (`exit_interview`, `grievance_hearing`)
    are private — visibility limited to participants + HR. The booking flow
    can auto-suggest slots via availability against existing rows."""
    MEETING_TYPE_CHOICES = [
        ('onboarding_orientation', 'Onboarding Orientation'),
        ('one_on_one', '1:1 with Manager'),
        ('performance_review', 'Performance Review'),
        ('mid_year_check_in', 'Mid-year Check-in'),
        ('exit_interview', 'Exit Interview'),
        ('grievance_hearing', 'Grievance Hearing'),
        ('training_session', 'Training Session'),
        ('benefits_consult', 'Benefits Consultation'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('rescheduled', 'Rescheduled'),
    ]
    VISIBILITY_CHOICES = [
        ('company', 'Company-visible'),
        ('private', 'Private (participants + HR only)'),
    ]

    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='hr_meetings')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    meeting_type = models.CharField(max_length=30, choices=MEETING_TYPE_CHOICES, default='one_on_one')
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='company')

    organizer = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='hr_meetings_organized')
    participants = models.ManyToManyField(Employee, blank=True, related_name='hr_meetings_attending')

    scheduled_at = models.DateTimeField()
    duration_minutes = models.IntegerField(default=30)
    timezone_name = models.CharField(max_length=64, default='UTC')
    meeting_link = models.URLField(blank=True, null=True)
    location = models.CharField(max_length=500, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')

    notes = models.TextField(blank=True, default='')
    transcript = models.TextField(blank=True, default='')
    action_items = models.JSONField(default=list, blank=True)

    reminder_24h_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_15m_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['company', 'scheduled_at']),
            models.Index(fields=['meeting_type', 'status']),
            models.Index(fields=['scheduled_at', 'reminder_24h_sent_at']),
            models.Index(fields=['scheduled_at', 'reminder_15m_sent_at']),
        ]

    def __str__(self):
        return f"{self.title} [{self.meeting_type}] @ {self.scheduled_at}"


# ============================================================================
# Notifications — templated, with employee-recipient option
# ============================================================================

class HRNotificationTemplate(models.Model):
    """Reusable notification template. Trigger config drives auto-creation
    on lifecycle events (mirrors Frontline's notification trigger pattern,
    plus HR-specific events like `birthday`, `work_anniversary`,
    `probation_ending`, `review_due`, `document_expiring`)."""
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('in_app', 'In-App'),
    ]
    NOTIFICATION_TYPE_CHOICES = [
        ('birthday', 'Birthday'),
        ('work_anniversary', 'Work Anniversary'),
        ('probation_ending', 'Probation Ending'),
        ('review_due', 'Review Due'),
        ('document_expiring', 'Document Expiring'),
        ('approval_pending', 'Approval Pending'),
        ('leave_request_status', 'Leave Request Status'),
        ('onboarding_step', 'Onboarding Step'),
        ('compliance_training', 'Compliance Training'),
        ('system', 'System'),
    ]
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='hr_notification_templates')
    name = models.CharField(max_length=200)
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES, default='system')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='email')
    subject = models.CharField(max_length=300, blank=True, default='')
    body = models.TextField(help_text='Use {{employee_name}}, {{event_date}}, {{document_title}} placeholders.')
    trigger_config = models.JSONField(default=dict, blank=True,
                                      help_text='e.g. {"on": "probation_ending", "days_before": 7}')
    use_llm_personalization = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.channel})"


class HRScheduledNotification(models.Model):
    """A queued / sent notification. Uses Frontline's retry/DLQ + quiet-hours
    bookkeeping shape so the same processor can be reused with table swap."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('dead_lettered', 'Dead-lettered'),
    ]
    company = models.ForeignKey('core.Company', on_delete=models.CASCADE, related_name='hr_scheduled_notifications')
    template = models.ForeignKey(HRNotificationTemplate, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='scheduled_notifications')
    recipient_employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name='hr_scheduled_notifications')
    recipient_email = models.EmailField(blank=True, default='',
                                        help_text='Falls back to recipient_employee.work_email if blank.')
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    related_leave_request = models.ForeignKey(LeaveRequest, on_delete=models.SET_NULL, null=True, blank=True,
                                              related_name='scheduled_notifications')
    related_meeting = models.ForeignKey(HRMeeting, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='scheduled_notifications')
    related_document = models.ForeignKey(HRDocument, on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='scheduled_notifications')
    context = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)

    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error = models.TextField(blank=True, null=True)
    dead_lettered_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deferred_reason = models.CharField(max_length=50, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['status', 'scheduled_at']),
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['company']),
        ]

    def __str__(self):
        return f"HRScheduledNotification {self.id} ({self.status}) @ {self.scheduled_at}"


# ============================================================================
# Knowledge Q&A — chat session + feedback (mirror of Frontline's QA models)
# ============================================================================

class HRMeetingSchedulerChat(models.Model):
    """Conversation transcript for natural-language meeting scheduling.

    Mirrors the PM agent's `MeetingSchedulerChat` shape: each chat is
    company-user-scoped, holds the back-and-forth between the user and the
    LLM scheduling agent, and lives in the sidebar of `HRMeetingScheduler`.
    """
    company_user = models.ForeignKey('core.CompanyUser', on_delete=models.CASCADE,
                                     related_name='hr_meeting_scheduler_chats')
    title = models.CharField(max_length=255, default='Meeting chat')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['-updated_at']

    def __str__(self):
        return f"HR meeting chat {self.id}: {self.title[:40]}"


class HRMeetingSchedulerChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]
    chat = models.ForeignKey(HRMeetingSchedulerChat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    response_data = models.JSONField(null=True, blank=True,
                                     help_text='Structured payload from the LLM (e.g. created meeting id, agenda).')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['created_at']


class HRKnowledgeChat(models.Model):
    """Q&A session for an employee. Multi-turn conversation context lives
    in the linked messages."""
    company_user = models.ForeignKey('core.CompanyUser', on_delete=models.CASCADE,
                                     related_name='hr_knowledge_chats')
    title = models.CharField(max_length=255, default='HR chat')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['-updated_at']

    def __str__(self):
        return f"HR chat {self.id}: {self.title[:40]}"


class HRKnowledgeChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]
    chat = models.ForeignKey(HRKnowledgeChat, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    response_data = models.JSONField(null=True, blank=True,
                                     help_text='Full QA response payload (citations, confidence) for assistant rows.')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'hr_agent'
        ordering = ['created_at']
