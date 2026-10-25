"""Recognise a project Project Pilot has made before, and number a second copy.

Uploading the same brief twice made two projects (25 Oct 2026): the check only compared the name the AI proposed
with existing names, and the AI words the name differently each time. Now each project Pilot makes keeps a
fingerprint of the document or description it came from (Project.source_fingerprint). When the same one comes
again, or the proposed name matches an existing project's, the review card says the project already exists and
offers it under a numbered name ("Afar Word Game 2"); Confirm makes that copy, Cancel makes nothing. It is never
made without the card, even when the company auto-confirms.
"""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from core.models import Project

NAME_MATCH = 0.85
_NUMBERED = re.compile(r'^(.*\S)\s+\(?#?(\d{1,3})\)?$')   # 'Afar Game 2', 'Afar Game (3)'; not 'Website 2026'


def fingerprint(text):
    """The same document or description gives the same value, whatever its spacing, case or punctuation."""
    words = re.findall(r'[a-z0-9]+', (text or '').lower())
    if len(words) < 8:        # "create a project" says nothing about which project
        return ''
    return hashlib.sha256(' '.join(words).encode('utf-8')).hexdigest()


def base_name(name):
    """'Afar Word Game 2' → 'Afar Word Game'. A name that is only a number stays as it is."""
    name = (name or '').strip()
    match = _NUMBERED.match(name)
    return match.group(1).strip() if match else name


def _same_name(a, b):
    a, b = base_name(a).lower(), base_name(b).lower()
    return bool(a and b) and (a == b or SequenceMatcher(None, a, b).ratio() >= NAME_MATCH)


def numbered_name(base, projects):
    """The next free numbered name: 'Afar Word Game 2', then 3, …"""
    taken = set()
    stem = base.lower()
    for name in projects.values_list('name', flat=True):
        if base_name(name).lower() != stem:
            continue
        match = _NUMBERED.match(name.strip())
        taken.add(int(match.group(2)) if match else 1)
    number = 2
    while number in taken:
        number += 1
    return f'{base} {number}'


def check(actions, projects, source_text):
    """Mark the proposed new project as a copy when it already exists. Changes `actions` in place.

    Every proposed project gets the source's fingerprint, to be kept when it is made. When a project with the
    same fingerprint or name exists, the proposal is renamed to the next numbered name and a description of the
    match is returned for the card; otherwise None. `projects` is the caller's projects (a queryset)."""
    proposal = next((a for a in actions or [] if isinstance(a, dict) and a.get('action') == 'create_project'), None)
    if proposal is None:
        return None
    mark = fingerprint(source_text)
    if mark:
        proposal['source_fingerprint'] = mark
    existing = projects.filter(source_fingerprint=mark).order_by('created_at').first() if mark else None
    reason = 'same_source'
    if existing is None:
        proposed = proposal.get('project_name') or proposal.get('name') or ''
        existing = next((p for p in projects.order_by('created_at').only('id', 'name', 'created_at')
                         if _same_name(p.name, proposed)), None)
        reason = 'same_name'
    if existing is None:
        return None
    base = base_name(existing.name)
    new_name = numbered_name(base, projects)
    proposal['project_name'] = new_name
    proposal.pop('name', None)
    tasks = existing.tasks.count()
    return {
        'existing_id': existing.id,
        'existing_name': existing.name,
        'created_at': existing.created_at.date().isoformat() if existing.created_at else None,
        'tasks': tasks,
        'new_name': new_name,
        'reason': reason,
        'message': (f'This project already exists: “{existing.name}”'
                    + (f' ({tasks} task{"" if tasks == 1 else "s"})' if tasks else '')
                    + ('. It was made from the same document.' if reason == 'same_source' else '.')
                    + f' Confirm to make another one, named “{new_name}”, or Cancel.'),
    }


def keep_fingerprint(project, action):
    """Store the fingerprint the confirmed proposal carried on the project just made from it."""
    mark = str(action.get('source_fingerprint') or '')
    if re.fullmatch(r'[0-9a-f]{64}', mark):
        Project.objects.filter(pk=project.pk).update(source_fingerprint=mark)
