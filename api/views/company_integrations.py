"""
Company-wide Google Calendar integration (managed from Company Profile).

Companies connect their own Google account via OAuth ("Connect" button). The
platform's Google Cloud OAuth app (client id/secret/redirect from settings) is
used to obtain a per-company refresh token, stored on
``Company.google_calendar_config``. Interview scheduling then creates calendar
events / Meet links on that company's calendar. There is no global env
fallback — a company that hasn't connected simply gets no calendar event.
"""
import base64
import logging
import urllib.parse

from django.conf import settings
from django.core import signing
from django.http import HttpResponseRedirect
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URI = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URI = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URI = 'https://openidconnect.googleapis.com/v1/userinfo'
CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar'
# Signed OAuth state is only valid briefly.
STATE_MAX_AGE_SECONDS = 600
STATE_SALT = 'recruitment.gcal.oauth'


def _oauth_configured():
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET and settings.GOOGLE_OAUTH_REDIRECT_URI)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def google_calendar_status(request):
    """Return the company's Google Calendar connection status (no secrets)."""
    company = request.user.company
    if not company:
        return Response({'status': 'error', 'message': 'No company on this account.'}, status=status.HTTP_404_NOT_FOUND)

    cfg = company.google_calendar_config or {}
    return Response({
        'status': 'success',
        'data': {
            'connected': bool(cfg.get('connected') and cfg.get('refresh_token')),
            'googleEmail': cfg.get('google_email') or '',
            'calendarId': cfg.get('calendar_id') or 'primary',
            'configured': _oauth_configured(),  # is the platform OAuth app set up?
            'lastError': cfg.get('last_error') or '',
        },
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def google_calendar_connect(request):
    """Return the Google consent URL for the company to authorize calendar access."""
    company = request.user.company
    if not company:
        return Response({'status': 'error', 'message': 'No company on this account.'}, status=status.HTTP_404_NOT_FOUND)
    if not _oauth_configured():
        return Response({
            'status': 'error',
            'message': 'Google Calendar is not configured on the server. Contact support.',
        }, status=status.HTTP_400_BAD_REQUEST)

    # Signed state carries the company id so the public callback can identify it.
    # Base64-urlsafe wrap so the value has no ':' characters (cleaner in URLs).
    signed = signing.dumps({'company_id': company.id}, salt=STATE_SALT)
    state = base64.urlsafe_b64encode(signed.encode()).decode().rstrip('=')

    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
        'response_type': 'code',
        'scope': f'openid email {CALENDAR_SCOPE}',
        'access_type': 'offline',
        'prompt': 'consent',  # force a refresh_token every time
        'state': state,
    }
    auth_url = f'{GOOGLE_AUTH_URI}?{urllib.parse.urlencode(params)}'
    return Response({'status': 'success', 'data': {'authUrl': auth_url}}, status=status.HTTP_200_OK)


def _settings_redirect(connected=None, error=None):
    """Redirect the browser back to the Company Profile integrations tab."""
    base = (settings.FRONTEND_URL or '').rstrip('/')
    url = f'{base}/company/profile/integrations'
    if connected:
        url += '?gcal=connected'
    elif error:
        url += f'?gcal_error={urllib.parse.quote(error)}'
    return HttpResponseRedirect(url)


@api_view(['GET'])
@permission_classes([AllowAny])
def google_calendar_callback(request):
    """Google redirects here with ?code&state. Exchange for a refresh token and save it."""
    import requests

    error = request.GET.get('error')
    if error:
        return _settings_redirect(error=error)

    code = request.GET.get('code')
    state = request.GET.get('state')
    if not code:
        return _settings_redirect(error='Missing authorization code.')
    if not state:
        # Happens when the flow was started from a hand-made URL without state.
        # Always start the connection from the in-app "Connect" button.
        return _settings_redirect(error='Missing state — please start from the Connect button.')

    try:
        # Reverse the base64-urlsafe wrapping applied in the connect step.
        padded = state + '=' * (-len(state) % 4)
        signed = base64.urlsafe_b64decode(padded.encode()).decode()
        data = signing.loads(signed, salt=STATE_SALT, max_age=STATE_MAX_AGE_SECONDS)
        company_id = data['company_id']
    except signing.SignatureExpired:
        return _settings_redirect(error='The connection request expired. Please try again.')
    except Exception:
        return _settings_redirect(error='Invalid connection request.')

    from core.models import Company
    try:
        company = Company.objects.get(id=company_id)
    except Company.DoesNotExist:
        return _settings_redirect(error='Company not found.')

    # Exchange the code for tokens.
    try:
        token_resp = requests.post(GOOGLE_TOKEN_URI, data={
            'code': code,
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
            'grant_type': 'authorization_code',
        }, timeout=20)
        token_json = token_resp.json()
        if token_resp.status_code != 200 or 'refresh_token' not in token_json:
            msg = token_json.get('error_description') or token_json.get('error') or 'Token exchange failed.'
            logger.error(f"Google token exchange failed for company {company_id}: {token_json}")
            return _settings_redirect(error=msg)

        refresh_token = token_json['refresh_token']
        access_token = token_json.get('access_token')

        # Best-effort: fetch the connected Google account email for display.
        google_email = ''
        try:
            if access_token:
                ui = requests.get(GOOGLE_USERINFO_URI, headers={'Authorization': f'Bearer {access_token}'}, timeout=15)
                if ui.status_code == 200:
                    google_email = ui.json().get('email', '')
        except Exception:
            pass

        company.google_calendar_config = {
            'connected': True,
            'refresh_token': refresh_token,
            'google_email': google_email,
            'calendar_id': 'primary',
            'last_error': '',
        }
        company.save(update_fields=['google_calendar_config'])
        return _settings_redirect(connected=True)

    except Exception as exc:
        logger.error(f"Google Calendar callback error for company {company_id}: {exc}", exc_info=True)
        return _settings_redirect(error='Failed to connect Google Calendar.')


@api_view(['DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def google_calendar_disconnect(request):
    """Clear the company's Google Calendar connection."""
    company = request.user.company
    if not company:
        return Response({'status': 'error', 'message': 'No company on this account.'}, status=status.HTTP_404_NOT_FOUND)
    company.google_calendar_config = {}
    company.save(update_fields=['google_calendar_config'])
    return Response({'status': 'success', 'message': 'Google Calendar disconnected.'}, status=status.HTTP_200_OK)
