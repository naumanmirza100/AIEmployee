"""
Django signals for Project Manager Agent features
Handles automatic email sending and notifications on model changes.
"""

import contextvars
import logging
from contextlib import contextmanager

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Task, TaskActivityLog, Notification, CompanyModulePurchase
from .email_service import EmailService


# Initialize email service instance
_email_service = None

def get_email_service():
    """Get or create email service instance (singleton pattern)"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


# ---- several tasks to one person at once -----------------------------------
# Handing a leaver's tasks to someone reassigns them one at a time, and every
# reassignment emailed and alerted on its own: thirty tasks, thirty emails.
# Inside `one_notice_per_assignee()` the assignments are collected instead, and
# on the way out each new assignee gets one email and one alert for the lot.
# The collecting list lives in a context variable set only for the length of
# the `with` block, so it cannot leak into an ordinary assignment made elsewhere.
_assignment_batch = contextvars.ContextVar('task_assignment_batch', default=None)


@contextmanager
def one_notice_per_assignee(reason=''):
    """`reason` is a sentence for the email and alert, e.g. who the tasks came from."""
    if _assignment_batch.get() is not None:         # already collecting further out
        yield
        return
    collected = {}
    token = _assignment_batch.set(collected)
    try:
        yield
    except BaseException:
        _assignment_batch.reset(token)              # whatever was being done failed: say nothing
        raise
    _assignment_batch.reset(token)
    for assignee, tasks in collected.values():
        _tell_assignee_once(assignee, tasks, reason)


def _tell_assignee_once(assignee, tasks, reason):
    log = logging.getLogger(__name__)
    try:
        get_email_service().send_tasks_assigned_summary(assignee, tasks, reason)
    except Exception as e:
        log.error(f"Failed to send the tasks-assigned summary email: {str(e)}")
    try:
        if len(tasks) == 1:
            title, message = f"New Task Assigned: {tasks[0].title}", f"You have been assigned a new task: {tasks[0].title}"
        else:
            title = f"{len(tasks)} tasks assigned to you"
            message = (reason + ' ' if reason else '') + ', '.join(t.title for t in tasks[:5]) + (
                f' and {len(tasks) - 5} more' if len(tasks) > 5 else '')
        Notification.objects.create(user=assignee, type='task_assigned', notification_type='task_assigned',
                                    title=title, message=message, link='/me/tasks', action_url='/me/tasks')
    except Exception as e:
        log.error(f"Failed to create the tasks-assigned alert: {str(e)}")


# Store old task state before save to track changes
_task_state_cache = {}

@receiver(pre_save, sender=Task)
def task_pre_save_handler(sender, instance, **kwargs):
    """
    Store old task state before save to track changes.
    """
    if instance.pk:
        try:
            old_task = Task.objects.get(pk=instance.pk)
            _task_state_cache[instance.pk] = {
                'assignee_id': old_task.assignee_id,
                'status': old_task.status,
                'priority': old_task.priority,
                'due_date': old_task.due_date,
            }
        except Task.DoesNotExist:
            _task_state_cache[instance.pk] = None


@receiver(post_save, sender=Task)
def task_post_save_handler(sender, instance, created, **kwargs):
    """
    Handle task creation and updates.
    - Send email when task is assigned
    - Create activity log entries
    - Create in-app notifications
    """
    # Skip if this is a raw save (e.g., during fixtures loading)
    if kwargs.get('raw', False):
        return
    
    email_service = get_email_service()
    
    # Get old state from cache
    old_state = _task_state_cache.pop(instance.pk, None) if instance.pk else None
    assignee_changed = False
    
    if created:
        assignee_changed = instance.assignee_id is not None
    elif old_state:
        assignee_changed = old_state['assignee_id'] != instance.assignee_id
    
    # Send email when task is assigned (new assignment or reassignment)
    batch = _assignment_batch.get()
    if instance.assignee and (created or assignee_changed) and batch is not None:
        # Part of a hand-over: told once, at the end (one_notice_per_assignee).
        batch.setdefault(instance.assignee_id, (instance.assignee, []))[1].append(instance)
    elif instance.assignee and (created or assignee_changed):
        # Send assignment email
        try:
            email_service.send_task_assignment_email(
                task=instance,
                assignee=instance.assignee
            )
        except Exception as e:
            # Log error but don't fail the save
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send task assignment email: {str(e)}")
        
        # Create in-app notification
        try:
            Notification.objects.create(
                user=instance.assignee,
                type='task_assigned',
                notification_type='task_assigned',
                title=f"New Task Assigned: {instance.title}",
                message=f"You have been assigned a new task: {instance.title}",
                # My Space's task list. This pointed at /tasks/<id>/, a page
                # that does not exist, so the alert could not be opened.
                link='/me/tasks',
                action_url='/me/tasks',
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to create task assignment notification: {str(e)}")
    
    # Create activity log for new tasks
    if created:
        try:
            TaskActivityLog.objects.create(
                task=instance,
                user=kwargs.get('request_user'),  # Passed via save() if available
                action_type='created',
                new_value=instance.title,
                details={
                    'title': instance.title,
                    'status': instance.status,
                    'priority': instance.priority,
                    'project_id': instance.project_id,
                }
            )
        except Exception:
            pass  # Don't fail if activity log creation fails
    
    # Create activity log for status changes
    elif instance.pk and old_state:
        try:
            # Status change
            if old_state['status'] != instance.status:
                TaskActivityLog.objects.create(
                    task=instance,
                    user=kwargs.get('request_user'),
                    action_type='status_changed',
                    old_value=old_state['status'],
                    new_value=instance.status,
                    details={
                        'old_status': old_state['status'],
                        'new_status': instance.status,
                    }
                )
            
            # Assignment change (already handled email/notification above, just log activity)
            if assignee_changed:
                old_assignee_id = old_state['assignee_id']
                new_assignee_id = instance.assignee_id
                try:
                    if old_assignee_id:
                        old_user = User.objects.get(pk=old_assignee_id)
                        old_assignee_name = old_user.username
                    else:
                        old_assignee_name = "Unassigned"
                    
                    if new_assignee_id:
                        new_user = User.objects.get(pk=new_assignee_id)
                        new_assignee_name = new_user.username
                    else:
                        new_assignee_name = "Unassigned"
                except User.DoesNotExist:
                    old_assignee_name = str(old_assignee_id) if old_assignee_id else "Unassigned"
                    new_assignee_name = str(new_assignee_id) if new_assignee_id else "Unassigned"
                
                TaskActivityLog.objects.create(
                    task=instance,
                    user=kwargs.get('request_user'),
                    action_type='assigned' if instance.assignee else 'unassigned',
                    old_value=old_assignee_name,
                    new_value=new_assignee_name,
                    details={
                        'old_assignee_id': old_assignee_id,
                        'new_assignee_id': new_assignee_id,
                    }
                )
            
            # Priority change
            if old_state['priority'] != instance.priority:
                TaskActivityLog.objects.create(
                    task=instance,
                    user=kwargs.get('request_user'),
                    action_type='priority_changed',
                    old_value=old_state['priority'],
                    new_value=instance.priority,
                )
            
            # Due date change
            if old_state['due_date'] != instance.due_date:
                old_due = old_state['due_date'].isoformat() if old_state['due_date'] else None
                new_due = instance.due_date.isoformat() if instance.due_date else None
                TaskActivityLog.objects.create(
                    task=instance,
                    user=kwargs.get('request_user'),
                    action_type='due_date_changed',
                    old_value=old_due,
                    new_value=new_due,
                )
            
        except Exception as e:
            # Log error but don't fail
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating activity log: {str(e)}")


@receiver(post_save, sender=CompanyModulePurchase)
def provision_agent_quota_on_purchase(sender, instance, created, **kwargs):
    """On agent purchase, auto-create AgentTokenQuota with 1M free tokens.

    Snapshots `included_tokens` from AdminPricingConfig.free_tokens_on_purchase
    so later pricing changes don't retroactively affect this customer.
    Idempotent: re-purchase/renewal leaves existing used_tokens untouched.
    """
    if kwargs.get('raw'):
        return
    if not created or instance.status != 'active':
        return
    try:
        from core.api_key_service import provision_quota_on_purchase
        provision_quota_on_purchase(instance.company, instance.module_name)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(
            "Failed to provision quota for %s/%s: %s",
            instance.company_id, instance.module_name, e,
        )


# Note: We need to connect these signals in apps.py to ensure they're loaded
# The signals will be connected in core/apps.py

