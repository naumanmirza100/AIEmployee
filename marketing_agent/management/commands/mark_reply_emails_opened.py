"""
One-time backfill: mark EmailSendHistory as 'opened' when it is the triggering_email
of a Reply but still has status 'sent' or 'delivered'. Reply implies the email was opened.

Run: python manage.py mark_reply_emails_opened
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from marketing_agent.models import EmailSendHistory, Reply


class Command(BaseCommand):
    help = "Mark sent emails that received a reply as 'opened' for accurate open rate."

    def handle(self, *args, **options):
        # Emails that triggered at least one reply but are still sent/delivered
        replied_email_ids = Reply.objects.filter(
            triggering_email_id__isnull=False
        ).values_list('triggering_email_id', flat=True).distinct()
        to_update = EmailSendHistory.objects.filter(
            id__in=replied_email_ids,
            status__in=['sent', 'delivered']
        )
        count = to_update.count()
        if count == 0:
            self.stdout.write("No sent/delivered emails with replies to update.")
            return
        now = timezone.now()
        updated = to_update.update(status='opened', opened_at=now)
        self.stdout.write(self.style.SUCCESS(f"Marked {updated} email(s) as opened (reply implies open)."))
