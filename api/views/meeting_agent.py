"""
API views — AI Executive Meeting Assistant
Both company-user endpoints and admin endpoints.
"""

import json
import logging
from datetime import datetime

from django.db import models
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, throttle_classes,
)
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from core.api_key_service import KeyServiceError
from meeting_agent.ai_agents import ExecAgentRegistry
from meeting_agent.models import (
    ExecutiveMeeting,
    ExecutiveMeetingParticipant,
    MeetingNote,
    MeetingActionItem,
    ExecutiveTask,
    MeetingDocument,
    ExecNotification,
    ExecNotificationChannel,
    ExecMeetingSchedulingChat, ExecMeetingSchedulingChatMessage,
    ExecNotetakerChat, ExecNotetakerChatMessage,
    ExecTaskChat, ExecTaskChatMessage,
    ExecCalendarChat, ExecCalendarChatMessage,
    ExecDocumentChat, ExecDocumentChatMessage,
    ExecNotificationChat, ExecNotificationChatMessage,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Throttle classes
# ---------------------------------------------------------------------------

class ExecLLMThrottle(SimpleRateThrottle):
    scope = 'exec_llm'

    def get_cache_key(self, request, view):
        if hasattr(request, 'user') and request.user:
            ident = getattr(request.user, 'id', None) or getattr(request.user, 'pk', None)
            if ident:
                return self.cache_format % {'scope': self.scope, 'ident': ident}
        return self.get_ident(request)


class ExecCRUDThrottle(SimpleRateThrottle):
    scope = 'exec_crud'

    def get_cache_key(self, request, view):
        if hasattr(request, 'user') and request.user:
            ident = getattr(request.user, 'id', None) or getattr(request.user, 'pk', None)
            if ident:
                return self.cache_format % {'scope': self.scope, 'ident': ident}
        return self.get_ident(request)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_agent(name, company_user):
    agent = ExecAgentRegistry.get_agent(name)
    agent.company_id = company_user.company_id
    return agent


def _parse_datetime(value):
    """Parse ISO datetime string to aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt
    except (ValueError, AttributeError):
        return None


def _serialize_meeting(meeting, include_participants=False):
    data = {
        'id': meeting.id,
        'title': meeting.title,
        'description': meeting.description,
        'agenda': meeting.agenda,
        'location': meeting.location,
        'meeting_link': meeting.meeting_link,
        'scheduled_at': meeting.scheduled_at.isoformat(),
        'duration_minutes': meeting.duration_minutes,
        'timezone_name': meeting.timezone_name,
        'status': meeting.status,
        'recurrence': meeting.recurrence,
        'recurrence_end_date': meeting.recurrence_end_date.isoformat() if meeting.recurrence_end_date else None,
        'organizer_id': meeting.organizer_id,
        'organizer_name': meeting.organizer.full_name if hasattr(meeting, 'organizer') else '',
        'created_at': meeting.created_at.isoformat(),
    }
    if include_participants:
        data['participants'] = [
            {
                'id': p.id,
                'company_user_id': p.company_user_id,
                'name': p.company_user.full_name,
                'response': p.response,
                'counter_proposed_time': p.counter_proposed_time.isoformat() if p.counter_proposed_time else None,
                'reason': p.reason,
            }
            for p in meeting.participants.select_related('company_user').all()
        ]
    return data


def _serialize_task(task):
    assignee = None
    if task.assignee_id:
        try:
            cu = task.assignee
            assignee = {'id': cu.id, 'full_name': cu.full_name, 'email': cu.email}
        except Exception:
            pass
    return {
        'id': task.id,
        'title': task.title,
        'description': task.description,
        'status': task.status,
        'priority': task.priority,
        'due_date': task.due_date if isinstance(task.due_date, str) else (task.due_date.isoformat() if task.due_date else None),
        'estimated_hours': float(task.estimated_hours) if task.estimated_hours else None,
        'ai_reasoning': task.ai_reasoning,
        'assignee': assignee,
        'assignee_id': task.assignee_id,
        'linked_meeting_id': task.linked_meeting_id,
        'created_at': task.created_at.isoformat(),
        'updated_at': task.updated_at.isoformat(),
    }


def _serialize_notification(notif):
    return {
        'id': notif.id,
        'notification_type': notif.notification_type,
        'severity': notif.severity,
        'title': notif.title,
        'message': notif.message,
        'data': notif.data,
        'is_read': notif.is_read,
        'meeting_id': notif.meeting_id,
        'created_at': notif.created_at.isoformat(),
    }


# ===========================================================================
# MEETINGS
# ===========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def schedule_meeting_ai(request):
    """Parse a natural-language meeting request and optionally create the meeting."""
    company_user = request.user
    message = request.data.get('message', '').strip()
    create = request.data.get('create', False)

    if not message:
        return Response({'status': 'error', 'message': 'message is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        agent = _get_agent('meeting_scheduling', company_user)
        parsed = agent.parse_meeting_request(message, company_user.id)

        if not parsed:
            return Response({'status': 'error', 'message': 'Could not parse meeting request.'}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        result = {'status': 'success', 'parsed': parsed}

        if create:
            scheduled_at = _parse_datetime(parsed.get('scheduled_at'))
            if not scheduled_at:
                return Response({'status': 'error', 'message': 'Could not determine meeting time.'}, status=status.HTTP_400_BAD_REQUEST)

            duration = int(parsed.get('duration_minutes') or 60)
            conflicts = agent.check_conflicts(company_user.id, scheduled_at, duration)

            if conflicts:
                result['conflicts'] = conflicts
                result['message'] = 'Meeting has conflicts. Review before creating.'
            else:
                meeting = ExecutiveMeeting.objects.create(
                    organizer=company_user,
                    title=parsed.get('title', 'Executive Meeting'),
                    description=parsed.get('description', ''),
                    agenda=parsed.get('agenda', []),
                    location=parsed.get('location', ''),
                    meeting_link=parsed.get('meeting_link', ''),
                    scheduled_at=scheduled_at,
                    duration_minutes=duration,
                    timezone_name=parsed.get('timezone_name', 'UTC'),
                    recurrence=parsed.get('recurrence', 'none'),
                    recurrence_end_date=parsed.get('recurrence_end_date'),
                )
                result['meeting'] = _serialize_meeting(meeting)
                result['message'] = 'Meeting created successfully.'

        return Response(result, status=status.HTTP_200_OK)
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("schedule_meeting_ai error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_list(request):
    """List meetings or create one manually."""
    company_user = request.user

    if request.method == 'GET':
        status_filter = request.query_params.get('status')
        qs = ExecutiveMeeting.objects.filter(organizer=company_user).select_related('organizer')
        if status_filter:
            qs = qs.filter(status=status_filter)
        data = [_serialize_meeting(m) for m in qs[:50]]
        return Response({'status': 'success', 'meetings': data, 'count': len(data)})

    # POST — manual create
    title = request.data.get('title', '').strip()
    scheduled_at_str = request.data.get('scheduled_at', '')
    if not title or not scheduled_at_str:
        return Response({'status': 'error', 'message': 'title and scheduled_at are required.'}, status=status.HTTP_400_BAD_REQUEST)

    scheduled_at = _parse_datetime(scheduled_at_str)
    if not scheduled_at:
        return Response({'status': 'error', 'message': 'Invalid scheduled_at format. Use ISO 8601.'}, status=status.HTTP_400_BAD_REQUEST)

    meeting_link = request.data.get('meeting_link', '').strip()
    if not meeting_link:
        import secrets, string
        slug = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10))
        meeting_link = f'https://meet.jit.si/exec-{slug}'

    meeting = ExecutiveMeeting.objects.create(
        organizer=company_user,
        title=title,
        description=request.data.get('description', ''),
        agenda=request.data.get('agenda', []),
        location=request.data.get('location', ''),
        meeting_link=meeting_link,
        scheduled_at=scheduled_at,
        duration_minutes=int(request.data.get('duration_minutes', 60)),
        timezone_name=request.data.get('timezone_name', 'UTC'),
        recurrence=request.data.get('recurrence', 'none'),
    )
    return Response({'status': 'success', 'meeting': _serialize_meeting(meeting)}, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_detail(request, meeting_id):
    """Get, update, or delete a meeting."""
    company_user = request.user
    meeting = get_object_or_404(ExecutiveMeeting, id=meeting_id, organizer=company_user)

    if request.method == 'GET':
        return Response({'status': 'success', 'meeting': _serialize_meeting(meeting, include_participants=True)})

    if request.method == 'PATCH':
        updatable = ['title', 'description', 'agenda', 'location', 'meeting_link',
                     'duration_minutes', 'timezone_name', 'status', 'recurrence']
        for field in updatable:
            if field in request.data:
                setattr(meeting, field, request.data[field])
        if 'scheduled_at' in request.data:
            dt = _parse_datetime(request.data['scheduled_at'])
            if dt:
                meeting.scheduled_at = dt
        meeting.save()
        return Response({'status': 'success', 'meeting': _serialize_meeting(meeting)})

    if request.method == 'DELETE':
        meeting.status = 'cancelled'
        meeting.save()
        return Response({'status': 'success', 'message': 'Meeting cancelled.'})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def search_company_users(request):
    """Search company users by name/email for participant autocomplete.

    Returns both CompanyUser records and UserProfile-backed users that belong
    to the same company, so users added via the admin 'Add User' panel also
    appear in the results.
    """
    from core.models import CompanyUser, UserProfile
    company_user = request.user
    q = request.query_params.get('q', '').strip()
    if len(q) < 2:
        return Response({'status': 'success', 'users': []})

    # 1. CompanyUser accounts (self-registered via invitation link)
    cu_qs = CompanyUser.objects.filter(
        company=company_user.company,
        is_active=True,
    ).filter(
        models.Q(full_name__icontains=q) | models.Q(email__icontains=q)
    ).values('id', 'full_name', 'email', 'role')[:10]
    results = list(cu_qs)

    # 2. UserProfile-backed users created via the admin panel
    existing_emails = {u['email'] for u in results}
    up_qs = UserProfile.objects.filter(
        company=company_user.company,
    ).filter(
        models.Q(user__first_name__icontains=q)
        | models.Q(user__last_name__icontains=q)
        | models.Q(user__email__icontains=q)
        | models.Q(user__username__icontains=q)
    ).select_related('user').exclude(user__email__in=existing_emails)[:10]

    for up in up_qs:
        u = up.user
        full_name = f"{u.first_name} {u.last_name}".strip() or u.username
        results.append({
            'id': up.id,
            'full_name': full_name,
            'email': u.email,
            'role': up.role or 'team_member',
            # tag so frontend knows this is a UserProfile, not a CompanyUser
            'user_type': 'profile',
        })

    return Response({'status': 'success', 'users': results[:10]})


@api_view(['GET', 'POST', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_participants(request, meeting_id):
    """List, add, or remove participants from a meeting."""
    from core.models import CompanyUser
    company_user = request.user
    meeting = get_object_or_404(ExecutiveMeeting, id=meeting_id, organizer=company_user)

    if request.method == 'GET':
        parts = meeting.participants.select_related('company_user').all()
        return Response({'status': 'success', 'participants': [
            {'id': p.id, 'user_id': p.company_user.id,
             'full_name': p.company_user.full_name, 'email': p.company_user.email,
             'role': p.company_user.role, 'response': p.response}
            for p in parts
        ]})

    if request.method == 'POST':
        from django.contrib.auth.hashers import make_password as _make_password
        import secrets as _secrets
        user_id = request.data.get('user_id')
        user_type = request.data.get('user_type', 'company_user')
        if not user_id:
            return Response({'status': 'error', 'message': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        if user_type == 'profile':
            # UserProfile-backed user: resolve via UserProfile and create/find a CompanyUser mirror
            from core.models import UserProfile
            try:
                up = UserProfile.objects.select_related('user').get(id=user_id, company=company_user.company)
            except UserProfile.DoesNotExist:
                return Response({'status': 'error', 'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
            u = up.user
            full_name = f"{u.first_name} {u.last_name}".strip() or u.username
            role = up.role or 'company_user'
            # Get or create a CompanyUser mirror so we can use it in the participant FK
            target, _ = CompanyUser.objects.get_or_create(
                company=company_user.company,
                email=u.email,
                defaults={
                    'full_name': full_name,
                    'role': role,
                    'password_hash': _make_password(_secrets.token_urlsafe(16)),
                    'is_active': True,
                },
            )
        else:
            try:
                target = CompanyUser.objects.get(id=user_id, company=company_user.company, is_active=True)
            except CompanyUser.DoesNotExist:
                return Response({'status': 'error', 'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        p, created = ExecutiveMeetingParticipant.objects.get_or_create(meeting=meeting, company_user=target)
        return Response({'status': 'success', 'participant': {
            'id': p.id, 'user_id': target.id, 'full_name': target.full_name,
            'email': target.email, 'role': target.role, 'response': p.response,
        }}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    if request.method == 'DELETE':
        user_id = request.data.get('user_id')
        ExecutiveMeetingParticipant.objects.filter(meeting=meeting, company_user_id=user_id).delete()
        return Response({'status': 'success'})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_respond(request, meeting_id):
    """Accept, reject, or counter-propose a meeting invitation."""
    company_user = request.user
    meeting = get_object_or_404(ExecutiveMeeting, id=meeting_id)
    response_val = request.data.get('response', '').strip()
    reason = request.data.get('reason', '')
    counter_time_str = request.data.get('counter_proposed_time', '')

    valid_responses = ['accepted', 'rejected', 'tentative', 'counter_proposed']
    if response_val not in valid_responses:
        return Response({'status': 'error', 'message': f'response must be one of {valid_responses}'}, status=status.HTTP_400_BAD_REQUEST)

    participant, _ = ExecutiveMeetingParticipant.objects.get_or_create(
        meeting=meeting, company_user=company_user,
    )
    participant.response = response_val
    participant.reason = reason
    participant.responded_at = timezone.now()

    if response_val == 'counter_proposed' and counter_time_str:
        ct = _parse_datetime(counter_time_str)
        if ct:
            participant.counter_proposed_time = ct

    participant.save()

    # Notify organizer
    ExecNotification.objects.create(
        company_user=meeting.organizer,
        notification_type='participant_response',
        severity='info',
        title=f"{company_user.full_name} {response_val} your meeting",
        message=f"{company_user.full_name} has {response_val} the meeting '{meeting.title}'." + (f" Reason: {reason}" if reason else ''),
        meeting=meeting,
        data={'participant_id': company_user.id, 'response': response_val, 'meeting_id': meeting.id},
    )

    return Response({'status': 'success', 'participant': {
        'response': participant.response,
        'responded_at': participant.responded_at.isoformat(),
    }})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def meeting_suggest_slots(request):
    """Suggest free time slots for a meeting."""
    company_user = request.user
    preferred_date = request.query_params.get('date', timezone.now().strftime('%Y-%m-%d'))
    duration = int(request.query_params.get('duration_minutes', 60))
    num_slots = min(int(request.query_params.get('num_slots', 5)), 10)

    try:
        agent = _get_agent('meeting_scheduling', company_user)
        slots = agent.suggest_available_slots(company_user.id, preferred_date, duration, num_slots)
        return Response({'status': 'success', 'slots': slots, 'date': preferred_date})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("meeting_suggest_slots error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# MEETING NOTES
# ===========================================================================

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def meeting_notes(request, meeting_id):
    """Get or submit notes/transcript for a meeting."""
    company_user = request.user
    meeting = get_object_or_404(ExecutiveMeeting, id=meeting_id, organizer=company_user)

    if request.method == 'GET':
        try:
            note = meeting.note
            action_items = list(meeting.action_items.values(
                'id', 'title', 'description', 'status', 'priority',
                'due_date', 'ai_extracted', 'assignee_id',
            ))
            return Response({'status': 'success', 'notes': {
                'id': note.id,
                'ai_summary': note.ai_summary,
                'key_decisions': note.key_decisions,
                'raw_transcript': note.raw_transcript,
                'action_items': action_items,
            }})
        except MeetingNote.DoesNotExist:
            return Response({'status': 'success', 'notes': None})

    # POST — process transcript with AI
    transcript = request.data.get('transcript', '').strip()
    if not transcript:
        return Response({'status': 'error', 'message': 'transcript is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        agent = _get_agent('meeting_notetaker', company_user)
        participant_names = list(
            meeting.participants.select_related('company_user').values_list('company_user__full_name', flat=True)
        )
        result = agent.process_full_transcript(transcript, meeting.title, participant_names)

        note, _ = MeetingNote.objects.update_or_create(
            meeting=meeting,
            defaults={
                'raw_transcript': transcript,
                'ai_summary': result.get('summary', ''),
                'key_decisions': result.get('key_decisions', []),
            },
        )

        # Save AI-extracted action items
        created_items = []
        for item_data in result.get('action_items', []):
            item = MeetingActionItem.objects.create(
                meeting=meeting,
                title=item_data.get('title', 'Action Item'),
                description=item_data.get('description', ''),
                due_date=item_data.get('due_date') or None,
                priority=item_data.get('priority', 'medium'),
                ai_extracted=True,
            )
            created_items.append({'id': item.id, 'title': item.title})

        return Response({'status': 'success', 'notes': {
            'ai_summary': note.ai_summary,
            'key_decisions': note.key_decisions,
            'action_items_created': len(created_items),
            'followup_email': result.get('followup_email', ''),
        }})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("meeting_notes POST error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# ACTION ITEMS
# ===========================================================================

@api_view(['GET', 'PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def action_item_detail(request, item_id):
    """Update or view a meeting action item."""
    company_user = request.user
    item = get_object_or_404(MeetingActionItem, id=item_id, meeting__organizer=company_user)

    if request.method == 'GET':
        return Response({'status': 'success', 'action_item': {
            'id': item.id, 'title': item.title, 'description': item.description,
            'status': item.status, 'priority': item.priority,
            'due_date': item.due_date.isoformat() if item.due_date else None,
            'assignee_id': item.assignee_id, 'ai_extracted': item.ai_extracted,
        }})

    for field in ['title', 'description', 'status', 'priority']:
        if field in request.data:
            setattr(item, field, request.data[field])
    if 'due_date' in request.data:
        item.due_date = request.data['due_date'] or None
    if 'assignee_id' in request.data:
        item.assignee_id = request.data['assignee_id'] or None
    item.save()
    return Response({'status': 'success', 'message': 'Action item updated.'})


# ===========================================================================
# TASKS
# ===========================================================================

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def task_list(request):
    """List tasks or create one."""
    company_user = request.user

    if request.method == 'GET':
        status_filter = request.query_params.get('status')
        priority_filter = request.query_params.get('priority')
        qs = ExecutiveTask.objects.filter(company_user=company_user)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        return Response({'status': 'success', 'tasks': [_serialize_task(t) for t in qs[:100]], 'count': qs.count()})

    title = request.data.get('title', '').strip()
    if not title:
        return Response({'status': 'error', 'message': 'title is required.'}, status=status.HTTP_400_BAD_REQUEST)

    assignee_id = request.data.get('assignee_id') or None
    assignee_user_type = request.data.get('assignee_user_type', 'company_user')
    assignee = None
    if assignee_id:
        from core.models import CompanyUser as _CU, UserProfile as _UP
        import secrets as _sec
        from django.contrib.auth.hashers import make_password as _mkpw
        if assignee_user_type == 'profile':
            try:
                up = _UP.objects.select_related('user').get(id=assignee_id, company=company_user.company)
                u = up.user
                full_name = f"{u.first_name} {u.last_name}".strip() or u.username
                assignee, _ = _CU.objects.get_or_create(
                    company=company_user.company, email=u.email,
                    defaults={'full_name': full_name, 'role': up.role or 'company_user',
                              'password_hash': _mkpw(_sec.token_urlsafe(16)), 'is_active': True},
                )
            except _UP.DoesNotExist:
                pass
        else:
            try:
                assignee = _CU.objects.get(id=assignee_id, company=company_user.company)
            except _CU.DoesNotExist:
                pass

    task = ExecutiveTask.objects.create(
        company_user=company_user,
        title=title,
        description=request.data.get('description', ''),
        status=request.data.get('status', 'todo'),
        priority=request.data.get('priority', 'medium'),
        due_date=request.data.get('due_date') or None,
        linked_meeting_id=request.data.get('linked_meeting_id') or None,
        assignee=assignee,
    )
    return Response({'status': 'success', 'task': _serialize_task(task)}, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def task_detail(request, task_id):
    """Get, update, or delete a task."""
    company_user = request.user
    task = get_object_or_404(ExecutiveTask, id=task_id, company_user=company_user)

    if request.method == 'GET':
        return Response({'status': 'success', 'task': _serialize_task(task)})

    if request.method == 'PATCH':
        for field in ['title', 'description', 'status', 'priority', 'due_date', 'ai_reasoning']:
            if field in request.data:
                setattr(task, field, request.data[field] or None if field == 'due_date' else request.data[field])
        if 'estimated_hours' in request.data:
            task.estimated_hours = request.data['estimated_hours'] or None
        if 'assignee_id' in request.data:
            aid = request.data['assignee_id']
            if not aid:
                task.assignee = None
            else:
                from core.models import CompanyUser as _CU
                try:
                    task.assignee = _CU.objects.get(id=aid, company=company_user.company)
                except _CU.DoesNotExist:
                    pass
        task.save()
        return Response({'status': 'success', 'task': _serialize_task(task)})

    task.delete()
    return Response({'status': 'success', 'message': 'Task deleted.'})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def task_prioritize_ai(request):
    """AI-prioritize a set of tasks."""
    company_user = request.user
    task_ids = request.data.get('task_ids', [])
    context = request.data.get('context', '')

    tasks_qs = ExecutiveTask.objects.filter(company_user=company_user)
    if task_ids:
        tasks_qs = tasks_qs.filter(id__in=task_ids)

    tasks_data = [_serialize_task(t) for t in tasks_qs[:30]]
    if not tasks_data:
        return Response({'status': 'error', 'message': 'No tasks found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        agent = _get_agent('task_prioritization', company_user)
        result = agent.prioritize_tasks(tasks_data, context)

        # Apply AI priorities back to DB
        updated = 0
        for item in result:
            tid = item.get('id')
            if tid:
                try:
                    t = ExecutiveTask.objects.get(id=tid, company_user=company_user)
                    if item.get('priority') in ['low', 'medium', 'high', 'critical']:
                        t.priority = item['priority']
                    if item.get('ai_reasoning'):
                        t.ai_reasoning = item['ai_reasoning']
                    if item.get('suggested_due_date') and not t.due_date:
                        from datetime import date
                        try:
                            t.due_date = datetime.strptime(item['suggested_due_date'], '%Y-%m-%d').date()
                        except ValueError:
                            pass
                    t.save(update_fields=['priority', 'ai_reasoning', 'due_date'])
                    updated += 1
                except ExecutiveTask.DoesNotExist:
                    pass

        return Response({'status': 'success', 'prioritized': result, 'updated_count': updated})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("task_prioritize_ai error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def task_workload_analysis(request):
    """Analyze workload for the current user."""
    company_user = request.user
    tasks_data = [_serialize_task(t) for t in ExecutiveTask.objects.filter(company_user=company_user)[:50]]
    try:
        agent = _get_agent('task_prioritization', company_user)
        analysis = agent.analyze_workload(tasks_data, company_user.full_name)
        return Response({'status': 'success', 'analysis': analysis})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("task_workload_analysis error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# CALENDAR
# ===========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def calendar_plan_week(request):
    """Generate an AI weekly calendar plan."""
    company_user = request.user
    week_start = request.data.get('week_start', timezone.now().strftime('%Y-%m-%d'))

    meetings = [
        {
            'id': m.id, 'title': m.title,
            'scheduled_at': m.scheduled_at.isoformat(),
            'duration_minutes': m.duration_minutes,
            'status': m.status,
        }
        for m in ExecutiveMeeting.objects.filter(
            organizer=company_user,
            scheduled_at__date__gte=week_start,
            status__in=['scheduled', 'in_progress'],
        )[:30]
    ]

    tasks = [_serialize_task(t) for t in ExecutiveTask.objects.filter(
        company_user=company_user, status__in=['todo', 'in_progress']
    )[:30]]

    try:
        agent = _get_agent('calendar_planner', company_user)
        plan = agent.plan_week(meetings, tasks, week_start)
        return Response({'status': 'success', 'plan': plan})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("calendar_plan_week error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def calendar_free_slots(request):
    """Get free calendar slots for a given date."""
    company_user = request.user
    date = request.query_params.get('date', timezone.now().strftime('%Y-%m-%d'))
    duration = int(request.query_params.get('duration_minutes', 60))

    try:
        agent = _get_agent('calendar_planner', company_user)
        slots = agent.get_free_slots(company_user.id, date, duration)
        return Response({'status': 'success', 'slots': slots, 'date': date})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("calendar_free_slots error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# DOCUMENTS
# ===========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def document_draft(request):
    """AI-draft a meeting document (agenda, minutes, briefing, report)."""
    company_user = request.user
    doc_type = request.data.get('doc_type', 'agenda')
    meeting_id = request.data.get('meeting_id')
    save = request.data.get('save', False)

    valid_doc_types = ['agenda', 'minutes', 'briefing', 'report']
    if doc_type not in valid_doc_types:
        return Response({'status': 'error', 'message': f'doc_type must be one of {valid_doc_types}'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        agent = _get_agent('document_authoring', company_user)
        meeting = None
        if meeting_id:
            try:
                meeting = ExecutiveMeeting.objects.get(id=meeting_id, organizer=company_user)
            except ExecutiveMeeting.DoesNotExist:
                pass

        if doc_type == 'agenda':
            topics = request.data.get('topics', [])
            attendees = request.data.get('attendees', [])
            if meeting and not topics:
                topics = meeting.agenda or []
            if meeting and not attendees:
                attendees = list(meeting.participants.values_list('company_user__full_name', flat=True))
            content = agent.draft_agenda(
                meeting.title if meeting else request.data.get('title', 'Meeting'),
                meeting.duration_minutes if meeting else int(request.data.get('duration_minutes', 60)),
                topics, attendees, request.data.get('context', ''),
            )

        elif doc_type == 'minutes':
            summary = request.data.get('summary', '')
            if meeting and not summary:
                try:
                    summary = meeting.note.ai_summary
                except Exception:
                    summary = ''
            action_items = request.data.get('action_items', [])
            decisions = request.data.get('decisions', [])
            if meeting and not action_items:
                action_items = [{'title': a.title, 'assignee_hint': a.assignee.full_name if a.assignee else None, 'due_date': str(a.due_date) if a.due_date else None} for a in meeting.action_items.all()[:15]]
            if meeting and not decisions:
                try:
                    decisions = meeting.note.key_decisions or []
                except Exception:
                    decisions = []
            attendees_minutes = request.data.get('attendees', [])
            if meeting and not attendees_minutes:
                attendees_minutes = list(meeting.participants.values_list('company_user__full_name', flat=True))
            content = agent.write_minutes(
                meeting.title if meeting else request.data.get('title', 'Meeting'),
                request.data.get('date', timezone.now().strftime('%Y-%m-%d')),
                attendees_minutes,
                summary, action_items, decisions,
            )

        elif doc_type == 'briefing':
            content = agent.create_briefing(
                request.data.get('topic', ''),
                request.data.get('context', ''),
                request.data.get('key_points'),
                request.data.get('audience', 'Executive Team'),
            )

        else:  # report
            content = agent.draft_report(
                request.data.get('report_type', 'Status'),
                request.data.get('data', {}),
                request.data.get('period', ''),
            )

        result = {'status': 'success', 'doc_type': doc_type, 'content': content}

        # Always auto-save as standalone document
        from meeting_agent.models import ExecStandaloneDocument
        doc_title = request.data.get('title', '') or (meeting.title if meeting else 'Untitled')
        standalone = ExecStandaloneDocument.objects.create(
            company_user=company_user,
            doc_type=doc_type,
            title=f"{doc_type.capitalize()} — {doc_title}",
            content=content,
            ai_generated=True,
        )
        result['document_id'] = standalone.id

        if save and meeting:
            MeetingDocument.objects.create(
                meeting=meeting,
                created_by=company_user,
                doc_type=doc_type,
                title=doc_title,
                content=content,
                ai_generated=True,
            )

        return Response(result)
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("document_draft error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def meeting_documents(request, meeting_id):
    """List documents for a meeting."""
    company_user = request.user
    meeting = get_object_or_404(ExecutiveMeeting, id=meeting_id, organizer=company_user)
    docs = meeting.documents.filter(created_by=company_user)
    return Response({'status': 'success', 'documents': [
        {'id': d.id, 'doc_type': d.doc_type, 'title': d.title, 'ai_generated': d.ai_generated,
         'content': d.content, 'created_at': d.created_at.isoformat()}
        for d in docs
    ]})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def standalone_document_list(request):
    """List all AI-generated standalone documents for the company user."""
    from meeting_agent.models import ExecStandaloneDocument
    company_user = request.user
    doc_type = request.query_params.get('doc_type')
    qs = ExecStandaloneDocument.objects.filter(company_user=company_user)
    if doc_type:
        qs = qs.filter(doc_type=doc_type)
    docs = [
        {
            'id': d.id, 'doc_type': d.doc_type, 'title': d.title,
            'content': d.content, 'ai_generated': d.ai_generated,
            'created_at': d.created_at.isoformat(),
        }
        for d in qs[:100]
    ]
    return Response({'status': 'success', 'documents': docs, 'count': len(docs)})


@api_view(['GET', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def standalone_document_detail(request, doc_id):
    """Get or delete a standalone document."""
    from meeting_agent.models import ExecStandaloneDocument
    company_user = request.user
    doc = get_object_or_404(ExecStandaloneDocument, id=doc_id, company_user=company_user)
    if request.method == 'DELETE':
        doc.delete()
        return Response({'status': 'success', 'message': 'Document deleted.'})
    return Response({
        'status': 'success',
        'document': {
            'id': doc.id, 'doc_type': doc.doc_type, 'title': doc.title,
            'content': doc.content, 'ai_generated': doc.ai_generated,
            'created_at': doc.created_at.isoformat(),
        },
    })


# ===========================================================================
# NOTIFICATIONS
# ===========================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def notification_list(request):
    """List notifications for the current user."""
    company_user = request.user
    unread_only = request.query_params.get('unread', 'false').lower() == 'true'
    severity = request.query_params.get('severity')

    qs = ExecNotification.objects.filter(company_user=company_user)
    if unread_only:
        qs = qs.filter(is_read=False)
    if severity:
        qs = qs.filter(severity=severity)

    notifications = [_serialize_notification(n) for n in qs[:50]]
    unread_count = ExecNotification.objects.filter(company_user=company_user, is_read=False).count()
    return Response({'status': 'success', 'notifications': notifications, 'unread_count': unread_count})


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def notification_mark_read(request, notification_id):
    """Mark a notification as read."""
    company_user = request.user
    notif = get_object_or_404(ExecNotification, id=notification_id, company_user=company_user)
    notif.is_read = True
    notif.save(update_fields=['is_read'])
    return Response({'status': 'success', 'message': 'Notification marked as read.'})


@api_view(['PATCH'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def notification_mark_all_read(request):
    """Mark all notifications as read."""
    company_user = request.user
    ExecNotification.objects.filter(company_user=company_user, is_read=False).update(is_read=True)
    return Response({'status': 'success', 'message': 'All notifications marked as read.'})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def notification_daily_digest(request):
    """Get AI-generated daily digest."""
    company_user = request.user
    try:
        agent = _get_agent('proactive_notification', company_user)
        digest = agent.generate_daily_digest(company_user.id, company_user.full_name)
        return Response({'status': 'success', 'digest': digest})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("notification_daily_digest error: %s", e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# CHAT — generic endpoint for any sub-agent
# ===========================================================================

_CHAT_MODEL_MAP = {
    'meeting_scheduling': (ExecMeetingSchedulingChat, ExecMeetingSchedulingChatMessage),
    'meeting_notetaker': (ExecNotetakerChat, ExecNotetakerChatMessage),
    'task_prioritization': (ExecTaskChat, ExecTaskChatMessage),
    'calendar_planner': (ExecCalendarChat, ExecCalendarChatMessage),
    'document_authoring': (ExecDocumentChat, ExecDocumentChatMessage),
    'proactive_notification': (ExecNotificationChat, ExecNotificationChatMessage),
}

_CHAT_SYSTEM_PROMPTS = {
    'meeting_scheduling': "You are the Meeting Scheduling Agent for the AI Executive Meeting Assistant. Help the user schedule, reschedule, and manage executive meetings.",
    'meeting_notetaker': "You are the Meeting Notetaker Agent. Help the user capture, summarize, and follow up on meeting notes and action items.",
    'task_prioritization': "You are the Task & Prioritization Agent. Help the user manage, prioritize, and track executive tasks.",
    'calendar_planner': "You are the Calendar Auto-planner Agent. Help the user optimize their calendar and schedule.",
    'document_authoring': "You are the Document Authoring Agent. Help the user draft agendas, minutes, briefings, and reports.",
    'proactive_notification': "You are the Proactive Notification Agent. Help the user stay on top of their meetings, tasks, and deadlines.",
}


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecCRUDThrottle])
def chat_list(request, agent_name):
    """List chats or create a new chat for a sub-agent."""
    if agent_name not in _CHAT_MODEL_MAP:
        return Response({'status': 'error', 'message': f'Unknown agent: {agent_name}'}, status=status.HTTP_404_NOT_FOUND)

    company_user = request.user
    ChatModel, _ = _CHAT_MODEL_MAP[agent_name]

    if request.method == 'GET':
        chats = ChatModel.objects.filter(company_user=company_user)[:20]
        return Response({'status': 'success', 'chats': [
            {'id': c.id, 'title': c.title, 'created_at': c.created_at.isoformat(), 'updated_at': c.updated_at.isoformat()}
            for c in chats
        ]})

    chat = ChatModel.objects.create(
        company_user=company_user,
        title=request.data.get('title', 'Chat'),
    )
    return Response({'status': 'success', 'chat': {'id': chat.id, 'title': chat.title}}, status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([ExecLLMThrottle])
def chat_messages(request, agent_name, chat_id):
    """Get messages or send a message in a sub-agent chat."""
    if agent_name not in _CHAT_MODEL_MAP:
        return Response({'status': 'error', 'message': f'Unknown agent: {agent_name}'}, status=status.HTTP_404_NOT_FOUND)

    company_user = request.user
    ChatModel, MessageModel = _CHAT_MODEL_MAP[agent_name]

    chat = get_object_or_404(ChatModel, id=chat_id, company_user=company_user)

    if request.method == 'GET':
        messages = chat.messages.all()[:100]
        return Response({'status': 'success', 'messages': [
            {'id': m.id, 'role': m.role, 'content': m.content,
             'response_data': m.response_data, 'created_at': m.created_at.isoformat()}
            for m in messages
        ]})

    user_message = request.data.get('message', '').strip()
    if not user_message:
        return Response({'status': 'error', 'message': 'message is required.'}, status=status.HTTP_400_BAD_REQUEST)

    # Save user message
    MessageModel.objects.create(chat=chat, role='user', content=user_message)

    # Build history context for LLM
    history = chat.messages.order_by('-created_at')[:8]
    history_text = '\n'.join([
        f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
        for m in reversed(list(history))
        if m.content != user_message
    ])

    try:
        agent = _get_agent(agent_name, company_user)
        system_prompt = _CHAT_SYSTEM_PROMPTS.get(agent_name, '')
        prompt = f"{history_text}\nUser: {user_message}" if history_text else user_message
        ai_response = agent._call_llm(prompt, system_prompt, temperature=0.5, max_tokens=800)

        msg = MessageModel.objects.create(
            chat=chat, role='assistant', content=ai_response,
            response_data={'agent': agent_name},
        )
        chat.title = user_message[:60] if chat.title == 'Chat' else chat.title
        chat.save(update_fields=['title', 'updated_at'])

        return Response({'status': 'success', 'message': {
            'id': msg.id, 'role': 'assistant', 'content': ai_response,
            'created_at': msg.created_at.isoformat(),
        }})
    except KeyServiceError:
        raise
    except Exception as e:
        logger.error("chat_messages POST error (agent=%s): %s", agent_name, e)
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===========================================================================
# ADMIN ENDPOINTS
# ===========================================================================

from api.permissions import IsAdmin as IsAdminUser


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsAdminUser])
@throttle_classes([ExecCRUDThrottle])
def admin_meeting_list(request):
    """Admin: list all meetings across all companies."""
    company_id = request.query_params.get('company_id')
    status_filter = request.query_params.get('status')
    qs = ExecutiveMeeting.objects.select_related('organizer', 'organizer__company').all()
    if company_id:
        qs = qs.filter(organizer__company_id=company_id)
    if status_filter:
        qs = qs.filter(status=status_filter)
    data = []
    for m in qs[:100]:
        s = _serialize_meeting(m)
        s['company_id'] = m.organizer.company_id
        s['company_name'] = getattr(m.organizer.company, 'name', '') if hasattr(m.organizer, 'company') else ''
        data.append(s)
    return Response({'status': 'success', 'meetings': data, 'count': len(data)})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsAdminUser])
@throttle_classes([ExecCRUDThrottle])
def admin_task_list(request):
    """Admin: list all executive tasks across all companies."""
    company_id = request.query_params.get('company_id')
    priority_filter = request.query_params.get('priority')
    status_filter = request.query_params.get('status')
    qs = ExecutiveTask.objects.select_related('company_user', 'company_user__company').all()
    if company_id:
        qs = qs.filter(company_user__company_id=company_id)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)
    data = []
    for t in qs[:100]:
        s = _serialize_task(t)
        s['company_user_name'] = t.company_user.full_name
        s['company_id'] = t.company_user.company_id
        data.append(s)
    return Response({'status': 'success', 'tasks': data, 'count': len(data)})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsAdminUser])
@throttle_classes([ExecCRUDThrottle])
def admin_notification_list(request):
    """Admin: list all notifications across all companies."""
    company_id = request.query_params.get('company_id')
    severity_filter = request.query_params.get('severity')
    qs = ExecNotification.objects.select_related('company_user').all()
    if company_id:
        qs = qs.filter(company_user__company_id=company_id)
    if severity_filter:
        qs = qs.filter(severity=severity_filter)
    data = []
    for n in qs[:100]:
        s = _serialize_notification(n)
        s['company_user_name'] = n.company_user.full_name
        s['company_id'] = n.company_user.company_id
        data.append(s)
    return Response({'status': 'success', 'notifications': data, 'count': len(data)})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsAdminUser])
@throttle_classes([ExecCRUDThrottle])
def admin_stats(request):
    """Admin: aggregate stats for the AI Executive Meeting Assistant."""
    from django.db.models import Count
    company_id = request.query_params.get('company_id')

    meeting_qs = ExecutiveMeeting.objects.all()
    task_qs = ExecutiveTask.objects.all()
    notif_qs = ExecNotification.objects.all()

    if company_id:
        meeting_qs = meeting_qs.filter(organizer__company_id=company_id)
        task_qs = task_qs.filter(company_user__company_id=company_id)
        notif_qs = notif_qs.filter(company_user__company_id=company_id)

    return Response({'status': 'success', 'stats': {
        'meetings': {
            'total': meeting_qs.count(),
            'by_status': dict(meeting_qs.values_list('status').annotate(c=Count('id')).values_list('status', 'c')),
        },
        'tasks': {
            'total': task_qs.count(),
            'by_priority': dict(task_qs.values_list('priority').annotate(c=Count('id')).values_list('priority', 'c')),
            'by_status': dict(task_qs.values_list('status').annotate(c=Count('id')).values_list('status', 'c')),
        },
        'notifications': {
            'total': notif_qs.count(),
            'unread': notif_qs.filter(is_read=False).count(),
            'by_severity': dict(notif_qs.values_list('severity').annotate(c=Count('id')).values_list('severity', 'c')),
        },
    }})
