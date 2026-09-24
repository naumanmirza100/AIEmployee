"""Create the missing `Employee` rows for a company's existing logins.

    python manage.py backfill_hr_employees            # every active company
    python manage.py backfill_hr_employees --company 12

`list_employees` used to do this on every request — an existence query per
person, on a read path, which also meant a GET performed writes (HR-PERF-1 in
MDS/HR_AGENT_AUDIT.md). New logins are covered by the CompanyUser→Employee
signal; this command covers the ones that predate it.

Safe to run repeatedly: it only creates rows that are missing.
"""
from django.core.management.base import BaseCommand

from core.models import Company


class Command(BaseCommand):
    help = 'Create missing hr_agent.Employee rows for existing company logins.'

    def add_arguments(self, parser):
        parser.add_argument('--company', type=int, help='Only this company id.')

    def handle(self, *args, **options):
        from hr_agent.signals import backfill_employees_for_company

        companies = Company.objects.filter(is_active=True)
        if options.get('company'):
            companies = companies.filter(pk=options['company'])

        total = 0
        for company in companies.order_by('id'):
            created = backfill_employees_for_company(company.id)
            total += created
            if created:
                self.stdout.write(f'  {company.name}: {created} employee row(s) created')
        self.stdout.write(self.style.SUCCESS(f'Done: {total} employee row(s) created.'))
