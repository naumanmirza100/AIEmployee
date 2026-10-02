"""Floating Quick Chat history, kept on the server (core.models.QuickChat).

  GET    /quick-chats?agent=pm&mode=pilot    the login's newest conversations
  PUT    /quick-chats/<id>                   save one whole: {agent, mode, title, messages}
  DELETE /quick-chats/<id>?agent=pm          forget one

Each dashboard login sees only its own. POST does what PUT does, for the
browser's last save as the page closes (`fetch(..., {keepalive: true})`).
"""
import json

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.models import QuickChat

MODES = {'pm': ('pilot', 'qa'), 'hr': ('',), 'frontline': ('',)}
KEEP = 30                     # newest conversations kept per agent and mode
MAX_MESSAGES = 400
MAX_BYTES = 1_000_000


def _agent_and_mode(data):
    agent = str(data.get('agent') or '')
    mode = str(data.get('mode') or '')
    if agent not in MODES:
        return None, None, 'agent must be one of: ' + ', '.join(MODES)
    if mode not in MODES[agent]:
        return None, None, f'Unknown mode for {agent}.'
    return agent, mode, None


def _payload(chat):
    return {'id': chat.client_id, 'title': chat.title, 'messages': chat.messages,
            'updated_at': int(chat.updated_at.timestamp() * 1000)}


def _error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({'status': 'error', 'message': message}, status=code)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_quick_chats(request):
    agent, mode, problem = _agent_and_mode(request.query_params)
    if problem:
        return _error(problem)
    chats = (QuickChat.objects.filter(company_user=request.user, agent=agent, mode=mode)
             .order_by('-updated_at')[:KEEP])
    return Response({'status': 'success', 'data': [_payload(c) for c in chats]})


@api_view(['PUT', 'POST', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def quick_chat(request, client_id):
    if request.method == 'DELETE':
        agent = request.query_params.get('agent')
        if agent not in MODES:
            return _error('agent must be one of: ' + ', '.join(MODES))
        QuickChat.objects.filter(company_user=request.user, agent=agent, client_id=client_id).delete()
        return Response({'status': 'success'})

    data = request.data if isinstance(request.data, dict) else {}
    agent, mode, problem = _agent_and_mode(data)
    if problem:
        return _error(problem)
    messages = data.get('messages')
    if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
        return _error('messages must be a list of messages.')
    if len(messages) > MAX_MESSAGES or len(json.dumps(messages, default=str)) > MAX_BYTES:
        return _error('This conversation is too long to save. Start a new one.',
                      status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    title = (str(data.get('title') or '').strip() or 'Chat')[:255]

    chat, _ = QuickChat.objects.update_or_create(
        company_user=request.user, agent=agent, client_id=client_id,
        defaults={'mode': mode, 'title': title, 'messages': messages})
    # Keep the newest few, as the browser's list did.
    stale = (QuickChat.objects.filter(company_user=request.user, agent=agent, mode=mode)
             .order_by('-updated_at').values_list('pk', flat=True)[KEEP:])
    QuickChat.objects.filter(pk__in=list(stale)).delete()
    return Response({'status': 'success', 'data': {'id': chat.client_id,
                                                   'updated_at': int(chat.updated_at.timestamp() * 1000)}})
