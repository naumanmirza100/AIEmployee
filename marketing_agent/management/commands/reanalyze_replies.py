"""
Re-analyze replies that were misclassified.
- Neutral + "make it more clear" etc. -> requested_info
- Negative + "dont send again" etc. -> unsubscribe
- Negative + "dont think it can be done" etc. -> objection

Run after updating reply_analyzer.py rules to fix existing Reply and CampaignContact records.

Usage:
  python manage.py reanalyze_replies
  python manage.py reanalyze_replies --campaign 1
  python manage.py reanalyze_replies --dry-run
"""
from django.core.management.base import BaseCommand
from marketing_agent.models import Reply, CampaignContact
from marketing_agent.utils.reply_analyzer import ReplyAnalyzer

CLARIFY_PHRASES = [
    'make it more clear', 'make it clearer', 'make it mroe clear', 'make it clear',
    'please clarify', 'could you clarify', 'can you clarify', 'can you explain',
    'clarify please', 'more clear please',
]
UNSUBSCRIBE_PHRASES = [
    "don't send again", "dont send again", "do not send again", "stop sending", "stop sending me",
    "unsubscribe", "remove me", "stop emailing", "opt out",
]
OBJECTION_PHRASES = [
    "don't think it can be done", "dont think it can be done", "can't be done like this",
    "cant be done like this", "don't think this can work", "dont think this can work",
]


class Command(BaseCommand):
    help = 'Re-analyze misclassified replies (neutral->requested_info, negative->unsubscribe/objection).'

    def add_arguments(self, parser):
        parser.add_argument('--campaign', type=int, default=None, help='Limit to campaign ID')
        parser.add_argument('--dry-run', action='store_true', help='Only print what would be updated')

    def _reanalyze(self, to_fix, analyzer, dry_run, msg):
        if not to_fix:
            return 0
        self.stdout.write(msg)
        updated = 0
        for reply in to_fix:
            result = analyzer.analyze_reply(
                reply_subject=reply.reply_subject or '',
                reply_content=reply.reply_content or '',
                campaign_name=reply.campaign.name if reply.campaign else '',
            )
            new_level = (result.get('interest_level') or '').lower()
            if new_level not in ['positive', 'negative', 'neutral', 'requested_info', 'objection', 'unsubscribe']:
                continue
            if new_level == reply.interest_level:
                continue
            self.stdout.write(f'  {reply.lead.email} (Reply id={reply.id}): {reply.interest_level} -> {new_level}')
            if not dry_run:
                reply.interest_level = new_level
                reply.analysis = (result.get('analysis') or reply.analysis or '')[:2000]
                reply.save()
                if reply.contact:
                    reply.contact.reply_interest_level = new_level
                    reply.contact.save(update_fields=['reply_interest_level'])
            updated += 1
        return updated

    def handle(self, *args, **options):
        campaign_id = options.get('campaign')
        dry_run = options.get('dry_run', False)
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be saved'))

        base = Reply.objects.select_related('contact', 'campaign', 'lead')
        if campaign_id:
            base = base.filter(campaign_id=campaign_id)

        analyzer = ReplyAnalyzer()
        total_updated = 0

        # 1) Neutral + clarify -> requested_info
        neutral_qs = base.filter(interest_level='neutral')
        to_fix = []
        for reply in neutral_qs:
            combined = f"{reply.reply_subject or ''} {reply.reply_content or ''}".lower()
            if any(p in combined for p in CLARIFY_PHRASES) or ('make it' in combined and ('clear' in combined or 'clarif' in combined)):
                to_fix.append(reply)
        total_updated += self._reanalyze(to_fix, analyzer, dry_run, f'Re-analyzing {len(to_fix)} reply/replies (Neutral + clarify -> requested_info).')

        # 2) Negative + unsubscribe phrases -> unsubscribe
        negative_qs = base.filter(interest_level='negative')
        to_fix = [r for r in negative_qs if any(p in (f"{r.reply_subject or ''} {r.reply_content or ''}".lower()) for p in UNSUBSCRIBE_PHRASES)]
        total_updated += self._reanalyze(to_fix, analyzer, dry_run, f'Re-analyzing {len(to_fix)} reply/replies (Negative + "dont send again" etc. -> unsubscribe).')

        # 3) Negative + objection phrases -> objection
        to_fix = [r for r in negative_qs if any(p in (f"{r.reply_subject or ''} {r.reply_content or ''}".lower()) for p in OBJECTION_PHRASES)]
        total_updated += self._reanalyze(to_fix, analyzer, dry_run, f'Re-analyzing {len(to_fix)} reply/replies (Negative + "dont think it can be done" etc. -> objection).')

        self.stdout.write(self.style.SUCCESS(f'Updated {total_updated} reply/replies.' if not dry_run else f'Would update {total_updated} reply/replies.'))
