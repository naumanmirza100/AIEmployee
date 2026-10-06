"""The company's do-not-email list (see `core.do_not_email`).

GET    company/do-not-email        the list, newest first; ?q= searches addresses.
POST   company/do-not-email        {email, note?} adds one by hand.
DELETE company/do-not-email/<id>   takes one off. Owner or admin only: it lets
                                   outreach reach that person again.
"""
import logging

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyAdmin, IsCompanyUserOnly
from core import do_not_email
from core.models import DoNotEmail

logger = logging.getLogger(__name__)

PAGE = 200
SOURCES = {'ai_sdr': 'AI SDR', 'marketing': 'Marketing', 'manual': 'Added by hand'}


def _row(entry):
    return {
        'id': entry.id,
        'email': entry.email,
        'reason': entry.reason,
        'reason_label': entry.get_reason_display(),
        'source': entry.source,
        'source_label': SOURCES.get(entry.source, entry.source or ''),
        'note': entry.note,
        'added_by': entry.added_by.full_name if entry.added_by_id else '',
        'created_at': entry.created_at.isoformat(),
    }


def _page(company_user, query=''):
    entries = DoNotEmail.objects.filter(company_id=company_user.company_id).select_related('added_by')
    total = entries.count()
    query = (query or '').strip().lower()
    if query:
        entries = entries.filter(email__contains=query)
    return {
        'entries': [_row(e) for e in entries[:PAGE]],
        'total': total,
        'shown_limit': PAGE,
        'can_remove': company_user.role in IsCompanyAdmin.ADMIN_ROLES,
    }


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_do_not_email(request):
    company_user = request.user
    if request.method == 'POST':
        email = do_not_email.clean((request.data or {}).get('email'))
        try:
            validate_email(email)
        except ValidationError:
            return Response({'status': 'error', 'message': 'Enter one valid email address.'},
                            status=status.HTTP_400_BAD_REQUEST)
        added = do_not_email.block(company_user.company_id, email, do_not_email.MANUAL, source='manual',
                                   note=str((request.data or {}).get('note') or '').strip(), added_by=company_user)
        return Response({'status': 'success', 'added': added, 'data': _page(company_user),
                         'message': f'{email} will not be emailed.' if added else f'{email} was already on the list.'},
                        status=status.HTTP_201_CREATED if added else status.HTTP_200_OK)
    return Response({'status': 'success', 'data': _page(company_user, request.query_params.get('q'))})


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_do_not_email_entry(request, entry_id):
    company_user = request.user
    if company_user.role not in IsCompanyAdmin.ADMIN_ROLES:
        return Response({'status': 'error',
                         'message': 'Only an owner or admin of the company can take an address off this list.'},
                        status=status.HTTP_403_FORBIDDEN)
    entry = DoNotEmail.objects.filter(company_id=company_user.company_id, id=entry_id).first()
    if not entry:
        return Response({'status': 'error', 'message': 'That address is not on the list.'},
                        status=status.HTTP_404_NOT_FOUND)
    do_not_email.unblock(company_user.company_id, entry.email)
    logger.info('Do-not-email: %s removed %s for company %s', company_user.id, entry.email, company_user.company_id)
    return Response({'status': 'success', 'data': _page(company_user),
                     'message': f'{entry.email} can be emailed again.'})
