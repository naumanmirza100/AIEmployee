"""Process CVs in the background (24 Nov 2026, the test report's Recruitment 5).

Each CV is read, scored and screened by the AI, about ten seconds a file; three CVs took 7½ minutes on screen, while the
live server ends a request after 60 seconds. The screen sent three files a request to stay under that. Now the upload is
answered at once with a `CVBatch`, the work runs in the background, and the screen follows the batch: each file's step,
then the same results the request used to give. The uploader is told in the bell when it is done, so they need not
wait on the page.

Since 25 Nov 2026 the Celery worker runs it (recruitment_agent.tasks.process_cv_batch), not a thread of the web server:
a deploy restarted the web server under a running batch and stopped it. The worker finishes the task it is on before a
deploy stops it (docker-compose.yml, stop_grace_period). The files wait in MEDIA_ROOT/cv_batches/<id>/, the volume the
web server and the worker share; the web server's own temporary files are not seen by the worker. When the worker
cannot be reached, the batch runs on a thread here, as before.
"""
import logging
import shutil
import threading
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)

#: A run not finished after this long stopped with the server (a deploy, a restart): it is marked failed when read.
STALE_AFTER = timedelta(minutes=45)
STATES = ('waiting', 'reading', 'scoring', 'done', 'failed')


def serialize(batch) -> dict:
    files = list(batch.files or [])
    out = {
        'id': batch.id,
        'status': batch.status,
        'job_id': batch.job_description_id,
        'job_title': batch.job_description.title if batch.job_description_id else '',
        'files': files,
        'counts': {state: sum(1 for f in files if f.get('state') == state) for state in STATES},
        'error': batch.error,
        'created_at': batch.created_at.isoformat() if batch.created_at else None,
        'finished_at': batch.finished_at.isoformat() if batch.finished_at else None,
    }
    if batch.status in ('done', 'failed'):
        out['result'] = batch.result or {}
    return out


def settle_stale(batch):
    """A batch still "running" long after it began stopped with the server: say so, rather than wait for ever."""
    if batch.status in ('queued', 'running') and batch.created_at < timezone.now() - STALE_AFTER:
        batch.status = 'failed'
        batch.error = ('Processing stopped part-way, most likely because the server restarted. The CVs already '
                       'scored are with the candidates; upload the others again.')
        batch.finished_at = timezone.now()
        batch.save(update_fields=['status', 'error', 'finished_at'])
        shutil.rmtree(batch_folder(batch.id), ignore_errors=True)
    return batch


def batch_folder(batch_id) -> Path:
    """Where a batch's files wait to be read: on the media volume, which the worker sees too."""
    return Path(settings.MEDIA_ROOT) / 'cv_batches' / str(int(batch_id))


def start(company_user, job_desc, job_kw_list, temp_files, top_n):
    """Record the batch and start it. Under the test settings (tasks run at once) it runs in place and answers as the
    request always did; otherwise 202 with the batch, which the screen follows."""
    from recruitment_agent.models import CVBatch
    batch = CVBatch.objects.create(
        company=company_user.company, company_user=company_user, job_description=job_desc,
        files=[{'name': name, 'state': 'waiting'} for name, _ in temp_files],
        options={'job_keywords': job_kw_list or [], 'top_n': top_n})
    if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
        code, payload = run(batch.id, temp_files, reraise=True)
        return Response({**payload, 'batch_id': batch.id}, status=code)

    folder = batch_folder(batch.id)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, (_name, temp_path) in enumerate(temp_files):
        kept = folder / f'{index}{Path(temp_path).suffix[:10]}'
        shutil.move(temp_path, kept)
        paths.append(str(kept))
    batch.options = {**batch.options, 'paths': paths}
    batch.save(update_fields=['options'])

    # After the batch row is committed, so the worker can read it.
    transaction.on_commit(lambda: queue(batch.id))
    return Response({'status': 'accepted', 'message': f'{len(temp_files)} CV(s) are being read and scored.',
                     'batch': serialize(batch)}, status=status.HTTP_202_ACCEPTED)


def queue(batch_id):
    """Hand the batch to the worker; when the worker's queue cannot be reached, run it on a thread here."""
    try:
        from recruitment_agent.tasks import process_cv_batch
        process_cv_batch.delay(batch_id)
    except Exception:
        logger.exception('CV batch %s: the worker could not be reached; reading it on the web server', batch_id)

        def on_its_own_thread():
            try:
                process(batch_id)
            except Exception:
                logger.exception('CV batch %s failed', batch_id)
            finally:
                connection.close()          # the thread's own database connection

        threading.Thread(target=on_its_own_thread, name=f'cv-batch-{batch_id}', daemon=True).start()


def process(batch_id):
    """Read and score a queued batch's files (the worker's task). A batch already taken, by the same task delivered
    twice, is left alone. Returns (HTTP status, payload), or None when there was nothing to do."""
    from recruitment_agent.models import CVBatch
    if not CVBatch.objects.filter(pk=batch_id, status='queued').update(status='running', started_at=timezone.now()):
        return None
    batch = CVBatch.objects.get(pk=batch_id)
    names = [entry.get('name') or '' for entry in batch.files or []]
    paths = (batch.options or {}).get('paths') or []
    try:
        return run(batch_id, list(zip(names, paths)))
    finally:
        shutil.rmtree(batch_folder(batch_id), ignore_errors=True)


def run(batch_id, temp_files, reraise=False):
    """Process the batch's files; returns (HTTP status, payload), also kept on the batch. `reraise`: a key or quota
    problem is raised, for the request's own handler to answer, as it always was."""
    from api.views.recruitment_agent import _process_files
    from core.api_key_service import KeyServiceError
    from recruitment_agent.models import CVBatch
    batch = CVBatch.objects.select_related('company_user__company', 'job_description').get(pk=batch_id)
    batch.status, batch.started_at = 'running', timezone.now()
    batch.save(update_fields=['status', 'started_at'])
    files = list(batch.files or [])

    def progress(index, state, **fields):
        if 0 <= index < len(files):
            files[index].update({'state': state, **{k: v for k, v in fields.items() if v is not None}})
            CVBatch.objects.filter(pk=batch_id).update(files=files)

    try:
        code, payload = _process_files(batch.company_user, batch.job_description,
                                       (batch.options or {}).get('job_keywords') or None, temp_files,
                                       (batch.options or {}).get('top_n'), progress=progress)
    except KeyServiceError as exc:            # out of AI tokens, a refused key, the AI busy
        from core.drf_exceptions import key_error_status
        CVBatch.objects.filter(pk=batch_id).update(status='failed', error=exc.user_message, finished_at=timezone.now())
        if reraise:
            raise
        code, payload = key_error_status(exc), {'status': 'error', 'code': exc.reason, 'message': exc.user_message}
    except Exception:
        logger.exception('CV batch %s failed', batch_id)
        code, payload = 500, {'status': 'error', 'message': 'Processing failed. Please try again.'}
    done = code < 400
    for entry in files:                   # a file the run never reached is not left "waiting"
        if entry.get('state') in ('waiting', 'reading', 'scoring'):
            entry.update({'state': 'failed' if not done else 'done',
                          'reason': entry.get('reason') or ('' if done else payload.get('message', ''))})
    CVBatch.objects.filter(pk=batch_id).update(
        status='done' if done else 'failed', files=files, result=payload,
        error='' if done else payload.get('message', ''), finished_at=timezone.now())
    _tell_uploader(batch, files, done, payload)
    return code, payload


def _tell_uploader(batch, files, done, payload):
    """The bell, so the uploader need not keep the page open. Never raises."""
    if batch.company_user is None or getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
        return                              # in place, the request itself answers
    try:
        from core.notification_utils import notify_company_users
        job = batch.job_description.title if batch.job_description_id else 'the job'
        scored = sum(1 for f in files if f.get('state') == 'done')
        failed = sum(1 for f in files if f.get('state') == 'failed')
        if done:
            title = f'{scored} CV(s) scored for {job}'
            message = (f'{scored} CV(s) were read and scored for {job}' + (f'; {failed} could not be added' if failed
                                                                           else '') + '. ' + (payload.get('notice') or ''))
        else:
            title, message = f'Processing CVs for {job} failed', payload.get('message') or 'Please try again.'
        notify_company_users([batch.company_user], title=title[:255], message=message.strip(),
                             link='/recruitment/candidates', kind='recruitment_cv_batch',
                             severity='info' if done else 'warning', data={'batch_id': batch.id})
    except Exception:
        logger.exception('CV batch %s: the uploader could not be told', batch.id)
