"""A company's own backups (core.backups, one company's): make one, list them, download one, delete one.

The same as Admin → Backups, for one company: its data across the agents and its uploaded files, with passwords, API
keys and sign-in tokens left out. Only an owner or admin of the company (IsCompanyAdmin.ADMIN_ROLES) gets in; a login
only ever sees its own company's. One is also made every night (core.tasks.make_company_backups).

The download is a plain link the browser opens, so it can stream a backup of any size; it carries a signed ticket for
this company and this backup, good for a few minutes, in place of the login (backup_download_link).
"""
import logging

from django.core import signing
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyAdmin, IsCompanyUserOnly
from core import backups
from core.models import SystemBackup

logger = logging.getLogger(__name__)

_TICKET_SALT = 'company-backup-download'
_TICKET_MAX_AGE = 300   # seconds


def _admins_only(request):
    """The refusal for a dashboard login that is not an owner or admin, else None. A backup holds everything the
    company has (its leads, employees, tickets, documents), so it is for the people who run the account."""
    if getattr(request.user, 'role', None) in IsCompanyAdmin.ADMIN_ROLES:
        return None
    return Response({'status': 'error', 'code': 'admins_only',
                     'message': 'Only an owner or admin of your company can make or download backups.'},
                    status=status.HTTP_403_FORBIDDEN)


def _serialize(backup):
    return {
        'id': backup.id,
        'status': backup.status,
        'file_name': backup.file_name,
        'size_bytes': backup.size_bytes,
        'records': (backup.summary or {}).get('records'),
        'files': (backup.summary or {}).get('files'),
        'error': backup.error,
        'created_by': (backup.company_user.full_name or backup.company_user.email) if backup.company_user else '',
        'nightly': backups.is_nightly(backup),
        'created_at': backup.created_at.isoformat(),
        'finished_at': backup.finished_at.isoformat() if backup.finished_at else None,
    }


def _ours(request, backup_id, **filters):
    return SystemBackup.objects.filter(pk=backup_id, company_id=request.user.company_id, **filters).first()


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_backups(request):
    """GET: the company's backups, newest first. POST: start a new one (built in the background; poll GET for it)."""
    refused = _admins_only(request)
    if refused:
        return refused
    if request.method == 'POST':
        try:
            backup = backups.start_backup(None, company=request.user.company, company_user=request.user)
        except ValueError as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=409)
        return Response({'status': 'success', 'message': 'Backup started.', 'data': _serialize(backup)}, status=201)

    backups.fail_stale_backups()
    rows = SystemBackup.objects.filter(company_id=request.user.company_id).select_related('company_user')
    return Response({'status': 'success', 'data': [_serialize(b) for b in rows]})


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_backup_delete(request, backup_id):
    refused = _admins_only(request)
    if refused:
        return refused
    backup = _ours(request, backup_id)
    if not backup:
        return Response({'status': 'error', 'message': 'Backup not found.'}, status=404)
    if backup.status == 'running':
        return Response({'status': 'error', 'message': 'That backup is still being made.'}, status=409)
    backups.backup_path(backup).unlink(missing_ok=True)
    backup.delete()
    return Response({'status': 'success', 'message': 'Backup deleted.'})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_backup_download_link(request, backup_id):
    """A link that downloads this backup for the next few minutes."""
    refused = _admins_only(request)
    if refused:
        return refused
    backup = _ours(request, backup_id, status='done')
    if not backup or not backups.backup_path(backup).is_file():
        return Response({'status': 'error', 'message': 'That backup is not there to download.'}, status=404)
    ticket = signing.TimestampSigner(salt=_TICKET_SALT).sign(f'{backup.company_id}:{backup.id}')
    return Response({'status': 'success', 'ticket': ticket})


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def company_backup_download(request, backup_id):
    try:
        signed = signing.TimestampSigner(salt=_TICKET_SALT).unsign(
            request.GET.get('ticket', ''), max_age=_TICKET_MAX_AGE)
    except signing.BadSignature:   # also an expired ticket
        return Response({'status': 'error', 'message': 'This download link has expired. Start it again.'}, status=403)
    company_id, _, signed_id = signed.partition(':')
    if signed_id != str(backup_id):
        return Response({'status': 'error', 'message': 'This download link is not for that backup.'}, status=403)
    backup = SystemBackup.objects.filter(pk=backup_id, company_id=company_id, status='done').first()
    path = backups.backup_path(backup) if backup else None
    if not path or not path.is_file():
        return Response({'status': 'error', 'message': 'Backup not found.'}, status=404)
    logger.info('Company %s backup %s downloaded', company_id, backup.id)
    return FileResponse(open(path, 'rb'), as_attachment=True, filename=backup.file_name,
                        content_type='application/zip')
