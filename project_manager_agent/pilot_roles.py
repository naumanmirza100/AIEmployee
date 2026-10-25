"""Work for one kind of person: "only to the developers", "to all team members", "developers ko de do".

Project Pilot was given everyone with their role and left to keep to the role asked for. On the live site
(26 Oct 2026) "assign the tasks to all developers" also gave work to a designer and a team member (a word list
read "all developers" as "everyone"), and "developers only, no designers" gave a task to the project manager.
Now the roles a request names are read here, from the typed words only (a brief that mentions developers is not
an instruction): the AI is offered only those people, and a task it still gives to someone else is moved to one of
them before the review card. Someone named in the request ("Sana and the developers") may have work too.

A role nobody in the team has is said so when the request insists ("only the interns"). Used loosely ("assign
tasks to developer users" where everyone still has the default role, Team Member) it is read as before: everyone.
"""
import re
from collections import Counter

# The roles of core.UserProfile, with the words people use for them.
ROLES = {
    'developer': ('Developer', r'developers?|devs'),
    'designer': ('Designer', r'designers?'),
    'team_member': ('Team Member', r'team[\s-]?members?'),
    'project_manager': ('Project Manager', r'project[\s-]?managers?'),
    'viewer': ('Viewer', r'viewers?'),
    'internee': ('Internee', r'intern(?:ee)?s?'),
}
# "to all the developers", "between our designers", "only the team members", "sirf developers".
_FILLER = r'(?:(?:all|only|just|of|the|our|my|your|a|an|any|one|some)\s+){0,3}'
_KEEP_BEFORE = r'\b(?:to|between|among|amongst|across|only|just|sirf|all)\s+' + _FILLER
_KEEP_AFTER = r'\s+(?:only|ko|hi\s+ko)\b'                      # "developers only", "developers ko de do"
_DROP_BEFORE = r'\b(?:no|not|excluding|without)\s+(?:to\s+|for\s+)?' + _FILLER
_DROP_AFTER = r'\s+(?:ko\s+)?(?:nahi|nahin|mat)\b'             # "designers ko nahi"
# "everyone except the designers" rules them out; "nobody except the developers" keeps the work to them.
_EXCEPT = r'\b(?:except|other\s+than)\s+(?:for\s+)?' + _FILLER
_NOBODY_ELSE = re.compile(r"\b(?:no\s*one|nobody|none|anyone|anybody|not|never|dont)\b|n['’]t\b")
_NEGATED = re.compile(r"\b(?:not|never|dont)\b|n['’]t\b")          # "don't give anything to the designers"
# The request insists: "only the developers", "developers only", "sirf developers".
_INSIST_BEFORE = r'\b(?:only|just|sirf)\s+(?:to\s+)?' + _FILLER
_INSIST_AFTER = r'\s+(?:only|hi)\b'


def _clause(low, at):
    """The words of the request's clause before position `at`."""
    return re.split(r'[.,;!?]|\bbut\b', low[:at])[-1]


def _read(text):
    """(roles kept to, roles kept from, roles insisted on), read from the typed words."""
    low = ' '.join(str(text or '').lower().split())
    keep, drop, insist = set(), set(), set()
    for key, (_label, words) in ROLES.items():
        role = rf'(?:{words})\b'
        if re.search(_DROP_BEFORE + role, low) or re.search(rf'\b{role}{_DROP_AFTER}', low):
            drop.add(key)
            continue
        for match in re.finditer(_EXCEPT + role, low):
            if _NOBODY_ELSE.search(_clause(low, match.start())):
                keep.add(key)
                insist.add(key)
            else:
                drop.add(key)
        for match in (*re.finditer(_KEEP_BEFORE + role, low), *re.finditer(rf'\b{role}{_KEEP_AFTER}', low)):
            (drop if _NEGATED.search(_clause(low, match.start())) else keep).add(key)
        if re.search(_INSIST_BEFORE + role, low) or re.search(rf'\b{role}{_INSIST_AFTER}', low):
            insist.add(key)
    return keep - drop, drop, insist - drop


def asked(text):
    """(roles the work is kept to, roles it is kept from), read from the typed words."""
    keep, drop, _insist = _read(text)
    return keep, drop


def _kept(people, text):
    """The roles the work is kept to and from. A role nobody has, used loosely ("assign tasks to developer users"
    where everyone still has the default role), keeps nothing, as before."""
    keep, drop, insist = _read(text)
    if keep and not any(p.get('role') in keep for p in people) and not (insist & keep):
        keep = set()
    return keep, drop


def _named(people, text):
    """The people the request names: "give the menu task to Sana and the rest to the developers"."""
    words = set(re.findall(r'[a-z]+', str(text or '').lower()))
    return [p for p in people
            if any(w in words for w in str(p.get('name') or '').lower().split() if len(w) >= 3)]


def limit(people, text):
    """The people the work may go to: those with the roles asked for (or without the ones ruled out), and anyone
    the request names. Everyone when the request names no role."""
    keep, drop = _kept(people or [], text)
    if not keep and not drop:
        return list(people or [])
    named = {p.get('id') for p in _named(people or [], text)}
    return [p for p in people or []
            if p.get('id') in named
            or ((not keep or p.get('role') in keep) and p.get('role') not in drop)]


def nobody(people, text):
    """A sentence when the request insists on a role nobody in the team has; None otherwise."""
    keep, _drop = _kept(people or [], text)
    if not keep or any(p.get('role') in keep for p in people or []) or _named(people or [], text):
        return None
    labels = ' or '.join(ROLES[k][0] for k in sorted(keep))
    return (f"Nobody in your team has the role {labels}, so nothing was changed. Set people's roles under Users "
            "(the pencil on their row), or name the people who should do it.")


def _assignee(action):
    if action.get('action') == 'create_task':
        return True, action.get('assignee_id')
    if action.get('action') == 'update_task' and 'assignee_id' in (action.get('updates') or {}):
        return True, action['updates']['assignee_id']
    return False, None


def keep_to(actions, text, people):
    """Every task in the proposal given to someone the request allows (`limit`): one given to anyone else, or to
    nobody, goes to whoever of them has the fewest so far. Unchanged when the request names no role."""
    allowed = limit(people, text)
    if len(allowed) == len(people or []) or not allowed:
        return actions
    ids = [p['id'] for p in allowed]
    allowed_ids = {str(i) for i in ids}
    load = Counter()
    for action in actions:
        gives, who = _assignee(action)
        if gives and who is not None and str(who) in allowed_ids:
            load[str(who)] += 1
    for action in actions:
        gives, who = _assignee(action)
        if not gives or (who is not None and str(who) in allowed_ids):
            continue
        pick = min(ids, key=lambda i: (load[str(i)], ids.index(i)))
        load[str(pick)] += 1
        if action.get('action') == 'create_task':
            action['assignee_id'] = pick
        else:
            action['updates']['assignee_id'] = pick
    return actions
