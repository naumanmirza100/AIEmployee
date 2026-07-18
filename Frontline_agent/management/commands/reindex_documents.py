"""Re-run parse + chunk + embed for existing Frontline documents.

Useful after upgrading the chunker (e.g. adding a TOC/index filter) so
already-uploaded docs get their junk chunks dropped and re-embedded with
the new pipeline.

Usage:
    python manage.py reindex_documents                # all docs, all companies
    python manage.py reindex_documents --company 3
    python manage.py reindex_documents --doc 42
    python manage.py reindex_documents --failed       # only 'failed' status
    python manage.py reindex_documents --async        # dispatch via Celery
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Reprocess Frontline Document rows through the chunk+embed pipeline."

    def add_arguments(self, parser):
        parser.add_argument('--company', type=int, help='Restrict to one company id')
        parser.add_argument('--doc', type=int, help='Restrict to one Document id')
        parser.add_argument('--failed', action='store_true',
                            help='Only reprocess docs with status=failed')
        parser.add_argument('--async', dest='use_celery', action='store_true',
                            help='Dispatch via Celery (default: run inline)')

    def handle(self, *args, **opts):
        from Frontline_agent.models import Document
        from Frontline_agent.tasks import process_document

        qs = Document.objects.all()
        if opts.get('company'):
            qs = qs.filter(company_id=opts['company'])
        if opts.get('doc'):
            qs = qs.filter(id=opts['doc'])
        if opts.get('failed'):
            qs = qs.filter(processing_status='failed')

        total = qs.count()
        if not total:
            self.stdout.write('No documents match the given filters.')
            return

        self.stdout.write(f'Reprocessing {total} document(s)...')
        ok = fail = 0
        for doc in qs.only('id', 'title'):
            try:
                if opts.get('use_celery'):
                    process_document.delay(doc.id)
                    self.stdout.write(f'  queued: {doc.id} — {doc.title}')
                    ok += 1
                else:
                    result = process_document(doc.id)
                    status = (result or {}).get('status', '?')
                    chunks = (result or {}).get('chunks', 0)
                    self.stdout.write(f'  {status}: {doc.id} — {doc.title} '
                                      f'({chunks} chunks)')
                    if status == 'ready':
                        ok += 1
                    else:
                        fail += 1
            except Exception as exc:
                self.stderr.write(f'  ERROR: {doc.id} — {doc.title}: {exc}')
                fail += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done. success={ok} failed={fail} total={total}'
        ))
