"""What an edit changed, from and to, for the audit entry.

The audit entry for an edit named only the fields ("deadline"), so nothing could later say the deadline moved
from 7 December to 4 November, or who a task was handed to. The project record (Meeting Notes → Project
record) is built from these entries.
"""


def _plain(value):
    if value is None:
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()[:10]
    if hasattr(value, 'get_full_name'):
        return value.get_full_name() or value.username
    return str(value)


def snapshot(obj, fields):
    """The current value of each of `fields`, as text."""
    return {field: _plain(getattr(obj, field, None)) for field in fields}


def moved(before, obj, fields):
    """``{'from': {...}, 'to': {...}}`` for the fields whose value differs from `before`; {} when none do."""
    after = snapshot(obj, fields)
    changed = [f for f in fields if before.get(f) != after.get(f)]
    if not changed:
        return {}
    return {'from': {f: before.get(f) for f in changed}, 'to': {f: after.get(f) for f in changed}}
