"""Super-admin API for whole-system backups (core.backups): make one, list them, download one, delete one.
A company's own backups are on its dashboard (api/views/company_backups.py), not here.

Every endpoint but the download requires IsAuthenticated + IsAdmin. The download is a plain link the browser opens,
so it can stream a backup of any size; it carries a signed ticket instead of the login, good for one backup and a few
minutes, which only an admin can get (backup_download_link).
"""
import logging

from django.core import signing
from django.http import FileResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.permissions import IsAdmin
from core import backups
from core.models import SystemBackup

logger = logging.getLogger(__name__)

_TICKET_SALT = 'system-backup-download'
_TICKET_MAX_AGE = 300   # seconds


def _serialize(backup):
    return {
        'id': backup.id,
        'status': backup.status,
        'file_name': backup.file_name,
        'size_bytes': backup.size_bytes,
        'records': (backup.summary or {}).get('records'),
        'files': (backup.summary or {}).get('files'),
        'error': backup.error,
        'created_by': backup.created_by.username if backup.created_by else '',
        'nightly': backups.is_nightly(backup),
        'created_at': backup.created_at.isoformat(),
        'finished_at': backup.finished_at.isoformat() if backup.finished_at else None,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def backups_list(request):
    """GET: every backup, newest first. POST: start a new one (built in the background; poll GET for it)."""
    if request.method == 'POST':
        try:
            backup = backups.start_backup(request.user)
        except ValueError as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=409)
        return Response({'status': 'success', 'message': 'Backup started.', 'data': _serialize(backup)}, status=201)

    backups.fail_stale_backups()
    rows = SystemBackup.objects.filter(company__isnull=True).select_related('created_by')
    return Response({'status': 'success', 'data': [_serialize(b) for b in rows]})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsAdmin])
def backup_delete(request, backup_id):
    backup = SystemBackup.objects.filter(pk=backup_id, company__isnull=True).first()
    if not backup:
        return Response({'status': 'error', 'message': 'Backup not found.'}, status=404)
    if backup.status == 'running':
        return Response({'status': 'error', 'message': 'That backup is still being made.'}, status=409)
    backups.backup_path(backup).unlink(missing_ok=True)
    backup.delete()
    return Response({'status': 'success', 'message': 'Backup deleted.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdmin])
def backup_download_link(request, backup_id):
    """A link that downloads this backup for the next few minutes."""
    backup = SystemBackup.objects.filter(pk=backup_id, status='done', company__isnull=True).first()
    if not backup or not backups.backup_path(backup).is_file():
        return Response({'status': 'error', 'message': 'That backup is not there to download.'}, status=404)
    ticket = signing.TimestampSigner(salt=_TICKET_SALT).sign(str(backup.id))
    return Response({'status': 'success', 'ticket': ticket})


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def backup_download(request, backup_id):
    try:
        signed_id = signing.TimestampSigner(salt=_TICKET_SALT).unsign(
            request.GET.get('ticket', ''), max_age=_TICKET_MAX_AGE)
    except signing.BadSignature:   # also an expired ticket
        return Response({'status': 'error', 'message': 'This download link has expired. Start it again.'}, status=403)
    if signed_id != str(backup_id):
        return Response({'status': 'error', 'message': 'This download link is not for that backup.'}, status=403)
    backup = SystemBackup.objects.filter(pk=backup_id, status='done', company__isnull=True).first()
    path = backups.backup_path(backup) if backup else None
    if not path or not path.is_file():
        return Response({'status': 'error', 'message': 'Backup not found.'}, status=404)
    logger.info('System backup %s downloaded', backup.id)
    return FileResponse(open(path, 'rb'), as_attachment=True, filename=backup.file_name,
                        content_type='application/zip')
