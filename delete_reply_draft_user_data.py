"""
Delete a user's Reply Draft Agent data (InboxEmail + ReplyDraft).
The user account itself is preserved — only reply-draft-agent rows are removed.

Usage:
    python delete_reply_draft_user_data.py
"""
import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.contrib.auth.models import User
from django.db import transaction

from reply_draft_agent.models import InboxEmail, ReplyDraft


def find_user(identifier):
    return (
        User.objects.filter(email__iexact=identifier).first()
        or User.objects.filter(username__iexact=identifier).first()
    )


def delete_reply_draft_data(identifier):
    user = find_user(identifier)
    if not user:
        print(f"No user found with email or username '{identifier}'")
        return

    print(f"Found user: id={user.id}  username={user.username}  email={user.email}")

    drafts_qs = ReplyDraft.objects.filter(owner=user)
    inbox_qs = InboxEmail.objects.filter(owner=user)

    drafts_count = drafts_qs.count()
    inbox_count = inbox_qs.count()

    print(f"  ReplyDraft rows : {drafts_count}")
    print(f"  InboxEmail rows: {inbox_count}")

    if drafts_count == 0 and inbox_count == 0:
        print("Nothing to delete.")
        return

    confirm = input("Type DELETE to permanently remove these rows: ")
    if confirm != "DELETE":
        print("Operation cancelled.")
        return

    with transaction.atomic():
        drafts_qs.delete()
        inbox_qs.delete()

    print(f"Deleted {drafts_count} drafts and {inbox_count} inbox emails for {user.email}")
    print("User account itself is preserved.")


if __name__ == '__main__':
    target = "noorfatima262004@gmail.com"
    delete_reply_draft_data(target)
