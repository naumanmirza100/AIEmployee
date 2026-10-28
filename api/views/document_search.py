"""Whether HR's and Frontline's document search works by meaning, and a way to fix parts saved without (CO-70).

GET  company/document-search?agent=hr_agent|frontline_agent  — see core.document_search.status, plus can_fix.
POST company/document-search  {agent}                         — give the parts with no vector one, in the background.
"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core import document_search

logger = logging.getLogger(__name__)

_WHO_CAN_FIX = {
    'hr_agent': ("Only an HR admin can do this: the company's owner, an admin, or a login with the HR admin role, "
                 "because HR documents are theirs to manage."),
}


def _may_fix(company_user, agent):
    if agent == 'hr_agent':
        from hr_agent.alerts import HR_ADMIN_ROLES
        return company_user.role in HR_ADMIN_ROLES
    return True


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def document_search_status(request):
    from core.modules import has_module
    company_user = request.user
    agent = request.query_params.get('agent') if request.method == 'GET' else (request.data or {}).get('agent')
    if agent not in document_search.AGENTS or not has_module(company_user.company, agent):
        return Response({'status': 'error', 'message': 'Choose hr_agent or frontline_agent, one the company has.'},
                        status=status.HTTP_400_BAD_REQUEST)
    company_id = company_user.company_id
    if request.method == 'GET':
        return Response({'status': 'success', 'data': {
            **document_search.status(company_id, agent), 'can_fix': _may_fix(company_user, agent)}})
    if not _may_fix(company_user, agent):
        return Response({'status': 'error', 'code': 'hr_admin_only', 'message': _WHO_CAN_FIX[agent]},
                        status=status.HTTP_403_FORBIDDEN)
    if not document_search.provider_available(company_id, agent):
        return Response({'status': 'error', 'message': (
            'Searching by meaning is off on the server, so there is nothing to fix with yet. Add an OpenAI key for '
            'this agent under AI keys, or ask Pay Per Project support.')}, status=status.HTTP_409_CONFLICT)
    from api.views.frontline_agent import _celery_broker_ready
    from core.tasks import fill_missing_vectors
    if _celery_broker_ready(timeout_seconds=0.5):
        try:
            fill_missing_vectors.apply_async(args=[company_id, agent], retry=False)
            return Response({'status': 'success', 'data': {'queued': True}})
        except Exception:
            logger.exception('fill_missing_vectors: dispatch failed, running inline')
    filled = document_search.fill_missing_vectors(company_id, agent)
    return Response({'status': 'success', 'data': {'queued': False, 'filled': filled}})
