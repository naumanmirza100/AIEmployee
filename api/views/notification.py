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
        from project_manager_agent.models import ScheduledMeeting, MeetingResponse
        from django.core.mail import send_mail
        from django.conf import settings as django_settings

        user = request.user
        action = request.data.get('action', '').strip()
        reason = request.data.get('reason', '').strip()
        counter_time_str = request.data.get('counter_time', '')

        if action not in ('accepted', 'rejected', 'counter_proposed'):
            return Response({'status': 'error', 'message': 'Invalid action. Use: accepted, rejected, counter_proposed'}, status=status.HTTP_400_BAD_REQUEST)

        # Get the meeting — invitee must be this user
        try:
            meeting = ScheduledMeeting.objects.select_related('organizer', 'invitee').get(id=meeting_id, invitee=user)
        except ScheduledMeeting.DoesNotExist:
            return Response({'status': 'error', 'message': 'Meeting not found or you are not the invitee.'}, status=status.HTTP_404_NOT_FOUND)

        # Can't act on finalized meetings
        if meeting.status in ('accepted', 'withdrawn'):
            return Response({'status': 'error', 'message': f'Meeting is already {meeting.status}.'}, status=status.HTTP_400_BAD_REQUEST)

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

        # Update meeting status
        if action == 'accepted':
            meeting.status = 'accepted'
        elif action == 'rejected':
            meeting.status = 'rejected'
        elif action == 'counter_proposed':
            meeting.status = 'counter_proposed'
            meeting.proposed_time = counter_time
        meeting.save()

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

        # Also send email to organizer
        try:
            from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
            send_mail(
                subject=f'Meeting Update: {meeting.title}',
                message='',
                from_email=from_email,
                recipient_list=[organizer.email],
                html_message=f'<p><strong>{invitee_name}</strong> has {action.replace("_", " ")} the meeting <strong>"{meeting.title}"</strong>.</p>',
                fail_silently=True,
            )
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
    """List all meetings where the current project user is the invitee."""
    try:
        from project_manager_agent.models import ScheduledMeeting

        user = request.user
        logger.info(f"[MEETING LIST] user={user}, id={user.id}, username={user.username}, type={type(user).__name__}")
        meetings = ScheduledMeeting.objects.filter(
            invitee=user
        ).select_related('organizer', 'invitee').prefetch_related('responses').order_by('-created_at')[:50]
        logger.info(f"[MEETING LIST] Found {meetings.count()} meetings for user {user.id}")

        data = []
        for m in meetings:
            responses = []
            for r in m.responses.all().order_by('created_at'):
                if r.responded_by == 'organizer':
                    responder_name = m.organizer.full_name
                else:
                    responder_name = m.invitee.get_full_name() or m.invitee.username
                responses.append({
                    'id': r.id,
                    'responded_by': r.responded_by,
                    'responder_name': responder_name,
                    'action': r.action,
                    'proposed_time': r.proposed_time.isoformat() if r.proposed_time else None,
                    'reason': r.reason,
                    'created_at': r.created_at.isoformat(),
                })

            data.append({
                'id': m.id,
                'organizer_name': m.organizer.full_name,
                'organizer_email': m.organizer.email,
                'title': m.title,
                'description': m.description,
                'proposed_time': m.proposed_time.isoformat(),
                'duration_minutes': m.duration_minutes,
                'status': m.status,
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

