"""
Re-match existing Reply records to the correct sent email (triggering_email).
Use after fixing reply matching logic so that "In reply to" shows the correct sequence step.
Run: python manage.py fix_reply_triggering_email
Optional: --campaign-id ID to limit to one campaign, --dry-run to only print changes.
"""
import logging
from django.core.management.base import BaseCommand
from marketing_agent.models import Reply
from marketing_agent.services.reply_processor import find_triggering_email

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Re-match Reply.triggering_email using subject-first matching so "In reply to" is correct.'

    def add_arguments(self, parser):
        parser.add_argument('--campaign-id', type=int, default=None, help='Only fix replies for this campaign.')
        parser.add_argument('--dry-run', action='store_true', help='Only print what would be updated.')

    def handle(self, *args, **options):
        campaign_id = options.get('campaign_id')
        dry_run = options.get('dry_run', False)
        qs = Reply.objects.filter(
            campaign__isnull=False,
            lead__isnull=False
        ).select_related('campaign', 'lead', 'triggering_email')
        if campaign_id is not None:
            qs = qs.filter(campaign_id=campaign_id)
        updated = 0
        for reply in qs:
            if not reply.reply_subject and not reply.reply_content:
                continue
            new_triggering = find_triggering_email(
                reply.campaign,
                reply.lead,
                reply.reply_subject or '',
                reply.reply_content or '',
                replied_at=reply.replied_at,
            )
            old_id = reply.triggering_email_id
            new_id = new_triggering.id if new_triggering else None
            if old_id != new_id:
                old_subj = (reply.triggering_email.subject if reply.triggering_email else None) or '(none)'
                new_subj = (new_triggering.subject if new_triggering else None) or '(none)'
                self.stdout.write(
                    f"Reply #{reply.id} {reply.lead.email}: "
                    f"triggering_email {old_id} ({old_subj}) -> {new_id} ({new_subj})"
                )
                if not dry_run and new_triggering:
                    reply.triggering_email = new_triggering
                    reply.save(update_fields=['triggering_email'])
                    updated += 1
                elif not dry_run and new_id is None:
                    reply.triggering_email = None
                    reply.save(update_fields=['triggering_email'])
                    updated += 1
        self.stdout.write(self.style.SUCCESS(f"Done. Updated {updated} reply(s)." + (" (dry-run)" if dry_run else "")))
