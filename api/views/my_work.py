"""One "My work" list across the agents (see `core.my_work`).

Two addresses because there are two kinds of login, whose tokens don't
authenticate each other's endpoints: `company/my-work` for dashboard logins
and `user/my-work` for employee logins. Neither sits under an agent's prefix,
so a company that hasn't bought one agent can still load the list.
"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication, EmployeeTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core import my_work

logger = logging.getLogger(__name__)


def _respond(items):
    return Response({'status': 'success', 'data': {'items': items, 'total': len(items)}})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_my_work(request):
    try:
        return _respond(my_work.for_company_user(request.user))
    except Exception:
        logger.exception('company_my_work failed')
        return Response({'status': 'error', 'message': 'Could not load your work.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([EmployeeTokenAuthentication])
@permission_classes([IsAuthenticated])
def user_my_work(request):
    try:
        return _respond(my_work.for_user(request.user))
    except Exception:
        logger.exception('user_my_work failed')
        return Response({'status': 'error', 'message': 'Could not load your work.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
