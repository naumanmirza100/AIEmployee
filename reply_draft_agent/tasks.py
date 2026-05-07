"""
Async tasks for Reply Draft Agent cleanup and maintenance.
"""
import logging
from celery import shared_task
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ReplyDraft, ReplyDraftAttachment, InboxEmail, InboxAttachment

logger = logging.getLogger(__name__)


@shared_task(name='reply_draft_agent.tasks.delete_reply_draft_account_data')
def delete_reply_draft_account_data(user_ids, email_account_id, drop_account_row=False):
    """Async cleanup for a Reply-Draft account disconnect.

    Runs in a Celery worker so the user's "Disconnect" click returns
    instantly — the heavy CASCADE delete (drafts, inbox, attachments,
    file storage) happens in the background.

    Args:
        user_ids: Django User IDs bridged to the company.
        email_account_id: EmailAccount this run is detaching from.
        drop_account_row: When True, drop the EmailAccount row after
            data cleanup. Set by the API view only when the row has no
            other role left (is_marketing_account=False). Dual-use rows
            stay in place — marketing still owns them.
    """
    from marketing_agent.models import EmailAccount

    try:
        account = EmailAccount.objects.get(id=email_account_id)
    except EmailAccount.DoesNotExist:
        logger.warning(f'EmailAccount {email_account_id} not found during async delete')
        return

    # 1) Delete ReplyDraftAttachments — batch and defer file cleanup
    logger.info(f'Starting ReplyDraftAttachment cleanup for users {user_ids}...')
    reply_draft_ids = list(
        ReplyDraft.objects.filter(owner_id__in=user_ids).values_list('id', flat=True)
    )

    # Collect file paths BEFORE deleting rows (for deferred cleanup)
    draft_attachment_files = list(
        ReplyDraftAttachment.objects.filter(
            draft_id__in=reply_draft_ids
        ).values_list('file', flat=True).filter(file__isnull=False).exclude(file='')
    )

    draft_attachment_count, _ = ReplyDraftAttachment.objects.filter(
        draft_id__in=reply_draft_ids
    ).delete()
    logger.info(f'Deleted {draft_attachment_count} ReplyDraftAttachments')

    # Defer file deletion to avoid I/O blocking (batch cleanup later)
    if draft_attachment_files:
        delete_attachment_files.delay(draft_attachment_files, 'draft')

    # 2) Delete ReplyDrafts — bulk delete without per-row cascade
    logger.info(f'Starting ReplyDraft cleanup for users {user_ids}...')
    draft_count, _ = ReplyDraft.objects.filter(owner_id__in=user_ids).delete()
    logger.info(f'Deleted {draft_count} ReplyDrafts')

    # 3) Delete InboxEmails & InboxAttachments
    logger.info(f'Starting InboxEmail cleanup for account {account.email}...')

    # Collect file paths BEFORE deleting (for deferred cleanup)
    inbox_attachment_files = list(
        InboxAttachment.objects.filter(
            inbox_email__email_account=account
        ).values_list('file', flat=True).filter(file__isnull=False).exclude(file='')
    )

    email_count, _ = InboxEmail.objects.filter(email_account=account).delete()
    logger.info(f'Deleted {email_count} InboxEmails (+ cascaded InboxAttachments)')

    # Defer file deletion
    if inbox_attachment_files:
        delete_attachment_files.delay(inbox_attachment_files, 'inbox')

    # 4) Drop the EmailAccount row itself, if the API view determined
    # neither role wants it anymore. We do this LAST and inside the
    # task so the synchronous DELETE endpoint never has to wait for
    # the cascade — the CASCADE chain was the dominant cost of the
    # endpoint before this refactor.
    if drop_account_row:
        try:
            EmailAccount.objects.filter(pk=account.pk).delete()
            logger.info(f'Dropped EmailAccount row {account.id} ({account.email})')
        except Exception as exc:
            logger.warning(f'Failed to drop EmailAccount {account.id}: {exc}')

    logger.info(
        f'Account {account.email} disconnected. '
        f'Deleted: {draft_attachment_count} draft attachments, '
        f'{draft_count} drafts, {email_count} emails. '
        f'File cleanup scheduled asynchronously.'
    )


@shared_task(name='reply_draft_agent.tasks.delete_attachment_files')
def delete_attachment_files(file_paths, attachment_type='draft'):
    """
    Async task to delete attachment files in batches.
    
    Runs separately from DB deletions to avoid I/O blocking the main task.
    Batches file deletions and handles errors gracefully.
    
    Args:
        file_paths: List of file paths/names to delete
        attachment_type: 'draft' or 'inbox' (for logging)
    """
    from django.core.files.storage import default_storage
    
    if not file_paths:
        return
    
    deleted = 0
    errors = 0
    
    # Batch delete in groups of 100 to manage memory
    batch_size = 100
    for i in range(0, len(file_paths), batch_size):
        batch = file_paths[i:i+batch_size]
        for file_name in batch:
            if not file_name:
                continue
            try:
                # Check if file still exists and delete it
                if default_storage.exists(file_name):
                    default_storage.delete(file_name)
                    deleted += 1
            except Exception as e:
                logger.warning(
                    f'Failed to delete {attachment_type} attachment {file_name}: {e}'
                )
                errors += 1
    
    logger.info(
        f'Cleaned up {deleted} {attachment_type} attachment files '
        f'({errors} errors, skipped {len(file_paths) - deleted - errors} missing files)'
    )
