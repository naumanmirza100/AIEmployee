"""Keep a company as a demo snapshot for the Test data page (core/demo_data.py).

    python manage.py demo_snapshot --company "Margalla Software" --key margalla --label "Margalla Software (agent demo videos)"

Secrets are blanked in the snapshot; the company itself is not changed.
"""
from django.core.management.base import BaseCommand, CommandError

from core.demo_data import make_snapshot
from core.models import Company


class Command(BaseCommand):
    help = 'Keep a company as a demo snapshot for the Test data page.'

    def add_arguments(self, parser):
        parser.add_argument('--company', required=True, help='The company name, exactly.')
        parser.add_argument('--key', required=True, help='Short name, e.g. margalla.')
        parser.add_argument('--label', default='', help='What the page calls it.')

    def handle(self, *args, **opts):
        company = Company.objects.filter(name=opts['company']).first()
        if company is None:
            raise CommandError(f'No company named {opts["company"]!r}.')
        snap = make_snapshot(company, key=opts['key'], label=opts['label'] or company.name)
        self.stdout.write(f'{snap.key}: {snap.company_name}, {snap.rows} rows, {len(bytes(snap.data)):,} bytes compressed')
