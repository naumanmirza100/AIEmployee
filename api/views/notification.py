from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime
import logging

from core.models import Notification

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_notifications(request):
    """Get user notifications"""
    try:
        user = request.user
        
        # Get unread notifications first, then read
        unread = Notification.objects.filter(user=user, is_read=False).order_by('-created_at')
        read = Notification.objects.filter(user=user, is_read=True).order_by('-created_at')[:50]  # Limit read notifications
        
        # Serialize notifications
        notifications_data = []
        def _serialize_notif(notif):
            return {
                'id': notif.id,
                'title': notif.title,
                'message': notif.message,
                'type': notif.type,
                'notification_type': notif.notification_type,
                'link': notif.link,
                'action_url': notif.action_url,
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat() if notif.created_at else None,
            }

        for notif in unread:
            notifications_data.append(_serialize_notif(notif))
        for notif in read:
            notifications_data.append(_serialize_notif(notif))
        
        return Response({
            'status': 'success',
            'data': notifications_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to fetch notifications',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, id):
    """Mark notification as read"""
    try:
        notification = get_object_or_404(Notification, id=id, user=request.user)
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        
        return Response({
            'status': 'success',
            'message': 'Notification marked as read'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update notification',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    """Mark all notifications as read"""
    try:
        now = timezone.now()
        updated_count = Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True,
            read_at=now
        )
        
        return Response({
            'status': 'success',
            'message': f'{updated_count} notifications marked as read'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'status': 'error',
            'message': 'Failed to update notifications',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== MEETING RESPONSE (Project User) ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def meeting_respond(request, meeting_id):
    """
    Project user (Django User) responds to a meeting request.
    Actions: accept, reject, counter_propose
    """
    try:
        from project_manager_agent.models import ScheduledMeeting, MeetingResponse, MeetingParticipant
        from django.core.mail import send_mail
        from django.conf import settings as django_settings

        user = request.user
        action = request.data.get('action', '').strip()
        reason = request.data.get('reason', '').strip()
        counter_time_str = request.data.get('counter_time', '')

        if action not in ('accepted', 'rejected', 'counter_proposed'):
            return Response({'status': 'error', 'message': 'Invalid action. Use: accepted, rejected, counter_proposed'}, status=status.HTTP_400_BAD_REQUEST)

        # Get the meeting — user must be a participant
        try:
            meeting = ScheduledMeeting.objects.select_related('organizer', 'invitee').get(id=meeting_id)
            participant = MeetingParticipant.objects.get(meeting=meeting, user=user)
        except ScheduledMeeting.DoesNotExist:
            return Response({'status': 'error', 'message': 'Meeting not found.'}, status=status.HTTP_404_NOT_FOUND)
        except MeetingParticipant.DoesNotExist:
            # Fallback: check legacy invitee field
            if meeting.invitee_id != user.id:
                return Response({'status': 'error', 'message': 'You are not a participant in this meeting.'}, status=status.HTTP_404_NOT_FOUND)
            # Create participant record for legacy meeting
            participant = MeetingParticipant.objects.create(meeting=meeting, user=user, status='pending')

        # Can't act on withdrawn meetings
        if meeting.status == 'withdrawn':
            return Response({'status': 'error', 'message': 'This meeting has been withdrawn.'}, status=status.HTTP_400_BAD_REQUEST)

        # Can't act if this participant already accepted
        if participant.status == 'accepted' and action != 'counter_proposed':
            return Response({'status': 'error', 'message': 'You have already accepted this meeting.'}, status=status.HTTP_400_BAD_REQUEST)

        # Parse counter time
        counter_time = None
        if action == 'counter_proposed':
            if not counter_time_str:
                return Response({'status': 'error', 'message': 'counter_time is required for counter proposals.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                counter_time = datetime.fromisoformat(counter_time_str.replace('Z', '+00:00'))
                if timezone.is_naive(counter_time):
                    counter_time = timezone.make_aware(counter_time)
            except Exception:
                return Response({'status': 'error', 'message': 'Invalid counter_time format.'}, status=status.HTTP_400_BAD_REQUEST)

        # Create response record
        MeetingResponse.objects.create(
            meeting=meeting,
            responded_by='invitee',
            action=action,
            proposed_time=counter_time,
            reason=reason,
        )

        # Update this participant's status
        participant.status = action
        participant.reason = reason
        participant.responded_at = timezone.now()
        if action == 'counter_proposed':
            participant.counter_proposed_time = counter_time
        participant.save()

        # Update overall meeting status based on all participants
        if action == 'counter_proposed':
            meeting.proposed_time = counter_time
            meeting.save(update_fields=['proposed_time', 'updated_at'])
        meeting.update_overall_status()

        # Notify the organizer (CompanyUser) via PMNotification
        from project_manager_agent.models import PMNotification
        organizer = meeting.organizer
        invitee_name = user.get_full_name() or user.username
        time_display = meeting.proposed_time.strftime('%A, %B %d, %Y at %I:%M %p') if meeting.proposed_time else 'TBD'

        if action == 'accepted':
            PMNotification.objects.create(
                company_user=organizer,
                notification_type='custom',
                severity='info',
                title=f'Meeting Accepted: {meeting.title}',
                message=f'{invitee_name} accepted the meeting "{meeting.title}" scheduled for {time_display}.',
                data={'meeting_id': meeting.id, 'type': 'meeting_accepted'},
            )
        elif action == 'rejected':
            reason_text = f' Reason: {reason}' if reason else ''
            PMNotification.objects.create(
                company_user=organizer,
                notification_type='custom',
                severity='warning',
                title=f'Meeting Rejected: {meeting.title}',
                message=f'{invitee_name} rejected the meeting "{meeting.title}".{reason_text}',
                data={'meeting_id': meeting.id, 'type': 'meeting_rejected', 'reason': reason},
            )
        elif action == 'counter_proposed':
            new_time_display = counter_time.strftime('%A, %B %d, %Y at %I:%M %p')
            reason_text = f' Reason: {reason}' if reason else ''
            PMNotification.objects.create(
                company_user=organizer,
                notification_type='custom',
                severity='info',
                title=f'New Time Proposed: {meeting.title}',
                message=f'{invitee_name} suggested a new time for "{meeting.title}": {new_time_display}.{reason_text}',
                data={'meeting_id': meeting.id, 'type': 'meeting_counter_proposed', 'new_time': counter_time.isoformat(), 'reason': reason},
            )

        # Generate .ics for organizer when invitee accepts
        ics_attachment = None
        if action == 'accepted':
            try:
                from project_manager_agent.ics_generator import generate_meeting_ics
                ics_attachment = generate_meeting_ics(meeting, action='REQUEST')
            except Exception:
                pass

        # Also send email to organizer
        try:
            from django.core.mail import EmailMultiAlternatives
            from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
            email_body = f'<p><strong>{invitee_name}</strong> has {action.replace("_", " ")} the meeting <strong>"{meeting.title}"</strong>.</p>'
            email_msg = EmailMultiAlternatives(
                subject=f'Meeting Update: {meeting.title}',
                body='',
                from_email=from_email,
                to=[organizer.email],
            )
            email_msg.attach_alternative(email_body, 'text/html')
            if ics_attachment:
                email_msg.attach('meeting.ics', ics_attachment, 'text/calendar; method=REQUEST')
            email_msg.send(fail_silently=True)

        except Exception as e:
            logger.warning(f'Failed to send meeting email to organizer: {e}')

        return Response({
            'status': 'success',
            'message': f'Meeting {action.replace("_", " ")} successfully.',
            'data': {
                'meeting_id': meeting.id,
                'status': meeting.status,
                'proposed_time': meeting.proposed_time.isoformat(),
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception('meeting_respond failed')
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def meeting_list_for_user(request):
    """List all meetings where the current project user is a participant."""
    try:
        from project_manager_agent.models import ScheduledMeeting, MeetingParticipant

        user = request.user
        # Find meetings where user is a participant OR legacy invitee
        participant_meeting_ids = MeetingParticipant.objects.filter(user=user).values_list('meeting_id', flat=True)
        from django.db.models import Q
        meetings = ScheduledMeeting.objects.filter(
            Q(id__in=participant_meeting_ids) | Q(invitee=user)
        ).distinct().select_related('organizer', 'invitee').prefetch_related('responses', 'participants__user').order_by('-created_at')[:50]

        data = []
        for m in meetings:
            responses = []
            for r in m.responses.all().order_by('created_at'):
                if r.responded_by == 'organizer':
                    responder_name = m.organizer.full_name
                else:
                    responder_name = m.invitee.get_full_name() or m.invitee.username if m.invitee else 'Invitee'
                responses.append({
                    'id': r.id,
                    'responded_by': r.responded_by,
                    'responder_name': responder_name,
                    'action': r.action,
                    'proposed_time': r.proposed_time.isoformat() if r.proposed_time else None,
                    'reason': r.reason,
                    'created_at': r.created_at.isoformat(),
                })

            # Participants with per-user status
            participants = []
            my_status = 'pending'
            for p in m.participants.all():
                pname = p.user.get_full_name() or p.user.username
                participants.append({
                    'user_id': p.user_id,
                    'name': pname,
                    'status': p.status,
                })
                if p.user_id == user.id:
                    my_status = p.status

            data.append({
                'id': m.id,
                'organizer_name': m.organizer.full_name,
                'organizer_email': m.organizer.email,
                'title': m.title,
                'description': m.description,
                'agenda': m.agenda or [],
                'proposed_time': m.proposed_time.isoformat(),
                'duration_minutes': m.duration_minutes,
                'status': m.status,
                'my_status': my_status,
                'participants': participants,
                'created_at': m.created_at.isoformat(),
                'responses': responses,
            })

        return Response({
            'status': 'success',
            'data': {'meetings': data, 'total': len(data)}
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception('meeting_list_for_user failed')
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== EMAIL-LINK MEETING ACCEPT / REJECT ====================
#
# Lets invitees accept or reject a meeting straight from the invitation email
# WITHOUT logging in. We sign a `<meeting_id>:<user_id>` payload using
# `TimestampSigner` (HMAC over SECRET_KEY + a salt) so the link can't be
# forged or replayed past its TTL.
#
# Token lifetime: 14 days — long enough to cover a typical meeting window
# but short enough to not leave indefinitely-valid action URLs floating
# around in mailboxes.

EMAIL_TOKEN_MAX_AGE_SECONDS = 14 * 24 * 3600
EMAIL_TOKEN_SALT = 'pm.meeting.email-action.v1'


def _make_meeting_email_token(meeting_id: int, user_id: int) -> str:
    """Sign a `meeting_id:user_id` payload for use in a meeting invitation email."""
    from django.core.signing import TimestampSigner
    signer = TimestampSigner(salt=EMAIL_TOKEN_SALT)
    return signer.sign(f'{int(meeting_id)}:{int(user_id)}')


def _verify_meeting_email_token(token: str):
    """Verify a signed token. Returns (meeting_id, user_id) tuple or None."""
    from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
    signer = TimestampSigner(salt=EMAIL_TOKEN_SALT)
    try:
        raw = signer.unsign(token, max_age=EMAIL_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    try:
        meeting_id_str, user_id_str = raw.split(':')
        return int(meeting_id_str), int(user_id_str)
    except (ValueError, AttributeError):
        return None


def build_meeting_email_action_url(meeting_id: int, user_id: int, action: str) -> str:
    """Build the absolute URL for an email accept/reject link.

    `action` is one of 'accepted', 'rejected'. Imported by the meeting-create
    code in pm_agent.py to embed in the invitation HTML.
    """
    from django.conf import settings as django_settings
    if action not in ('accepted', 'rejected'):
        raise ValueError(f"Unsupported action: {action}")
    backend_base = (getattr(django_settings, 'BACKEND_PUBLIC_URL', None)
                    or getattr(django_settings, 'PUBLIC_BACKEND_URL', None)
                    or 'http://localhost:8000')
    backend_base = backend_base.rstrip('/')
    token = _make_meeting_email_token(meeting_id, user_id)
    return f"{backend_base}/api/meetings/email-action/{action}/{token}/"


def _render_email_action_page(title: str, message: str, color: str = '#10b981'):
    """Tiny HTML confirmation page shown after the invitee clicks the email link."""
    from django.http import HttpResponse
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%);
            color: #fff; padding: 24px; }}
    .card {{ max-width: 460px; width:100%; background: rgba(0,0,0,0.4); border:1px solid rgba(255,255,255,0.08);
             border-radius: 16px; padding: 32px; text-align:center; }}
    .icon {{ font-size: 48px; line-height:1; margin-bottom: 16px; color: {color}; }}
    h1 {{ font-size: 20px; margin: 0 0 12px; }}
    p {{ color: rgba(255,255,255,0.7); line-height: 1.5; margin: 0; }}
    .hint {{ margin-top: 24px; font-size: 12px; color: rgba(255,255,255,0.4); }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">●</div>
    <h1>{title}</h1>
    <p>{message}</p>
    <p class="hint">You can close this window.</p>
  </div>
</body>
</html>"""
    return HttpResponse(html, content_type='text/html')


def meeting_email_action(request, action, token):
    """Public endpoint hit from the accept/reject buttons in the invitation
    email. No auth required — the signed token IS the auth.

    URL: GET /api/meetings/email-action/<action>/<token>/
    Returns a small HTML confirmation page (the invitee opened this from
    their mail client; we render directly instead of a JSON API response).
    """
    from project_manager_agent.models import (
        ScheduledMeeting, MeetingParticipant, MeetingResponse, PMNotification,
    )

    if action not in ('accepted', 'rejected'):
        return _render_email_action_page(
            'Invalid action',
            'The link you opened is malformed. Please open the invitation email again.',
            color='#ef4444',
        )

    payload = _verify_meeting_email_token(token)
    if not payload:
        return _render_email_action_page(
            'Link expired or invalid',
            'This invitation link is no longer valid. Please log in to your dashboard to respond.',
            color='#ef4444',
        )
    meeting_id, user_id = payload

    try:
        meeting = ScheduledMeeting.objects.select_related('organizer', 'invitee').get(id=meeting_id)
    except ScheduledMeeting.DoesNotExist:
        return _render_email_action_page(
            'Meeting not found',
            'This meeting no longer exists. It may have been cancelled.',
            color='#ef4444',
        )

    if meeting.status == 'withdrawn':
        return _render_email_action_page(
            'Meeting withdrawn',
            f'The organizer has withdrawn the meeting "{meeting.title}". No action is required.',
            color='#9ca3af',
        )

    participant, _created = MeetingParticipant.objects.get_or_create(
        meeting=meeting, user_id=user_id, defaults={'status': 'pending'},
    )

    # Idempotency — if the invitee already pressed the same button, show the
    # same confirmation page instead of writing a duplicate response row.
    if participant.status == action:
        verb = 'accepted' if action == 'accepted' else 'rejected'
        return _render_email_action_page(
            f'Already {verb}',
            f'You have already {verb} the meeting "{meeting.title}". No further action is needed.',
            color='#10b981' if action == 'accepted' else '#9ca3af',
        )

    participant.status = action
    participant.responded_at = timezone.now()
    participant.save(update_fields=['status', 'responded_at'])

    MeetingResponse.objects.create(
        meeting=meeting, responded_by='invitee', action=action, reason='',
    )
    meeting.update_overall_status()

    # Notify the organizer (in-app). Email-to-organizer follow-up isn't
    # essential here — they'll see status update next time they refresh.
    try:
        invitee_name = participant.user.get_full_name() or participant.user.username
        time_display = meeting.proposed_time.strftime('%A, %B %d, %Y at %I:%M %p') if meeting.proposed_time else 'TBD'
        if action == 'accepted':
            PMNotification.objects.create(
                company_user=meeting.organizer,
                notification_type='custom',
                severity='info',
                title=f'Meeting Accepted: {meeting.title}',
                message=f'{invitee_name} accepted via email — "{meeting.title}" scheduled for {time_display}.',
                data={'meeting_id': meeting.id, 'via': 'email_link'},
            )
        else:
            PMNotification.objects.create(
                company_user=meeting.organizer,
                notification_type='custom',
                severity='warning',
                title=f'Meeting Rejected: {meeting.title}',
                message=f'{invitee_name} rejected "{meeting.title}" via email.',
                data={'meeting_id': meeting.id, 'via': 'email_link'},
            )
    except Exception:
        logger.exception('Failed to create organizer notification for email-link action')

    if action == 'accepted':
        return _render_email_action_page(
            'Meeting accepted',
            f'Thanks — you have accepted "{meeting.title}". The organizer has been notified.',
            color='#10b981',
        )
    return _render_email_action_page(
        'Meeting rejected',
        f'You have rejected "{meeting.title}". The organizer has been notified.',
        color='#9ca3af',
    )

