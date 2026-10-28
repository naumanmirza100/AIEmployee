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


# ---------------------------------------------------------------------------
# Slack and Teams for the company (CO-64)
# ---------------------------------------------------------------------------
#
# HR and Frontline notification templates can post to Slack or Teams, through incoming-webhook addresses kept on the
# company (Company.hr_slack_webhook_url and three more). No screen could fill them in: the template forms offered
# Slack and Teams ("uses PM webhook", which it did not), and every such message was dropped with a log line. They are
# set here, by the company's owner or an admin, for each agent the company has.

CHAT_AGENTS = (('hr_agent', 'HR', 'hr'), ('frontline_agent', 'Frontline', 'frontline'))
CHANNELS = ('slack', 'teams')
_ADMINS_ONLY = ("Only the company's owner or an admin can set or test the Slack and Teams addresses, because "
                "messages sent there leave the company's account. Ask one of them.")


def _field(prefix, channel):
    return f'{prefix}_{channel}_webhook_url'


def _masked(url):
    url = (url or '').strip()
    return f'{url[:30]}…{url[-6:]}' if len(url) > 40 else ('set' if url else '')


def _check_url(channel, url):
    """None when the address can be used, else why not."""
    if not url.startswith('https://'):
        return 'The address must start with https://.'
    host = url.split('/')[2].lower()
    if channel == 'slack' and host != 'hooks.slack.com':
        return 'A Slack incoming-webhook address starts with https://hooks.slack.com/.'
    if channel == 'teams' and not (host.endswith('.webhook.office.com') or host.endswith('.logic.azure.com')
                                   or host.endswith('.environment.api.powerplatform.com')):
        return ('A Teams address comes from an "Incoming Webhook" connector (…webhook.office.com) or a Workflows '
                'webhook (…logic.azure.com).')
    return None


@api_view(['GET', 'PATCH', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def chat_webhooks(request):
    """GET: the Slack and Teams addresses per agent (masked). PATCH {agent, channel, url}: set or clear one. POST
    {agent, channel}: send a test message there. Only the owner or an admin may change or test them."""
    from core.modules import has_module
    company_user = request.user
    company = company_user.company
    agents = [(key, label, prefix) for key, label, prefix in CHAT_AGENTS if has_module(company, key)]

    def page():
        return [{'agent': key, 'label': label,
                 **{ch: {'set': bool(getattr(company, _field(prefix, ch))), 'shown': _masked(getattr(company, _field(prefix, ch)))}
                    for ch in CHANNELS}}
                for key, label, prefix in agents]

    if request.method == 'GET':
        return Response({'status': 'success', 'data': {'agents': page(),
                                                       'can_edit': company_user.role in ('owner', 'admin')}})
    data = request.data or {}
    found = next((a for a in agents if a[0] == data.get('agent')), None)
    channel = data.get('channel')
    if found is None or channel not in CHANNELS:
        return Response({'status': 'error', 'message': 'Choose an agent the company has, and slack or teams.'},
                        status=status.HTTP_400_BAD_REQUEST)
    key, label, prefix = found
    if company_user.role not in ('owner', 'admin'):
        return Response({'status': 'error', 'code': 'admins_only', 'message': _ADMINS_ONLY},
                        status=status.HTTP_403_FORBIDDEN)
    if request.method == 'POST':
        if not getattr(company, _field(prefix, channel)):
            return Response({'status': 'error', 'message': f'No {channel.title()} address is set for {label} yet.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if prefix == 'hr':
            from api.views.hr_agent import _send_hr_notification_slack as slack, _send_hr_notification_teams as teams
        else:
            from api.views.frontline_agent import _send_notification_slack as slack, _send_notification_teams as teams
        sent = (slack if channel == 'slack' else teams)(
            company, 'Test from Pay Per Project', f'{label} notifications will arrive here.')
        if not sent:
            return Response({'status': 'error', 'message': (
                f'{channel.title()} did not accept the test message. Check the address is the whole incoming-webhook '
                'address and that the webhook is still switched on.')}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({'status': 'success', 'data': {'sent': True}})
    url = (data.get('url') or '').strip()
    if url:
        why = _check_url(channel, url)
        if why:
            return Response({'status': 'error', 'message': why}, status=status.HTTP_400_BAD_REQUEST)
    setattr(company, _field(prefix, channel), url)
    company.save(update_fields=[_field(prefix, channel)])
    return Response({'status': 'success', 'data': {'agents': page(), 'can_edit': True}})
