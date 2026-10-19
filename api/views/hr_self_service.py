"""HR for employees, from their own login (My Space).

Every HR screen and address took dashboard logins only, so an employee could not see
their own leave balance, ask for leave, or ask HR a question; someone with a dashboard
login had to do it for them. My Space's Profile page even linked them to HR
self-service, which sent them back to the company sign-in.

These addresses take the employee from their sign-in and from nothing else: no
employee number is accepted, so nobody can read or file anyone else's leave. They use
HR's own rules: the same working-day count and approver as HR's screen
(`make_leave_request`), and the same confidentiality ladder for questions (an
employee is answered from documents every employee may read, and from their own
record).
"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.authentication import EmployeeTokenAuthentication
from core.api_key_service import KeyServiceError
from hr_agent.models import Employee, LeaveBalance, LeaveRequest
from hr_agent.throttling import HRCRUDThrottle, HRLLMThrottle

logger = logging.getLogger(__name__)

NO_HR = {'status': 'success', 'data': {'available': False,
                                       'message': 'Your company does not use the HR agent.'}}
NO_RECORD = {'status': 'success', 'data': {'available': False,
                                           'message': 'HR has no record for you yet. Ask HR to add you.'}}


def _me(request):
    """(company, employee) for the signed-in employee; either may be None."""
    from core.models import CompanyModulePurchase
    from core.tenancy import company_of_user
    company = company_of_user(request.user)
    if company is None:
        return None, None
    purchase = CompanyModulePurchase.objects.filter(company=company, module_name='hr_agent').first()
    if not (purchase and purchase.is_active()):
        return None, None
    return company, Employee.objects.filter(company=company, user=request.user).select_related(
        'manager', 'department_obj').first()


def _leave(lr):
    return {
        'id': lr.id,
        'leave_type': lr.leave_type,
        'leave_type_label': lr.get_leave_type_display(),
        'start_date': lr.start_date.isoformat(),
        'end_date': lr.end_date.isoformat(),
        'days_requested': float(lr.days_requested or 0),
        'partial_day_period': lr.partial_day_period,
        'reason': lr.reason or '',
        'status': lr.status,
        'status_label': lr.get_status_display(),
        'approver_name': lr.approver.full_name if lr.approver_id else None,
        'approval_note': lr.approval_note or '',
        'decided_at': lr.decided_at.isoformat() if lr.decided_at else None,
        'created_at': lr.created_at.isoformat() if lr.created_at else None,
    }


def _balances(emp):
    """This leave year's balance for each kind of leave: the newest row of each."""
    newest = {}
    for row in emp.leave_balances.order_by('leave_type', '-period_start'):
        newest.setdefault(row.leave_type, row)
    labels = dict(LeaveBalance.LEAVE_TYPE_CHOICES)
    return [{
        'leave_type': row.leave_type,
        'label': labels.get(row.leave_type, row.leave_type),
        'accrued_days': float(row.accrued_days or 0),
        'carried_over_days': float(row.carried_over_days or 0),
        'used_days': float(row.used_days or 0),
        'remaining': row.remaining,
        'period_end': row.period_end.isoformat() if row.period_end else None,
    } for row in newest.values()]


@api_view(['GET'])
@authentication_classes([EmployeeTokenAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([HRCRUDThrottle])
def my_hr(request):
    """The employee's HR record, leave balances and own leave requests."""
    company, emp = _me(request)
    if company is None:
        return Response(NO_HR)
    if emp is None:
        return Response(NO_RECORD)
    requests = emp.leave_requests.select_related('approver').order_by('-start_date', '-id')[:50]
    return Response({'status': 'success', 'data': {
        'available': True,
        'employee': {
            'full_name': emp.full_name,
            'job_title': emp.job_title,
            'department': emp.department_obj.name if emp.department_obj_id else emp.department,
            'manager': emp.manager.full_name if emp.manager_id else None,
            'start_date': emp.start_date.isoformat() if emp.start_date else None,
            'employment_type': emp.get_employment_type_display(),
            'work_email': emp.work_email,
        },
        'balances': _balances(emp),
        'leave_requests': [_leave(lr) for lr in requests],
        'leave_types': [{'value': v, 'label': label} for v, label in LeaveBalance.LEAVE_TYPE_CHOICES],
    }})


@api_view(['POST'])
@authentication_classes([EmployeeTokenAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([HRCRUDThrottle])
def my_hr_request_leave(request):
    """Ask for leave for oneself. HR (or the manager) is told, as for any request."""
    from api.views.hr_agent import make_leave_request
    company, emp = _me(request)
    if company is None or emp is None:
        # Not 403: My Space treats a 403 as a lapsed sign-in and signs the person out.
        return Response({'status': 'error', 'message': 'You cannot ask for leave here yet.'},
                        status=status.HTTP_400_BAD_REQUEST)
    data = {k: request.data.get(k) for k in ('leave_type', 'start_date', 'end_date', 'partial_day_period',
                                             'partial_hours', 'reason')}
    lr, refused = make_leave_request(emp, company, data)
    if refused is not None:
        return refused
    return Response({'status': 'success', 'data': _leave(lr)}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@authentication_classes([EmployeeTokenAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([HRCRUDThrottle])
def my_hr_cancel_leave(request, request_id):
    """Cancel one's own request while it is still waiting for a decision."""
    from django.utils import timezone
    company, emp = _me(request)
    lr = LeaveRequest.objects.filter(pk=request_id, employee=emp).first() if emp is not None else None
    if lr is None:
        return Response({'status': 'error', 'message': 'Leave request not found.'}, status=status.HTTP_404_NOT_FOUND)
    if lr.status != 'pending':
        return Response({'status': 'error', 'message': f'This request is already {lr.get_status_display().lower()}.'},
                        status=status.HTTP_400_BAD_REQUEST)
    lr.status = 'cancelled'
    lr.decided_at = timezone.now()
    lr.save(update_fields=['status', 'decided_at', 'updated_at'])
    return Response({'status': 'success', 'data': _leave(lr)})


@api_view(['POST'])
@authentication_classes([EmployeeTokenAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([HRLLMThrottle])
def my_hr_ask(request):
    """Ask HR a question: answered from documents every employee may read, and from the
    asker's own record (their balance, their manager). Nothing about anyone else."""
    from core.HR_agent.hr_agent import HRAgent
    from hr_agent.models import HRDocument, HRDocumentAccessLog
    company, emp = _me(request)
    if company is None or emp is None:
        return Response({'status': 'error', 'message': 'You cannot ask HR here yet.'},
                        status=status.HTTP_400_BAD_REQUEST)
    question = (request.data.get('question') or '').strip()
    if not question:
        return Response({'status': 'error', 'message': 'Please type a question.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(question) > 2000:
        return Response({'status': 'error', 'message': 'Please keep the question under 2,000 characters.'},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        result = HRAgent(company_id=company.id).answer_question(question, asker_role='employee',
                                                                 asker_employee=emp)
    except KeyServiceError:
        # The company's AI allowance or key is between us and the company; an employee is
        # not shown billing messages, and a 402/403 would sign them out of My Space.
        logger.warning('my_hr_ask: HR AI unavailable for company %s', company.id)
        return Response({'status': 'error', 'message': "HR's assistant is not available just now. "
                                                       'Please ask HR directly.'},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception:
        logger.exception('my_hr_ask failed')
        return Response({'status': 'error', 'message': 'HR could not answer just now. Please try again.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    citations = [c for c in (result or {}).get('citations') or [] if isinstance(c, dict)]
    # A document quoted in an answer has been read; HR keeps a record of who read what.
    try:
        ids = {int(c['document_id']) for c in citations if str(c.get('document_id', '')).isdigit()}
        if ids:
            HRDocumentAccessLog.objects.bulk_create([
                HRDocumentAccessLog(company=company, actor=None, document=d, action='read',
                                    user_agent=f'My Space: {request.user.get_username()}'[:400])
                for d in HRDocument.objects.filter(company=company, pk__in=ids)])
    except Exception:
        logger.exception('my_hr_ask: could not log document reads')
    return Response({'status': 'success', 'data': {
        'answer': result.get('answer') or '',
        'has_verified_info': bool(result.get('has_verified_info')),
        'sources': [{'title': t} for t in dict.fromkeys(c.get('title') or 'HR document' for c in citations)],
    }})
