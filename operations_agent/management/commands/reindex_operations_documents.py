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
        parser.add_argument('--summaries', action='store_true',
                            help='Also (or only, with --only-summaries) reindex summarised files.')
        parser.add_argument('--only-summaries', action='store_true',
                            help='Reindex ONLY summarised files, not documents.')
        parser.add_argument('--async', dest='use_celery', action='store_true',
                            help='Dispatch via Celery (default: run inline)')

    def handle(self, *args, **opts):
        from operations_agent.models import OperationsDocument
        from operations_agent.tasks import reindex_operations_document, _reindex_impl

        ok = fail = 0

        if not opts.get('only_summaries'):
            qs = OperationsDocument.objects.all()
            if opts.get('company'):
                qs = qs.filter(company_id=opts['company'])
            if opts.get('doc'):
                qs = qs.filter(id=opts['doc'])
            if opts.get('failed'):
                qs = qs.filter(processing_status='failed')

            total = qs.count()
            if total:
                self.stdout.write(f'Reprocessing {total} document(s)...')
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
                            ok += 1 if st == 'ready' else 0
                            fail += 0 if st == 'ready' else 1
                    except Exception as exc:
                        self.stderr.write(f'  ERROR: {doc.id} — {doc.title}: {exc}')
                        fail += 1
            else:
                self.stdout.write('No documents match the given filters.')

        # Summaries (opt-in) — their chunks/embeddings weren't reindexable before.
        if opts.get('summaries') or opts.get('only_summaries'):
            from operations_agent.models import OperationsDocumentSummary
            from operations_agent.tasks import _reindex_summary_impl
            sqs = OperationsDocumentSummary.objects.all()
            if opts.get('company'):
                sqs = sqs.filter(company_id=opts['company'])
            if opts.get('failed'):
                sqs = sqs.filter(processing_status='failed')
            stotal = sqs.count()
            if stotal:
                self.stdout.write(f'Reprocessing {stotal} summarised file(s)...')
                for s in sqs.only('id', 'original_filename'):
                    try:
                        r = _reindex_summary_impl(s.id)
                        st = (r or {}).get('status', '?')
                        self.stdout.write(f'  {st}: summary {s.id} — {s.original_filename} ({(r or {}).get("chunks", 0)} chunks)')
                        ok += 1 if st == 'ready' else 0
                        fail += 0 if st == 'ready' else 1
                    except Exception as exc:
                        self.stderr.write(f'  ERROR: summary {s.id}: {exc}')
                        fail += 1
            else:
                self.stdout.write('No summaries match the given filters.')

        if ok == 0 and fail == 0:
            return

        # Each _reindex_*_impl already marks the company's FAISS index dirty via
        # _invalidate_operations_indexes, so no extra pass is needed here.
        self.stdout.write(self.style.SUCCESS(f'Done. success={ok} failed={fail}'))
