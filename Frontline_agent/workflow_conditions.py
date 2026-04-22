"""
Condition-DSL evaluator for workflow `branch` steps.

Design: small, deliberately restricted. No `eval()`, no `ast.parse` on
user-provided strings. Conditions are either:

1. A plain string with one comparison: "priority == 'high'", "category in ['billing','account']".
2. A dict form: {"left": "priority", "op": "==", "right": "high"} or
   {"all": [cond, cond, ...]} / {"any": [cond, cond, ...]} / {"not": cond}.

The dict form is preferred for UIs; the string form is convenience.
Lookups resolve `foo.bar.baz` paths against the execution context.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_OPS = {
    '==': lambda a, b: a == b,
    '!=': lambda a, b: a != b,
    '>': lambda a, b: _cmp(a, b) > 0,
    '<': lambda a, b: _cmp(a, b) < 0,
    '>=': lambda a, b: _cmp(a, b) >= 0,
    '<=': lambda a, b: _cmp(a, b) <= 0,
    'in': lambda a, b: a in (b or []),
    'not_in': lambda a, b: a not in (b or []),
    'contains': lambda a, b: b in (a or ''),
    'startswith': lambda a, b: str(a or '').startswith(str(b or '')),
    'endswith': lambda a, b: str(a or '').endswith(str(b or '')),
    'is_empty': lambda a, _b: a in (None, '', [], {}),
    'is_not_empty': lambda a, _b: a not in (None, '', [], {}),
}

_STRING_OP_PATTERN = re.compile(
    r"""^
    \s*(?P<left>[a-zA-Z_][a-zA-Z0-9_\.]*)\s*
    (?P<op>==|!=|>=|<=|>|<|\bin\b|\bnot_in\b|\bcontains\b|\bstartswith\b|\bendswith\b|\bis_empty\b|\bis_not_empty\b)\s*
    (?P<right>.*)$
    """,
    re.VERBOSE,
)


def _cmp(a: Any, b: Any) -> int:
    """Comparator that tolerates numeric-string / numeric mixes without raising."""
    try:
        if isinstance(a, (int, float)) or isinstance(b, (int, float)):
            return (float(a) > float(b)) - (float(a) < float(b))
    except (TypeError, ValueError):
        pass
    sa, sb = str(a or ''), str(b or '')
    return (sa > sb) - (sa < sb)


def _lookup(context: dict, path: str) -> Any:
    """Walk a dotted path ('ticket.priority') through nested dicts. Missing keys → None."""
    cur: Any = context
    for part in (path or '').split('.'):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _parse_literal(raw: str) -> Any:
    """Parse a right-hand-side literal. Supports quoted strings, numbers, bools,
    null, and simple bracketed lists. Anything else is returned as stripped string."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return ''
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        return s[1:-1]
    low = s.lower()
    if low == 'true':
        return True
    if low == 'false':
        return False
    if low in ('null', 'none'):
        return None
    # Number
    try:
        if '.' in s:
            return float(s)
        return int(s)
    except ValueError:
        pass
    # List literal: [a, 'b', 3]
    if s.startswith('[') and s.endswith(']'):
        inner = s[1:-1]
        if not inner.strip():
            return []
        return [_parse_literal(part) for part in _split_list_items(inner)]
    return s


def _split_list_items(s: str):
    """Split list literal contents by commas not inside quotes."""
    out, buf, in_s, quote_ch = [], [], False, ''
    for ch in s:
        if in_s:
            buf.append(ch)
            if ch == quote_ch:
                in_s = False
        elif ch in ("'", '"'):
            in_s = True
            quote_ch = ch
            buf.append(ch)
        elif ch == ',':
            out.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        out.append(''.join(buf).strip())
    return out


def _eval_atom(left_path: str, op: str, right_raw: Any, context: dict) -> bool:
    """Evaluate a single comparison."""
    fn = _OPS.get(op)
    if fn is None:
        logger.warning("Unknown condition op: %r", op)
        return False
    left = _lookup(context, left_path)
    right = _parse_literal(right_raw) if isinstance(right_raw, str) else right_raw
    try:
        return bool(fn(left, right))
    except Exception as exc:
        logger.warning("Condition eval failed (%s %s %r): %s", left_path, op, right, exc)
        return False


def evaluate(condition: Any, context: dict) -> bool:
    """Evaluate a condition against a context dict. Returns False on any parse error."""
    if condition is None:
        return True  # No condition = always true
    if isinstance(condition, bool):
        return condition
    if isinstance(condition, str):
        m = _STRING_OP_PATTERN.match(condition)
        if not m:
            logger.warning("Unparseable condition string: %r", condition)
            return False
        return _eval_atom(m.group('left'), m.group('op'), m.group('right'), context)
    if isinstance(condition, dict):
        if 'all' in condition:
            return all(evaluate(c, context) for c in (condition.get('all') or []))
        if 'any' in condition:
            return any(evaluate(c, context) for c in (condition.get('any') or []))
        if 'not' in condition:
            return not evaluate(condition.get('not'), context)
        if 'left' in condition and 'op' in condition:
            return _eval_atom(condition['left'], condition['op'], condition.get('right'), context)
        logger.warning("Unknown condition dict shape: %r", condition)
        return False
    logger.warning("Unsupported condition type: %r", type(condition))
    return False
