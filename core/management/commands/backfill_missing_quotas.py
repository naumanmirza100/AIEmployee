"""
Management command: backfill missing AgentTokenQuota rows.

Finds every active CompanyModulePurchase that has no matching AgentTokenQuota
and creates the quota row using AdminPricingConfig.free_tokens_on_purchase
(or 1_000_000 as default).

Usage:
    python manage.py backfill_missing_quotas
    python manage.py backfill_missing_quotas --dry-run
"""
from django.core.management.base import BaseCommand

from core.api_key_service import provision_quota_on_purchase
from core.models import AgentTokenQuota, CompanyModulePurchase


class Command(BaseCommand):
    help = 'Backfill missing AgentTokenQuota rows for active module purchases.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would be created without writing.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        purchases = CompanyModulePurchase.objects.filter(status='active').select_related('company')
        created = skipped = 0

        for p in purchases:
            exists = AgentTokenQuota.objects.filter(
                company=p.company, agent_name=p.module_name
            ).exists()
            if exists:
                skipped += 1
                continue
            if dry:
                self.stdout.write(f'  [DRY] Would create quota: company={p.company_id} / {p.module_name}')
            else:
                provision_quota_on_purchase(p.company, p.module_name)
                self.stdout.write(f'  CREATED: company={p.company_id} / {p.module_name}')
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. Created: {created}  Already existed: {skipped}'
            + (' (dry run — nothing written)' if dry else '')
        ))
