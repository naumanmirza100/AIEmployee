"""What a company's documents are now, for the Frontline and HR answer caches (21 Nov 2026).

Both agents keep an answer for five minutes, keyed on the question, in the memory of the process that answered it.
The cache was cleared only when a document was indexed, and that runs in the Celery worker, so the web process kept
its answers: a refund policy deleted from Frontline was still quoted, to staff and to website visitors (the test
report's Frontline 1). Putting this fingerprint in the key changes the key, in every process, as soon as a document
is added, read, removed, marked outdated or changed. One small query per question.
"""
import logging

logger = logging.getLogger(__name__)


def documents_version(model, company_id) -> str:
    """'count:indexed:outdated:last change' of `model`'s rows for the company; '' when it can't be read."""
    if not company_id:
        return ''
    from django.db.models import Count, Max, Q
    try:
        v = model.objects.filter(company_id=company_id).aggregate(
            n=Count('id'), indexed=Count('id', filter=Q(is_indexed=True)),
            outdated=Count('id', filter=Q(is_outdated=True)), last=Max('updated_at'))
    except Exception:
        logger.exception('answer cache: the documents could not be read')
        return ''
    return f"{v['n']}:{v['indexed']}:{v['outdated']}:{v['last'].isoformat() if v['last'] else ''}"
