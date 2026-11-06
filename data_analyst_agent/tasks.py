"""AI Data Analyst background work: reading a big uploaded .sql dump into its SQLite copy (7 Nov 2026)."""
from celery import shared_task

from .sources import DUMP_SECONDS


@shared_task(name='data_analyst_agent.load_dump', soft_time_limit=DUMP_SECONDS, time_limit=DUMP_SECONDS + 120)
def load_dump(source_id):
    from .models import DataSource
    from .sources import load_dump as read_into_copy
    source = DataSource.objects.filter(pk=source_id, status=DataSource.STATUS_LOADING).first()
    if source is None:
        return {'skipped': 'not loading'}
    ok, message = read_into_copy(source)
    return {'ok': ok, 'message': message[:300]}
