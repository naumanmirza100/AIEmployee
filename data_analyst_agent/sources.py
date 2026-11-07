"""Testing a source, and reading an uploaded .sql dump into its SQLite copy (7 Nov 2026).

Both are used by the API (api/views/data_analyst_agent.py) and the background job (tasks.load_dump), so they live here
rather than in the view.
"""
import logging
import os
import time
from datetime import timedelta

from django.utils import timezone

from . import connectors, dumps
from .guards import Refused
from .models import DataSource

logger = logging.getLogger(__name__)

DUMP_SECONDS = 1800               # the longest a dump may take to read
STALE_LOADING = timedelta(minutes=45)


def test_source(source: DataSource):
    """Connect, read the tables, check the user. Saves what it found; returns (ok, message)."""
    source.last_checked_at = timezone.now()
    try:
        tables = connectors.read_tables(source)
        if source.kind == DataSource.KIND_SQLITE:
            tables = dumps.with_keys(tables, source.load_report)
        source.tables, source.tables_read_at = tables, timezone.now()
        source.user_can_write = connectors.can_write(source)
        source.status, source.last_error = DataSource.STATUS_READY, ''
        source.save()
        if source.kind == DataSource.KIND_MONGO:
            if not tables:
                # A name MongoDB doesn't have (they are case-sensitive) reads as an empty database: name the real ones.
                from . import mongo
                names = [n for n in mongo.database_names(source) if n != source.database]
                seen = f' This user can see: {", ".join(names[:15])}. Names are case-sensitive.' if names else ''
                return True, f'Connected, but "{source.database}" has no collection this user can read.{seen}'
            return True, f'Connected to "{source.database}". {len(tables)} collection(s) read.'
        if not tables:
            return True, 'Connected, but no tables were found that this user can read.'
        return True, f'Connected. {len(tables)} table(s) and view(s) read.'
    except Refused as exc:
        message = str(exc)
    except Exception as exc:
        message = f'Could not connect: {connectors.friendly_error(exc)}'
        logger.info('data analyst: test of source %s failed: %s', source.pk, message[:200])
    source.status, source.last_error = DataSource.STATUS_FAILED, message
    source.save()
    return False, message


def summary(report) -> str:
    """What reading a dump did, in a sentence or three."""
    tables, rows = len(report.get('tables') or []), report.get('rows') or 0
    text = (f"Read {tables} table(s) and {rows:,} row(s) from the {report.get('dialect_label', '')} dump "
            f"in {report.get('seconds', 0)} s.")
    skipped = report.get('skipped') or {}
    if skipped:
        kinds = ', '.join(list(skipped)[:4])
        text += f' Skipped {sum(skipped.values())} statement(s) that are not tables or rows ({kinds}).'
    problems = report.get('problems') or []
    if problems:
        text += f' {len(problems)} problem(s), the first: {problems[0]}'
    return text


def load_dump(source: DataSource, seconds=None):
    """Read the source's uploaded dump into a new SQLite file, delete the dump, and test the copy. (ok, message).
    On a failure nothing of the dump is kept."""
    seconds = DUMP_SECONDS if seconds is None else seconds
    raw = source.file_path
    out = connectors.new_file_path(source.company_id)
    report = dict(source.load_report or {})
    try:
        result = dumps.load(connectors.safe_path(raw), out, report.get('dialect') or 'mysql',
                            deadline=time.monotonic() + seconds)
        if not result['tables']:
            raise Refused('No table or row could be read from this file.')
    except Refused as exc:
        message = str(exc)
    except Exception as exc:
        if exc.__class__.__name__ == 'SoftTimeLimitExceeded':
            message = 'Loading stopped: the dump took too long to read. Upload a smaller one, or only the tables to ask about.'
        else:
            message = f'The dump could not be read: {str(exc)[:200]}'
            logger.exception('data analyst: dump of source %s failed', source.pk)
    else:
        report.update(result)
        connectors.remove_file(raw)
        source.file_path, source.file_size = out, os.path.getsize(out)
        source.load_report, source.status = report, DataSource.STATUS_NEW
        source.save()
        ok, message = test_source(source)
        return ok, (summary(report) if ok else message)
    connectors.remove_file(out)
    connectors.remove_file(raw)
    source.file_path, source.status, source.last_error = '', DataSource.STATUS_FAILED, message
    source.save()
    return False, message


def settle_stale(source: DataSource) -> bool:
    """A dump still "loading" long after the longest a load may take was cut short (a restart): say so. True if so."""
    if source.status != DataSource.STATUS_LOADING or source.updated_at > timezone.now() - STALE_LOADING:
        return False
    connectors.remove_file(source.file_path)
    source.file_path, source.status = '', DataSource.STATUS_FAILED
    source.last_error = 'Loading was cut short, most likely by a server restart. Upload the file again.'
    source.save()
    return True
