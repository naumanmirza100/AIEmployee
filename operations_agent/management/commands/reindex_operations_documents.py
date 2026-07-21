"""Re-chunk + re-embed existing Operations documents.

Useful after upgrading the chunker (e.g. adding the TOC/index filter) or after
setting up an embedding provider — already-uploaded docs get re-chunked with the
new pipeline and embedded so semantic search picks them up. Reads each doc's
stored ``parsed_text`` (no re-extraction, no LLM, no per-company key needed).

Usage:
    python manage.py reindex_operations_documents            # all docs
    python manage.py reindex_operations_documents --company 3
    python manage.py reindex_operations_documents --doc 42
    python manage.py reindex_operations_documents --failed   # only 'failed'
    python manage.py reindex_operations_documents --async    # via Celery
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Re-chunk + re-embed OperationsDocument rows from their stored text."

    def add_arguments(self, parser):
        parser.add_argument('--company', type=int, help='Restrict to one company id')
        parser.add_argument('--doc', type=int, help='Restrict to one OperationsDocument id')
        parser.add_argument('--failed', action='store_true',
                            help="Only reprocess docs with processing_status=failed")
        parser.add_argument('--async', dest='use_celery', action='store_true',
                            help='Dispatch via Celery (default: run inline)')

    def handle(self, *args, **opts):
        from operations_agent.models import OperationsDocument
        from operations_agent.tasks import reindex_operations_document, _reindex_impl

        qs = OperationsDocument.objects.all()
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
                if opts.get('use_celery') and hasattr(reindex_operations_document, 'delay'):
                    reindex_operations_document.delay(doc.id)
                    self.stdout.write(f'  queued: {doc.id} — {doc.title}')
                    ok += 1
                else:
                    result = _reindex_impl(doc.id)
                    st = (result or {}).get('status', '?')
                    chunks = (result or {}).get('chunks', 0)
                    self.stdout.write(f'  {st}: {doc.id} — {doc.title} ({chunks} chunks)')
                    if st == 'ready':
                        ok += 1
                    else:
                        fail += 1
            except Exception as exc:
                self.stderr.write(f'  ERROR: {doc.id} — {doc.title}: {exc}')
                fail += 1

        # Mark FAISS dirty for all affected companies so retrieval rebuilds from
        # the freshly-processed chunks on next query.
        try:
            from operations_agent.vector_store import mark_index_dirty
            company_ids = set(qs.values_list('company_id', flat=True))
            for cid in company_ids:
                if cid:
                    mark_index_dirty(cid)
            self.stdout.write(f'Marked Operations FAISS dirty for {len(company_ids)} company(ies).')
        except Exception as exc:
            self.stderr.write(f'FAISS dirty-mark failed: {exc}')

        self.stdout.write(self.style.SUCCESS(
            f'Done. success={ok} failed={fail} total={total}'
        ))
