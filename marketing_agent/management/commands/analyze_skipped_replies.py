"""
Analyze main-sequence replies that were wrongly skipped (interest_level='not_analyzed').
This can happen when a reply to a MAIN sequence email was processed but the old bug
(exception fallback: contact in sub_sequence => assume sub-sequence reply) caused
us to skip AI analysis.

Include replies where: (a) Reply.sub_sequence_id is null, OR (b) triggering_email
is set and points to a main-sequence email (wrongly stored as sub).

Run: python manage.py analyze_skipped_replies [--campaign-id ID] [--dry-run]
"""
from django.core.management.base import BaseCommand
from marketing_agent.models import Reply
from marketing_agent.utils.reply_analyzer import ReplyAnalyzer


def _triggering_email_is_main_sequence(reply):
    """True if reply has a triggering email and it is from a main sequence (not sub)."""
    if not reply.triggering_email or not getattr(reply.triggering_email, 'email_template_id', None):
        return False
    template = reply.triggering_email.email_template
    steps = list(template.sequence_steps.select_related('sequence').all())
    if not steps:
        return False
    return not any(s.sequence.is_sub_sequence for s in steps)


class Command(BaseCommand):
    help = 'Run AI analysis on main-sequence replies that are still not_analyzed (e.g. wrongly skipped).'

    def add_arguments(self, parser):
        parser.add_argument('--campaign-id', type=int, default=None, help='Limit to this campaign.')
        parser.add_argument('--dry-run', action='store_true', help='Only print what would be updated.')

    def handle(self, *args, **options):
        campaign_id = options.get('campaign_id')
        dry_run = options.get('dry_run', False)
        qs = Reply.objects.filter(interest_level='not_analyzed').select_related(
            'campaign', 'lead', 'contact', 'triggering_email', 'triggering_email__email_template'
        )
        if campaign_id is not None:
            qs = qs.filter(campaign_id=campaign_id)
        # Include if stored as main (sub_sequence null) OR if triggering email is main seq (wrongly marked as sub)
        to_analyze = [
            r for r in qs
            if r.sub_sequence_id is None or _triggering_email_is_main_sequence(r)
        ]
        if not to_analyze:
            self.stdout.write(self.style.SUCCESS('No main-sequence replies with not_analyzed found.'))
            return
        self.stdout.write(f'Found {len(to_analyze)} main-sequence reply/replies to analyze.')
        if dry_run:
            for r in to_analyze:
                self.stdout.write(f'  Would analyze: Reply #{r.id} {r.lead.email} subject "{r.reply_subject or ""}"')
            self.stdout.write(self.style.WARNING('DRY RUN - no changes saved.'))
            return
        analyzer = ReplyAnalyzer()
        updated = 0
        for reply in to_analyze:
            try:
                result = analyzer.analyze_reply(
                    reply_subject=reply.reply_subject or '',
                    reply_content=reply.reply_content or '',
                    campaign_name=reply.campaign.name if reply.campaign else '',
                )
                new_level = (result.get('interest_level') or 'neutral').lower()
                if new_level not in ('positive', 'negative', 'neutral', 'requested_info', 'objection', 'unsubscribe'):
                    new_level = 'neutral'
                reply.interest_level = new_level
                reply.analysis = (result.get('analysis') or '')[:2000]
                reply.save(update_fields=['interest_level', 'analysis'])
                if reply.contact_id:
                    reply.contact.reply_interest_level = new_level
                    reply.contact.save(update_fields=['reply_interest_level'])
                self.stdout.write(f'  Reply #{reply.id} {reply.lead.email}: -> {new_level}')
                updated += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Reply #{reply.id} failed: {e}'))
        self.stdout.write(self.style.SUCCESS(f'Updated {updated} reply/replies.'))
