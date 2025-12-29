from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


class Industry(models.Model):
    """Industry categories for projects"""
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    category = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Industries'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Project(models.Model):
    """Project model for managing projects"""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('in_progress', 'In Progress'),
        ('review', 'Review'),
    ]
    
    PROJECT_TYPE_CHOICES = [
        ('website', 'Website'),
        ('mobile_app', 'Mobile App'),
        ('web_app', 'Web Application'),
        ('ai_bot', 'AI Bot'),
        ('integration', 'Integration'),
        ('marketing', 'Marketing'),
        ('database', 'Database'),
        ('consulting', 'Consulting'),
        ('ai_system', 'AI System'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_projects')
    # Additional fields from payPerProject
    project_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_projects')
    industry = models.ForeignKey(Industry, on_delete=models.SET_NULL, null=True, blank=True, related_name='projects')
    project_type = models.CharField(max_length=50, choices=PROJECT_TYPE_CHOICES, default='web_app')
    budget_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    budget_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
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
    # Additional field from payPerProject
    removed_at = models.DateTimeField(null=True, blank=True)
    
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
        ('frontline_agent', 'Frontline Agent'),
        ('marketing_agent', 'Marketing Agent'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='team_member')
    # Company association (required for project_manager role)
    company = models.ForeignKey('Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='user_profiles')
    # Additional fields from payPerProject
    company_name = models.CharField(max_length=255, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    avatar_url = models.URLField(max_length=500, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    timezone = models.CharField(max_length=50, blank=True, null=True)
    website = models.URLField(max_length=255, blank=True, null=True)
    linkedin = models.URLField(max_length=255, blank=True, null=True)
    github = models.URLField(max_length=255, blank=True, null=True)
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
    
    def is_frontline_agent(self):
        """Check if user is a frontline agent"""
        return self.role == 'frontline_agent'

    def is_marketing_agent(self):
        """Check if user is a marketing agent"""
        return self.role == 'marketing_agent'
    
    def is_developer(self):
        """Check if user is a developer"""
        return self.role == 'developer'
    
    def clean(self):
        """Validate that project_manager role has company"""
        from django.core.exceptions import ValidationError
        if self.role == 'project_manager' and not self.company:
            raise ValidationError({
                'company': 'Project Manager role requires a company association.'
            })
    
    def save(self, *args, **kwargs):
        """Override save to call clean validation"""
        self.full_clean()
        super().save(*args, **kwargs)


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


# ============================================================================
# payPerProject Additional Models - Project Management
# ============================================================================

class ProjectMilestone(models.Model):
    """Project milestone tracking"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['due_date', 'created_at']
    
    def __str__(self):
        return f"{self.title} - {self.project.name}"


class ProjectDocument(models.Model):
    """Document storage for projects"""
    DOCUMENT_TYPE_CHOICES = [
        ('requirement', 'Requirement'),
        ('deliverable', 'Deliverable'),
        ('contract', 'Contract'),
        ('other', 'Other'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='documents')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_documents')
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_type = models.CharField(max_length=50)
    file_size = models.BigIntegerField()
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.file_name} - {self.project.name}"


class ProjectApplication(models.Model):
    """Freelancer applications for projects"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('shortlisted', 'Shortlisted'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='applications')
    freelancer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_applications')
    proposal = models.TextField()
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estimated_duration = models.IntegerField(null=True, blank=True, help_text="Duration in days")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    applied_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-applied_at']
        unique_together = ['project', 'freelancer']
    
    def __str__(self):
        return f"{self.freelancer.username} - {self.project.name}"


class IndustryChallenge(models.Model):
    """Industry-specific challenges and solutions"""
    industry_slug = models.CharField(max_length=255)  # References Industry.slug
    challenge_title = models.CharField(max_length=255)
    challenge_description = models.TextField()
    solution = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.challenge_title}"


# ============================================================================
# payPerProject Additional Models - Company Management
# ============================================================================

class Company(models.Model):
    """Company/organization information"""
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=500, blank=True, null=True)
    website = models.URLField(max_length=255, blank=True, null=True)
    industry = models.CharField(max_length=100, blank=True, null=True)
    company_size = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Companies'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class CompanyUser(models.Model):
    """Users belonging to companies"""
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('recruiter', 'Recruiter'),
    ]
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='company_users')
    email = models.EmailField()
    password_hash = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='admin')
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['company', 'email']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.full_name} - {self.company.name}"


class CompanyRegistrationToken(models.Model):
    """Registration tokens for company user invitations"""
    token = models.CharField(max_length=255, unique=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='registration_tokens', null=True, blank=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_registration_tokens', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Token for {self.company.name if self.company else 'New Company'}"


# ============================================================================
# payPerProject Additional Models - Financial
# ============================================================================

class PricingPlan(models.Model):
    """Subscription pricing plans"""
    name = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='GBP')
    description = models.TextField()
    features = models.TextField()
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['price']
    
    def __str__(self):
        return self.name


class Subscription(models.Model):
    """User subscriptions to pricing plans"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('trial', 'Trial'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(PricingPlan, on_delete=models.CASCADE, related_name='subscriptions')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES)
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.plan.name}"


class Invoice(models.Model):
    """Billing invoices"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invoices')
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    invoice_number = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='GBP')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    due_date = models.DateField()
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.invoice_number} - {self.user.username}"


class PaymentMethod(models.Model):
    """Stored payment methods"""
    TYPE_CHOICES = [
        ('credit_card', 'Credit Card'),
        ('debit_card', 'Debit Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('paypal', 'PayPal'),
        ('other', 'Other'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_methods')
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    gateway_customer_id = models.CharField(max_length=255, blank=True, null=True)
    gateway_payment_method_id = models.CharField(max_length=255, blank=True, null=True)
    last_four = models.CharField(max_length=4, blank=True, null=True)
    brand = models.CharField(max_length=50, blank=True, null=True)
    expiry_month = models.PositiveSmallIntegerField(null=True, blank=True)
    expiry_year = models.PositiveSmallIntegerField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_default', '-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.get_type_display()}"


class Payment(models.Model):
    """Payment transactions"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='GBP')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    payment_gateway = models.CharField(max_length=50)
    transaction_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.transaction_id or 'No ID'} - {self.user.username}"


class Credit(models.Model):
    """User credit balance"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='credit')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.balance}"


class CreditTransaction(models.Model):
    """Credit transaction history"""
    TYPE_CHOICES = [
        ('earned', 'Earned'),
        ('spent', 'Spent'),
        ('refunded', 'Refunded'),
        ('expired', 'Expired'),
    ]
    
    credit = models.ForeignKey(Credit, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    description = models.TextField(blank=True, null=True)
    reference_type = models.CharField(max_length=50, blank=True, null=True)
    reference_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.credit.user.username} - {self.type} - {self.amount}"


class ReferralCode(models.Model):
    """Referral code system"""
    REWARD_TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('discount', 'Discount'),
        ('cash', 'Cash'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referral_codes')
    code = models.CharField(max_length=50, unique=True)
    reward_type = models.CharField(max_length=50, choices=REWARD_TYPE_CHOICES)
    reward_amount = models.DecimalField(max_digits=10, decimal_places=2)
    max_uses = models.IntegerField(null=True, blank=True)
    current_uses = models.IntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.code} - {self.user.username}"


class Referral(models.Model):
    """Referral usage tracking"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    referral_code = models.ForeignKey(ReferralCode, on_delete=models.CASCADE, related_name='referrals')
    referrer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referrals_given')
    referred_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referrals_received')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    reward_earned = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reward_paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.referrer.username} -> {self.referred_user.username}"


# ============================================================================
# payPerProject Additional Models - Content Management
# ============================================================================

class BlogTag(models.Model):
    """Blog post tags"""
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class BlogPost(models.Model):
    """Blog/article posts"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    slug = models.SlugField(max_length=255, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blog_posts')
    category = models.CharField(max_length=100)
    featured_image = models.URLField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='draft')
    published_at = models.DateTimeField(null=True, blank=True)
    views_count = models.IntegerField(default=0)
    tags = models.ManyToManyField(BlogTag, through='BlogPostTag', related_name='posts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-published_at', '-created_at']
    
    def __str__(self):
        return self.title


class BlogPostTag(models.Model):
    """Junction table for blog posts and tags"""
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='post_tags')
    tag = models.ForeignKey(BlogTag, on_delete=models.CASCADE, related_name='tag_posts')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['post', 'tag']
    
    def __str__(self):
        return f"{self.post.title} - {self.tag.name}"


class FAQ(models.Model):
    """Frequently asked questions"""
    question = models.TextField()
    answer = models.TextField()
    category = models.CharField(max_length=100, blank=True, null=True)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['display_order', 'created_at']
        verbose_name = 'FAQ'
        verbose_name_plural = 'FAQs'
    
    def __str__(self):
        return self.question[:100]


class Review(models.Model):
    """Customer reviews/testimonials"""
    client_name = models.CharField(max_length=255)
    company = models.CharField(max_length=255)
    quote = models.TextField()
    rating = models.DecimalField(max_digits=2, decimal_places=1)  # 1.0 to 5.0
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviews')
    featured = models.BooleanField(default=False)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.client_name} - {self.rating}"


# ============================================================================
# payPerProject Additional Models - Communication
# ============================================================================

class ContactMessage(models.Model):
    """Contact form submissions"""
    STATUS_CHOICES = [
        ('new', 'New'),
        ('read', 'Read'),
        ('replied', 'Replied'),
        ('archived', 'Archived'),
    ]
    
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    project_title = models.CharField(max_length=255, blank=True, null=True)
    message = models.TextField()
    attachment_path = models.CharField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.full_name} - {self.email}"


class Complaint(models.Model):
    """Customer complaints"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_review', 'In Review'),
        ('resolved', 'Resolved'),
        ('archived', 'Archived'),
    ]
    
    complaint_name = models.CharField(max_length=255, blank=True, null=True)
    complaint_email = models.EmailField()
    complaint_message = models.TextField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.complaint_email} - {self.status}"


class Consultation(models.Model):
    """Consultation requests"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='consultations')
    project_type = models.CharField(max_length=100)
    requirements = models.TextField()
    budget_range = models.CharField(max_length=100, blank=True, null=True)
    timeline = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.client.username} - {self.project_type}"


class ChatbotConversation(models.Model):
    """Chatbot conversation sessions"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('archived', 'Archived'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='chatbot_conversations')
    session_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Session {self.session_id} - {self.status}"


class ChatbotMessage(models.Model):
    """Chatbot conversation messages"""
    SENDER_TYPE_CHOICES = [
        ('user', 'User'),
        ('bot', 'Bot'),
    ]
    
    conversation = models.ForeignKey(ChatbotConversation, on_delete=models.CASCADE, related_name='messages')
    sender_type = models.CharField(max_length=50, choices=SENDER_TYPE_CHOICES)
    message = models.TextField()
    metadata = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.sender_type} - {self.message[:50]}"


# ============================================================================
# payPerProject Additional Models - User Management
# ============================================================================

class UserSession(models.Model):
    """User session management"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_sessions')
    session_token = models.CharField(max_length=255, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.session_token[:20]}..."


class UserVerification(models.Model):
    """Email/phone verification tokens"""
    TYPE_CHOICES = [
        ('email', 'Email'),
        ('phone', 'Phone'),
        ('password_reset', 'Password Reset'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verifications')
    token = models.CharField(max_length=255, unique=True)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.type}"


class UserActivityLog(models.Model):
    """Activity tracking for users"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50, blank=True, null=True)
    entity_id = models.BigIntegerField(null=True, blank=True)
    details = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.action}"


# ============================================================================
# payPerProject Additional Models - Analytics & Tracking
# ============================================================================

class AnalyticsEvent(models.Model):
    """Analytics event tracking"""
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='analytics_events')
    event_type = models.CharField(max_length=100)
    event_name = models.CharField(max_length=255)
    properties = models.TextField(blank=True, null=True)  # JSON stored as text
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.event_name} - {self.event_type}"


class PageView(models.Model):
    """Page view tracking"""
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='page_views')
    page_path = models.CharField(max_length=500)
    referrer = models.CharField(max_length=500, blank=True, null=True)
    session_id = models.CharField(max_length=255, blank=True, null=True)
    duration = models.IntegerField(null=True, blank=True, help_text="Duration in seconds")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.page_path} - {self.user.username if self.user else 'Anonymous'}"


class Notification(models.Model):
    """User notifications"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"


# ============================================================================
# payPerProject Additional Models - System
# ============================================================================

class AIPredictorSubmission(models.Model):
    """AI project predictor submissions"""
    email = models.EmailField()
    project_type = models.CharField(max_length=100)
    project_data = models.TextField()  # JSON stored as text
    predicted_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    predicted_duration = models.IntegerField(null=True, blank=True, help_text="Duration in days")
    predicted_team_size = models.IntegerField(null=True, blank=True)
    prediction_confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.email} - {self.project_type}"


class QuizResponse(models.Model):
    """Quiz/questionnaire responses"""
    email = models.EmailField()
    name = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    industry = models.CharField(max_length=100, blank=True, null=True)
    goal = models.CharField(max_length=100, blank=True, null=True)
    project_type = models.CharField(max_length=100, blank=True, null=True)
    responses = models.TextField()  # JSON stored as text
    recommendations = models.TextField(blank=True, null=True)  # JSON stored as text
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.email} - {self.project_type or 'Unknown'}"


class TalentRequest(models.Model):
    """Talent/recruitment requests"""
    EXPERIENCE_LEVEL_CHOICES = [
        ('junior', 'Junior'),
        ('mid', 'Mid'),
        ('senior', 'Senior'),
        ('expert', 'Expert'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
    ]
    
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='talent_requests')
    title = models.CharField(max_length=255)
    description = models.TextField()
    skills_required = models.TextField(blank=True, null=True)
    experience_level = models.CharField(max_length=50, choices=EXPERIENCE_LEVEL_CHOICES, blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.client.username}"


class WhiteLabelProduct(models.Model):
    """White-label product catalog"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    name = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=100)
    partner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='white_label_products')
    featured = models.BooleanField(default=False)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
