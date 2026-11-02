"""The Company Assistant's API (CO-18; see `core.assistant.engine`).

  GET  company/assistant          may this login use it, and what it reads (for the screen's note and suggestions)
  POST company/assistant/ask      {question, history}: {answer, sources, asked_back}
  POST company/assistant/ask-stream   the same, sent as it is written (ndjson: meta, token..., done)

For dashboard logins of a company with two agents or more. It is not under an agent's prefix, so the agents' own
gates don't apply; `has_module(company, 'company_assistant')` is its gate, as for an agent. Its chats are kept with
the Quick Chats (`quick-chats?agent=assistant`).
"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.assistant import engine
from core.modules import INCLUDED_WITH, has_module

logger = logging.getLogger(__name__)

MAX_QUESTION = 2000


class AssistantThrottle(SimpleRateThrottle):
    """Per login: `assistant_llm` in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']."""
    scope = 'assistant_llm'

    def get_cache_key(self, request, view):
        ident = getattr(getattr(request, 'user', None), 'pk', None)
        return self.cache_format % {'scope': self.scope, 'ident': ident or self.get_ident(request)}


def _not_included(request):
    if has_module(request.user.company, engine.AGENT_KEY):
        return None
    need = INCLUDED_WITH[engine.AGENT_KEY]
    message = (f'The Company Assistant comes with {need} agents or more. This company has fewer, so there is '
               'nothing to ask across yet.')
    return Response({'status': 'error', 'code': 'not_included', 'message': message}, status=status.HTTP_403_FORBIDDEN)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def assistant_status(request):
    ctx = engine.context_for(request.user)
    included = has_module(request.user.company, engine.AGENT_KEY)
    return Response({'status': 'success', 'data': {'included': included, 'needs_agents': INCLUDED_WITH[engine.AGENT_KEY],
                                                   **(engine.reading(ctx) if included else {})}})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([AssistantThrottle])
def assistant_ask(request):
    refused = _not_included(request)
    if refused:
        return refused
    data = request.data if isinstance(request.data, dict) else {}
    question = str(data.get('question') or '').strip()
    if not question:
        return Response({'status': 'error', 'message': 'Type a question.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(question) > MAX_QUESTION:
        return Response({'status': 'error', 'message': f'Keep the question under {MAX_QUESTION} characters.'},
                        status=status.HTTP_400_BAD_REQUEST)
    history = data.get('history') if isinstance(data.get('history'), list) else []
    from core.api_key_service import KeyServiceError
    try:
        result = engine.ask(request.user, question, history)
    except KeyServiceError as exc:
        return Response({'status': 'error', 'code': exc.reason, 'message': exc.user_message},
                        status=status.HTTP_402_PAYMENT_REQUIRED)
    except Exception:
        logger.exception('assistant_ask failed')
        return Response({'status': 'error', 'message': 'The assistant could not answer just now. Please try again.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response({'status': 'success', 'data': result})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([AssistantThrottle])
def assistant_ask_stream(request):
    """`assistant_ask`, with the answer sent as it is written (one JSON object per line; see api.streaming).

    A refusal (not included, no question, out of tokens before the answer starts) is an ordinary error response,
    so the screen shows it as it does for `ask`; once the answer has started, a problem is an 'error' event."""
    refused = _not_included(request)
    if refused:
        return refused
    data = request.data if isinstance(request.data, dict) else {}
    question = str(data.get('question') or '').strip()
    if not question:
        return Response({'status': 'error', 'message': 'Type a question.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(question) > MAX_QUESTION:
        return Response({'status': 'error', 'message': f'Keep the question under {MAX_QUESTION} characters.'},
                        status=status.HTTP_400_BAD_REQUEST)
    history = data.get('history') if isinstance(data.get('history'), list) else []
    from api.streaming import error_event, ndjson_response
    from core.api_key_service import KeyServiceError
    events = engine.ask_stream(request.user, question, history)
    try:
        first = next(events)            # planning and the lookups run here, so their refusals can still be a 402
    except KeyServiceError as exc:
        return Response({'status': 'error', 'code': exc.reason, 'message': exc.user_message},
                        status=status.HTTP_402_PAYMENT_REQUIRED)
    except Exception:
        logger.exception('assistant_ask_stream failed before the answer')
        return Response({'status': 'error', 'message': 'The assistant could not answer just now. Please try again.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def stream():
        yield first
        try:
            yield from events
        except Exception as exc:          # a key error once writing has begun, or anything else
            logger.exception('assistant_ask_stream failed while writing')
            yield error_event(exc)
    return ndjson_response(stream())
