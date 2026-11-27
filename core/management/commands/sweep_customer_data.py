"""Clear every customer's data: every company, login, employee and everything they made (core/demo_data.py).
Kept: the super admins, the platform's own setup (agents, plans, pricing, platform keys, demo snapshots, backups
history, Stripe events), the public site (blog, FAQ, industries) and what visitors sent through it.
Uploaded files are not touched.

    python manage.py sweep_customer_data                      what it would delete (nothing is deleted)
    python manage.py sweep_customer_data --commit --yes-delete-every-customer
    --keep-company "Name" (repeatable) keeps that company and everything that belongs to it.

Take a backup first (python manage.py make_backup).
"""
from django.core.management.base import BaseCommand, CommandError

from django.contrib.auth import get_user_model

from core.demo_data import kept_users, sweep
from core.models import Company


class Command(BaseCommand):
    help = "Clear every customer's data, keeping super admins and the platform's setup."

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true')
        parser.add_argument('--yes-delete-every-customer', action='store_true', dest='sure')
        parser.add_argument('--keep-company', action='append', default=[], dest='keep',
                            help='A company to keep, by its exact name (can be given more than once).')

    def handle(self, *args, **opts):
        if opts['commit'] and not opts['sure']:
            raise CommandError('Add --yes-delete-every-customer to really delete.')
        keep = get_user_model()._base_manager.filter(pk__in=kept_users()).order_by('pk')
        self.stdout.write('Logins kept: ' + ', '.join(
            f'{u.username}{" (super admin)" if u.is_superuser else ""}' for u in keep))
        kept = []
        for name in opts['keep']:
            company = Company.objects.filter(name=name).first()
            if company is None:
                raise CommandError(f'No company named {name!r}.')
            kept.append(company)
        if kept:
            self.stdout.write('Companies kept: ' + '; '.join(f'{c.pk} {c.name}' for c in kept))
        companies = list(Company.objects.exclude(pk__in=[c.pk for c in kept]).order_by('pk').values_list('pk', 'name'))
        self.stdout.write(f'Companies {"deleted" if opts["commit"] else "to delete"} ({len(companies)}): '
                          + '; '.join(f'{pk} {name}' for pk, name in companies))
        report = sweep(commit=bool(opts['commit']), keep_companies=kept)
        total = sum(report.values())
        for label, n in sorted(report.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'{n:7d}  {label}')
        self.stdout.write(f'{total:7d}  rows in {len(report)} tables ' + ('DELETED' if opts['commit'] else '(dry run: nothing deleted)'))
