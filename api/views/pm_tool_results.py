"""Project Manager: what the AI tools made for a project, opened again and acted on.

Saved phase checklists (Workflow & SOP) with items ticked off for good, saved meeting notes, the latest schedule plan
and its .ics download, and "create tasks" from a checklist or a meeting's action items. The saving itself happens in
the tools' own endpoints (api/views/pm_agent.py); the rules are in project_manager_agent/tool_results.py.
"""
import logging

from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from api.views.pm_agent import PMCRUDThrottle
from core.tenancy import projects_for_company_user
from project_manager_agent import services as pm_services
from project_manager_agent import project_record as record
from project_manager_agent import tool_results
from project_manager_agent.models import ProjectToolResult

logger = logging.getLogger(__name__)

NOT_FOUND = {'status': 'error', 'message': 'Project not found'}


def _project(request, project_id):
    return projects_for_company_user(request.user).filter(pk=project_id).first()


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def saved_checklist(request, project_id, phase):
    """The phase's saved checklist, or null when none has been made."""
    project = _project(request, project_id)
    if project is None:
        return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
    row = ProjectToolResult.objects.filter(project=project, kind=tool_results.CHECKLIST, key=phase[:60]).first()
    return Response({'status': 'success', 'data': tool_results.checklist_payload(row) if row else None})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def tick_checklist_item(request, result_id, index):
    """Tick an item off a saved checklist, or untick it: {"done": true|false}."""
    row = ProjectToolResult.objects.filter(
        pk=result_id, kind=tool_results.CHECKLIST,
        project__in=projects_for_company_user(request.user)).first()
    if row is None:
        return Response({'status': 'error', 'message': 'Checklist not found'}, status=status.HTTP_404_NOT_FOUND)
    if not tool_results.set_item_done(row, int(index), request.data.get('done') is True):
        return Response({'status': 'error', 'message': 'No such item'}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'status': 'success', 'data': tool_results.checklist_payload(row)})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def tasks_from_suggestions(request, project_id):
    """Create project tasks from suggestions (checklist items, meeting action items).

    Body: {"items": [{"title", "description"?, "priority"?, "assignee_id"? or "assignee_name"?, "due"?}]}.
    A name is matched to the one company member it fits; a due date outside the project's dates is left out.
    """
    project = _project(request, project_id)
    if project is None:
        return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
    items = request.data.get('items')
    if not isinstance(items, list) or not any(isinstance(i, dict) and str(i.get('title') or '').strip()
                                              for i in items):
        return Response({'status': 'error', 'message': 'Choose at least one item to turn into a task.'},
                        status=status.HTTP_400_BAD_REQUEST)
    actor = pm_services.DashboardActor(request.user, request)
    created, problems = tool_results.create_tasks(actor, project, [i for i in items if isinstance(i, dict)])
    return Response({'status': 'success', 'data': {
        'created': [{'id': t.id, 'title': t.title, 'assignee_id': t.assignee_id,
                     'due_date': t.due_date.isoformat() if t.due_date else None} for t in created],
        'problems': problems,
    }}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def saved_meeting_notes(request, project_id):
    """The project's saved meeting notes, newest first; ?id= opens one with its full text."""
    project = _project(request, project_id)
    if project is None:
        return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
    rows = ProjectToolResult.objects.filter(project=project, kind=tool_results.MEETING_NOTES)
    one = request.GET.get('id')
    if one:
        row = rows.filter(pk=one).first()
        if row is None:
            return Response({'status': 'error', 'message': 'Notes not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'status': 'success', 'data': tool_results.meeting_notes_payload(row, with_text=True)})
    return Response({'status': 'success', 'data': [
        tool_results.meeting_notes_payload(r) for r in rows.order_by('-created_at')[:tool_results.MEETING_NOTES_KEPT]]})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def saved_schedule_plan(request, project_id):
    """The project's latest schedule plan, or null."""
    project = _project(request, project_id)
    if project is None:
        return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
    row = ProjectToolResult.objects.filter(project=project, kind=tool_results.SCHEDULE_PLAN).first()
    data = {'id': row.id, 'saved_at': row.updated_at.isoformat(), **row.data} if row else None
    return Response({'status': 'success', 'data': data})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def schedule_plan_ics(request, project_id):
    """The latest plan as an .ics: the work planned for the person asking, or ?everyone=1 for the whole team.

    Downloaded into a person's own calendar only. It is not booked into the shared busy-time table: planned work
    would then refuse meetings.
    """
    from core.scheduling.identity import login_user_id_for_company_user
    from project_manager_agent.ics_generator import generate_plan_ics

    project = _project(request, project_id)
    if project is None:
        return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
    row = ProjectToolResult.objects.filter(project=project, kind=tool_results.SCHEDULE_PLAN).first()
    if row is None:
        return Response({'status': 'error', 'message': 'Make a schedule for this project first.'},
                        status=status.HTTP_404_NOT_FOUND)
    everyone = request.GET.get('everyone') in ('1', 'true')
    user_id = None if everyone else login_user_id_for_company_user(request.user)
    if not everyone and user_id is None:
        return Response({'status': 'error', 'message': 'You have no tasks in this plan.'},
                        status=status.HTTP_404_NOT_FOUND)
    assignments = tool_results.assignments_for(row.data, user_id)
    if not assignments:
        return Response({'status': 'error', 'message': 'There is nothing planned for you in this schedule.'},
                        status=status.HTTP_404_NOT_FOUND)
    response = HttpResponse(generate_plan_ics(project, assignments), content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="plan-{project.id}.ics"'
    return response


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def project_record(request, project_id):
    """What was decided and done on the project, in date order, with what is due, late and at risk:
    Meeting Notes → Project record. Built from stored entries; no AI call."""
    project = _project(request, project_id)
    if project is None:
        return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
    return Response({'status': 'success', 'data': record.build(project)})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
@throttle_classes([PMCRUDThrottle])
def company_record(request):
    """All projects at once: Meeting Notes → Project record with "All projects" chosen. What was added, changed,
    removed and confirmed across the company, day by day, then where each project stands. No AI call."""
    return Response({'status': 'success', 'data': record.build_company(request.user)})
