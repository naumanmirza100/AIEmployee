"""Field parsing and validation for projects and tasks — one rule per field,
used by every PM API family. Each helper raises ServiceError (400) on bad input.

Before, the three families each had their own copy, and they disagreed: an
invalid status was a 400 on create but silently ignored on update; a bad due
date was a 400 in two families and silently dropped in the third; choice
lists were typed out by hand instead of read from the model.
"""
from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .errors import ServiceError

TITLE_MAX_LENGTH = 200                      # Project.name and Task.title
BUDGET_MAX = Decimal('99999999.99')         # DecimalField(max_digits=10, decimal_places=2)
_EMPTY = (None, '', 'none', 'null')


def is_empty(value):
    return value in _EMPTY


def flag(value):
    """True for 1 / true / yes (as JSON boolean or string). `bool('false')` is
    True, which is why this exists."""
    return str(value).strip().lower() in ('1', 'true', 'yes')


def required_text(value, label, max_length=TITLE_MAX_LENGTH):
    text = str(value if value is not None else '').strip()
    if not text:
        raise ServiceError(f'{label} is required')
    if len(text) > max_length:
        raise ServiceError(f'{label} must be at most {max_length} characters.')
    return text


def optional_text(value):
    return str(value if value is not None else '').strip()


def choice(value, choices, field):
    allowed = [c[0] for c in choices]
    if value not in allowed:
        raise ServiceError(f'Invalid {field}. Must be one of: {", ".join(allowed)}')
    return value


def day(value, field):
    """A date from YYYY-MM-DD or an ISO datetime; None when empty."""
    if is_empty(value):
        return None
    text = str(value).strip()
    try:
        parsed = parse_date(text)
        if parsed is None:
            moment_ = parse_datetime(text)
            parsed = moment_.date() if moment_ else None
    except ValueError:  # well-formed but impossible, e.g. 2026-02-30
        parsed = None
    if parsed is None:
        raise ServiceError(f'Invalid {field}. Use YYYY-MM-DD.')
    return parsed


def moment(value, field='due_date'):
    """An aware datetime from an ISO datetime or YYYY-MM-DD (midnight); None when empty."""
    if is_empty(value):
        return None
    text = str(value).strip()
    try:
        parsed = parse_datetime(text)
        if parsed is None:
            d = parse_date(text)
            parsed = datetime.combine(d, time.min) if d else None
    except ValueError:
        parsed = None
    if parsed is None:
        raise ServiceError(f'Invalid {field} format. Use YYYY-MM-DD or ISO format')
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def budget(value, field):
    """Non-negative amount with at most 2 decimals, or None when empty."""
    if is_empty(value):
        return None
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ServiceError(f'{field} must be a number.')
    if not amount.is_finite():
        raise ServiceError(f'{field} must be a number.')
    if amount < 0:
        raise ServiceError(f'{field} must be non-negative.')
    if amount > BUDGET_MAX:
        raise ServiceError(f'{field} is too large (max {BUDGET_MAX}).')
    return amount.quantize(Decimal('0.01'))


def hours(value, field='estimated_hours'):
    if is_empty(value):
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ServiceError(f'{field} must be a non-negative number.')
    if amount != amount or amount < 0 or amount == float('inf'):  # NaN, negative, inf
        raise ServiceError(f'{field} must be a non-negative number.')
    return amount


def id_list(value, field):
    """A list of integer ids, de-duplicated in order."""
    if not isinstance(value, list):
        raise ServiceError(f'{field} must be a list of task IDs.')
    ids, seen = [], set()
    for raw in value:
        try:
            item = int(raw)
        except (TypeError, ValueError):
            raise ServiceError(f'Invalid task id in {field}: {raw!r}')
        if item not in seen:
            seen.add(item)
            ids.append(item)
    return ids
