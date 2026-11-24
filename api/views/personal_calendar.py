"""A person's own Google or Outlook calendar: its card's endpoints (core/personal_calendars.py, 24 Nov 2026).

Two doors to the same thing: a dashboard login (company/my-calendar, through the employee login it maps to) and an
employee login in My Space (me/calendar). Only the person themselves connects, changes or ends their connection.
"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core import personal_calendars as pc

logger = logging.getLogger(__name__)

COMPANY_PAGE = '/company/profile/integrations'
MY_SPACE_PAGE = '/me/meetings'


def _error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({'status': 'error', 'message': message}, status=code)


def _handle(request, user_id, company_id, default_page, linked=True):
    from core.models import PersonalCalendar
    if request.method == 'GET':
        return Response({'status': 'success', 'data': pc.status_for(user_id, linked=linked)})
    if not (linked and user_id and company_id):
        return _error(pc.NOT_LINKED)
    cal = PersonalCalendar.objects.filter(user_id=user_id).first()
    if request.method == 'PATCH':
        if cal is None:
            return _error('No calendar is connected.', status.HTTP_404_NOT_FOUND)
        changed = []
        for field, key in (('read_busy', 'readBusy'), ('push_events', 'pushEvents')):
            if key in request.data:
                setattr(cal, field, bool(request.data.get(key)))
                changed.append(field)
        if changed:
            cal.save(update_fields=changed)
            pc.sync(cal)
        return Response({'status': 'success', 'data': pc.status_for(user_id)})
    if request.method == 'DELETE':
        if cal is not None:
            pc.disconnect(cal)
        return Response({'status': 'success', 'message': 'Your calendar is disconnected.',
                         'data': pc.status_for(user_id)})
    return _error('Not allowed.', status.HTTP_405_METHOD_NOT_ALLOWED)


def _connect(request, user_id, company_id, default_page, linked=True):
    if not (linked and user_id and company_id):
        return _error(pc.NOT_LINKED)
    provider = str(request.data.get('provider') or '')
    if provider not in pc.PROVIDER_LABELS:
        return _error('Choose Google Calendar or Outlook.')
    if not pc.offered().get(provider):
        return _error(f'{pc.PROVIDER_LABELS[provider]} is not set up on this server yet. Contact support.')
    return_to = request.data.get('return_to') or default_page
    if not (isinstance(return_to, str) and return_to.startswith('/') and not return_to.startswith('//')):
        return_to = default_page
    state = pc.make_state(user_id=user_id, company_id=company_id, provider=provider, return_to=return_to)
    return Response({'status': 'success', 'data': {'authUrl': pc.auth_url(provider, state)}})


def _sync_now(user_id, linked=True):
    from core.models import PersonalCalendar
    cal = PersonalCalendar.objects.filter(user_id=user_id).first() if (linked and user_id) else None
    if cal is None:
        return _error('No calendar is connected.', status.HTTP_404_NOT_FOUND)
    result = pc.sync(cal)
    if result.get('skipped') == 'already syncing':
        return Response({'status': 'success', 'message': 'It is being synced right now.',
                         'data': pc.status_for(user_id)})
    return Response({'status': 'success', 'data': pc.status_for(user_id)})


# --- A dashboard login ---------------------------------------------------------------------------------------------

def _company_side(request):
    cu = request.user
    user_id = pc.calendar_user_id(cu)
    return user_id, cu.company_id, bool(user_id)


@api_view(['GET', 'PATCH', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_my_calendar(request):
    user_id, company_id, linked = _company_side(request)
    return _handle(request, user_id, company_id, COMPANY_PAGE, linked)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_my_calendar_connect(request):
    user_id, company_id, linked = _company_side(request)
    return _connect(request, user_id, company_id, COMPANY_PAGE, linked)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def company_my_calendar_sync(request):
    user_id, _company_id, linked = _company_side(request)
    return _sync_now(user_id, linked)


# --- An employee login (My Space) ----------------------------------------------------------------------------------

def _employee_side(request):
    from core.tenancy import company_of_user
    company = company_of_user(request.user)
    return request.user.id, (company.id if company else None), company is not None


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def my_calendar(request):
    user_id, company_id, linked = _employee_side(request)
    return _handle(request, user_id, company_id, MY_SPACE_PAGE, linked)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def my_calendar_connect(request):
    user_id, company_id, linked = _employee_side(request)
    return _connect(request, user_id, company_id, MY_SPACE_PAGE, linked)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def my_calendar_sync(request):
    user_id, _company_id, linked = _employee_side(request)
    return _sync_now(user_id, linked)


# --- Coming back from the sign-in ----------------------------------------------------------------------------------

def finish(request, provider):
    """Both providers come back here (Google through the company calendar's callback, whose state says which)."""
    error, code, state = request.GET.get('error'), request.GET.get('code'), request.GET.get('state')
    try:
        data = pc.read_state(state)
    except pc.CalendarError as exc:
        return pc.redirect_after('', error=str(exc))
    if data is None:
        return pc.redirect_after('', error='Invalid connection request. Start from the Connect button.')
    return_to = data.get('return_to') or ''
    if error:
        return pc.redirect_after(return_to, error=request.GET.get('error_description') or error)
    if not code or data.get('provider') != provider:
        return pc.redirect_after(return_to, error='Invalid connection request. Start from the Connect button.')
    try:
        pc.finish_connect(data, code)
    except pc.CalendarError as exc:
        return pc.redirect_after(return_to, error=str(exc))
    except Exception:
        logger.exception('Personal calendar connect failed (%s)', provider)
        return pc.redirect_after(return_to, error='The calendar could not be connected. Please try again.')
    return pc.redirect_after(return_to, connected=True)


@api_view(['GET'])
@permission_classes([AllowAny])
def microsoft_callback(request):
    return finish(request, 'microsoft')
