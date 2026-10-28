"""Recruitment workflows (SOPs): the list, the editor, templates, a test run and run history.

GET    recruitment/workflows                     the company's workflows, the events, step types and templates
POST   recruitment/workflows                     make one (owner or admin)
PATCH  recruitment/workflows/<id>                change one (owner or admin)
DELETE recruitment/workflows/<id>                delete one (owner or admin)
POST   recruitment/workflows/from-template       {template_key}: make one from a template (owner or admin)
POST   recruitment/workflows/<id>/test           {cv_record_id?}: a test run on a candidate; nothing is sent
GET    recruitment/workflows/runs                the last runs (?workflow_id=)
The runner is recruitment_agent/workflows.py.
"""
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from recruitment_agent import sharing, workflows
from recruitment_agent.models import RecruitmentWorkflow, RecruitmentWorkflowRun

ADMINS_ONLY = ("Only the company's owner or an admin can set up Recruitment workflows, because they email candidates "
               "and alert colleagues by themselves. Ask one of them.")


def _may_edit(company_user):
    return company_user.role in ('owner', 'admin')


def _payload(wf):
    return {'id': wf.id, 'name': wf.name, 'description': wf.description, 'trigger_event': wf.trigger_event,
            'trigger_label': wf.get_trigger_event_display(), 'job_id': wf.job_id,
            'job_title': wf.job.title if wf.job_id else '', 'conditions': wf.conditions, 'steps': wf.steps,
            'is_active': wf.is_active, 'updated_at': wf.updated_at.isoformat() if wf.updated_at else None,
            'runs': wf.runs.count()}


def _read(company_user, data, wf=None):
    """Fields from the request, checked; returns (fields, error message)."""
    fields = {}
    if wf is None or 'name' in data:
        fields['name'] = (data.get('name') or '').strip()[:200]
        if not fields['name']:
            return None, 'Give the workflow a name.'
    if wf is None or 'trigger_event' in data:
        if data.get('trigger_event') not in workflows.EVENTS:
            return None, 'Choose when it runs: ' + ', '.join(workflows.EVENTS) + '.'
        fields['trigger_event'] = data['trigger_event']
    if wf is None or 'steps' in data:
        problems = workflows.validate(data.get('steps'))
        if problems:
            return None, ' '.join(problems)
        fields['steps'] = data['steps']
    if 'job_id' in data:
        job = sharing.jobs(company_user).filter(pk=data.get('job_id')).first() if data.get('job_id') else None
        if data.get('job_id') and job is None:
            return None, 'That job is not one of the company\'s.'
        fields['job'] = job
    for key in ('description', 'conditions', 'is_active'):
        if key in data:
            fields[key] = data[key] if key != 'description' else (data[key] or '')
    return fields, None


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def workflow_list(request):
    company_user = request.user
    if request.method == 'GET':
        items = list(RecruitmentWorkflow.objects.filter(company=company_user.company).select_related('job'))
        # A template already added shows as in use: pressing Use again made a duplicate that ran twice.
        names = {wf.name for wf in items}
        return Response({'status': 'success', 'data': {
            'workflows': [_payload(wf) for wf in items], 'can_edit': _may_edit(company_user),
            'events': [{'key': k, 'label': v} for k, v in RecruitmentWorkflow.EVENT_CHOICES],
            'step_types': list(workflows.STEP_TYPES), 'placeholders': list(workflows.PLACEHOLDERS),
            'templates': [{'key': k, 'name': t['name'], 'description': t['description'],
                           'trigger_event': t['trigger_event'], 'in_use': t['name'] in names}
                          for k, t in workflows.TEMPLATES.items()],
        }})
    if not _may_edit(company_user):
        return Response({'status': 'error', 'code': 'admins_only', 'message': ADMINS_ONLY},
                        status=status.HTTP_403_FORBIDDEN)
    fields, error = _read(company_user, request.data or {})
    if error:
        return Response({'status': 'error', 'message': error}, status=status.HTTP_400_BAD_REQUEST)
    wf = RecruitmentWorkflow.objects.create(company=company_user.company, created_by=company_user, **fields)
    return Response({'status': 'success', 'data': _payload(wf)}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def workflow_from_template(request):
    company_user = request.user
    if not _may_edit(company_user):
        return Response({'status': 'error', 'code': 'admins_only', 'message': ADMINS_ONLY},
                        status=status.HTTP_403_FORBIDDEN)
    template = workflows.TEMPLATES.get((request.data or {}).get('template_key'))
    if template is None:
        return Response({'status': 'error', 'message': 'Choose one of the templates.'},
                        status=status.HTTP_400_BAD_REQUEST)
    wf = RecruitmentWorkflow.objects.create(
        company=company_user.company, created_by=company_user, name=(request.data.get('name') or template['name'])[:200],
        description=template['description'], trigger_event=template['trigger_event'], steps=template['steps'])
    return Response({'status': 'success', 'data': _payload(wf)}, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def workflow_detail(request, workflow_id):
    company_user = request.user
    wf = RecruitmentWorkflow.objects.filter(company=company_user.company, pk=workflow_id).first()
    if wf is None:
        return Response({'status': 'error', 'message': 'Workflow not found'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return Response({'status': 'success', 'data': _payload(wf)})
    if not _may_edit(company_user):
        return Response({'status': 'error', 'code': 'admins_only', 'message': ADMINS_ONLY},
                        status=status.HTTP_403_FORBIDDEN)
    if request.method == 'DELETE':
        wf.delete()
        return Response({'status': 'success', 'message': 'Workflow deleted.'})
    fields, error = _read(company_user, request.data or {}, wf)
    if error:
        return Response({'status': 'error', 'message': error}, status=status.HTTP_400_BAD_REQUEST)
    for key, value in fields.items():
        setattr(wf, key, value)
    wf.save()
    return Response({'status': 'success', 'data': _payload(wf)})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def workflow_test(request, workflow_id):
    """A test run on one candidate (the newest by default): what each step would do. Nothing is sent or made."""
    company_user = request.user
    wf = RecruitmentWorkflow.objects.filter(company=company_user.company, pk=workflow_id).first()
    if wf is None:
        return Response({'status': 'error', 'message': 'Workflow not found'}, status=status.HTTP_404_NOT_FOUND)
    cvs = sharing.cvs(company_user)
    cv = (cvs.filter(pk=request.data.get('cv_record_id')).first() if request.data.get('cv_record_id')
          else cvs.order_by('-created_at').first())
    if cv is None:
        return Response({'status': 'error', 'message': 'There is no candidate to test it on yet.'},
                        status=status.HTTP_400_BAD_REQUEST)
    interview = cv.interviews.order_by('-created_at').first() if hasattr(cv, 'interviews') else None
    ctx = workflows.context_for(wf.trigger_event, cv_record=cv, interview=interview)
    record = workflows.run(wf, ctx, simulate=True, cv_record=cv, interview=interview)
    return Response({'status': 'success', 'data': {'candidate': ctx.get('candidate_name'), 'results': record.results,
                                                   'error': record.error_message}})


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def workflow_runs(request):
    runs = RecruitmentWorkflowRun.objects.filter(company=request.user.company)
    if request.query_params.get('workflow_id'):
        runs = runs.filter(workflow_id=request.query_params['workflow_id'])
    return Response({'status': 'success', 'data': [{
        'id': r.id, 'workflow': r.workflow_name, 'event': r.event, 'candidate': r.candidate_name,
        'status': r.status, 'error': r.error_message, 'started_at': r.started_at.isoformat(),
        'steps': [{'type': s.get('type'), 'done': s.get('done'), 'note': s.get('note') or s.get('title') or
                   s.get('subject') or s.get('error') or ''} for s in (r.results or {}).get('results', [])],
    } for r in runs[:50]]})
