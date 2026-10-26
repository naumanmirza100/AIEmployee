"""Each leave type's days a year, set once for the whole company, and every employee's balance for this year.

A new company's employees had no leave balance at all ("HR has not set up your leave balance yet"): a balance came
only from an accrual policy, which had no screen, or from HR's Adjust button, one person and one leave type at a time.
Asked for on 26 Oct 2026 (HR demo), on the Leave screen: the days a year for each leave type, "Apply to everyone".

- An allowance is an annual `LeaveAccrualPolicy` (0 switches the type off), so the yearly job keeps crediting it.
- Applying sets this year's balance of every current employee to the allowance; days used are kept. The year is
  claimed for the job (`LeaveAccrualRun`), so it is not credited a second time; next year the job credits it.
- Someone who joins later gets this year's balances when their HR record is made (`give_to`).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

CURRENT = ('active', 'probation', 'on_leave')


def current(company):
    """{leave_type: days a year} from the company's active annual policies."""
    from hr_agent.models import LeaveAccrualPolicy
    return {p.leave_type: float(p.days_per_period)
            for p in LeaveAccrualPolicy.objects.filter(company=company, period='annual', is_active=True)
            if p.days_per_period > 0}


def _claim_year(policy, year):
    from hr_agent.models import LeaveAccrualRun
    try:
        with transaction.atomic():
            LeaveAccrualRun.objects.create(policy=policy, period_key=str(year), completed_at=timezone.now())
    except IntegrityError:
        pass                              # the job (or an earlier Apply) already has this year


def apply(company, allowances):
    """Save `allowances` ({leave_type: days a year}) and give everyone this year's balance. Returns how many
    employees now have them."""
    from hr_agent.models import Employee, LeaveAccrualPolicy, LeaveBalance, leave_year_start
    valid = dict(LeaveBalance.LEAVE_TYPE_CHOICES)
    year_start = leave_year_start()
    people = list(Employee.objects.filter(company=company, employment_status__in=CURRENT))
    with transaction.atomic():
        for leave_type, days in allowances.items():
            if leave_type not in valid:
                continue
            days = Decimal(str(max(0, min(366, float(days or 0))))).quantize(Decimal('0.01'))
            policy, _ = LeaveAccrualPolicy.objects.update_or_create(
                company=company, leave_type=leave_type,
                defaults={'period': 'annual', 'days_per_period': days, 'is_active': days > 0})
            if days <= 0:
                continue
            _claim_year(policy, year_start.year)
            for employee in people:
                balance, _ = LeaveBalance.objects.get_or_create(
                    employee=employee, leave_type=leave_type, period_start=year_start)
                if balance.accrued_days != days:
                    balance.accrued_days = days
                    balance.save(update_fields=['accrued_days', 'updated_at'])
    return len(people)


def give_to(employee):
    """This year's balances for someone new, from the company's allowances. Never raises: a new HR record must not
    fail because of its leave."""
    import logging
    from hr_agent.models import LeaveBalance, leave_year_start
    try:
        if employee.employment_status not in CURRENT or not employee.company_id:
            return 0
        year_start = leave_year_start()
        made = 0
        for leave_type, days in current(employee.company).items():
            _, created = LeaveBalance.objects.get_or_create(
                employee=employee, leave_type=leave_type, period_start=year_start,
                defaults={'accrued_days': Decimal(str(days))})
            made += int(created)
        return made
    except Exception:
        logging.getLogger(__name__).exception('Could not give employee %s their leave allowances', employee.pk)
        return 0


def available(employee, leave_type, *, excluding=None):
    """Days of `leave_type` the employee can still ask for this year: the balance, less what is already waiting
    for an answer. None when the company keeps no balance for that type (no allowance set)."""
    from django.db.models import Sum
    from hr_agent.models import LeaveBalance, LeaveRequest, leave_year_start
    year_start = leave_year_start()
    balance = LeaveBalance.objects.filter(employee=employee, leave_type=leave_type, period_start=year_start).first()
    if balance is None or (balance.accrued_days == 0 and balance.carried_over_days == 0):
        return None
    waiting = (LeaveRequest.objects.filter(employee=employee, leave_type=leave_type, status='pending',
                                           start_date__gte=year_start)
               .exclude(pk=getattr(excluding, 'pk', None))
               .aggregate(total=Sum('days_requested'))['total'] or 0)
    return round(balance.remaining - float(waiting), 2)
