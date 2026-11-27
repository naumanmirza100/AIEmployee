"""The super admin's Test data page (27 Nov 2026): add or remove the demo companies, in the background, and see their
logins, passwords and agents. See core/demo_data.py."""
import logging
import threading
from datetime import timedelta

from django.db import close_old_connections
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.permissions import IsAdmin
from core.demo_data import overview
from core.models import DemoDataRun, DemoSnapshot

logger = logging.getLogger(__name__)


def _run_payload(run):
    if run is None:
        return None
    pct = int(run.done_rows * 100 / run.total_rows) if run.total_rows else (100 if run.status == 'done' else 0)
    # The shape the page's background-work pill reads (BackgroundUploadManager's poll contract).
    return {'id': run.id, 'action': run.action, 'status': run.status,
            'processing_status': {'done': 'ready', 'failed': 'failed'}.get(run.status, 'processing'),
            'percent': pct, 'chunks_processed': run.done_rows, 'chunks_total': run.total_rows,
            'step': run.step, 'processing_error': run.error, 'started_at': run.started_at, 'finished_at': run.finished_at}


def _busy():
    """The run still going, if any. One left unfinished for two hours (a worker restarted) no longer blocks the page."""
    return DemoDataRun.objects.filter(status__in=['queued', 'running'],
                                      created_at__gte=timezone.now() - timedelta(hours=2)).first()


def _start(run):
    """On the Celery worker; in a thread here if the worker can't be reached."""
    try:
        from core.tasks import run_test_data_job
        run_test_data_job.delay(run.id)
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning('Test data: worker not reachable (%s); running in this process', exc)

    def work():
        close_old_connections()
        try:
            from core.demo_data import run_job
            run_job(run.id)
        finally:
            close_old_connections()
    threading.Thread(target=work, daemon=True).start()


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def test_data_overview(request):
    busy = _busy()
    last = DemoDataRun.objects.first()
    return Response({'status': 'success', 'snapshots': overview(), 'running': _run_payload(busy),
                     'last': _run_payload(last)})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def test_data_start(request, action):
    if action not in ('load', 'remove'):
        return Response({'status': 'error', 'message': 'Unknown action.'}, status=status.HTTP_400_BAD_REQUEST)
    if _busy() is not None:
        return Response({'status': 'error', 'message': 'Test data is already being added or removed.'},
                        status=status.HTTP_409_CONFLICT)
    keys = [k for k in (request.data.get('keys') or []) if isinstance(k, str)]
    if not DemoSnapshot.objects.exists():
        return Response({'status': 'error', 'message': 'There is no test data to add on this server yet.'},
                        status=status.HTTP_400_BAD_REQUEST)
    run = DemoDataRun.objects.create(action=action, keys=keys, started_by=request.user)
    _start(run)
    return Response({'status': 'success', 'data': _run_payload(run)}, status=status.HTTP_202_ACCEPTED)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdmin])
def test_data_run(request, run_id):
    run = DemoDataRun.objects.filter(pk=run_id).first()
    if run is None:
        return Response({'status': 'error', 'message': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'status': 'success', 'data': _run_payload(run)})
