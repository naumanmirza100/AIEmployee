"""The one notification settings page for a dashboard login (see
`core.notification_settings`).

GET   company/notification-settings  — the topics this company uses, with the
                                       caller's bell / email choice for each.
PATCH company/notification-settings  — {topic, in_app?, email?} changes one
                                       topic; {email_paused} pauses every email.
"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core import notification_settings as ns

logger = logging.getLogger(__name__)


def _bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


@api_view(['GET', 'PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_notification_settings(request):
    company_user = request.user
    if request.method == 'PATCH':
        data = request.data or {}
        if 'email_paused' in data:
            ns.set_choice(company_user, ns.ALL, email=not _bool(data['email_paused']))
        elif data.get('topic') in ns.BY_KEY:
            if 'in_app' not in data and 'email' not in data:
                return Response({'status': 'error', 'message': 'Say what to change: in_app or email.'},
                                status=status.HTTP_400_BAD_REQUEST)
            ns.set_choice(company_user, data['topic'],
                          in_app=_bool(data['in_app']) if 'in_app' in data else None,
                          email=_bool(data['email']) if 'email' in data else None)
        else:
            return Response({'status': 'error', 'message': 'Unknown notification topic.'},
                            status=status.HTTP_400_BAD_REQUEST)
    return Response({'status': 'success', 'data': ns.page(company_user)})
