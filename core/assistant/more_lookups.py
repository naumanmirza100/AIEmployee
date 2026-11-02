"""The Company Assistant's lookups for the rest of the agents (CO-18, phase 2, 2 Nov 2026).

Recruitment, Executive Meeting, Operations, Marketing, AI SDR, Reply Draft and CRM Sync, the company's documents,
and "what happened this week" across them all. Each lookup shows the asking login what that agent's own screens show
it, by the same rule:

- Recruitment, Operations, Reply Draft, CRM Sync: the whole company (`recruitment_agent.sharing`; the company's one
  Reply Draft mailbox; company-wide lists).
- Executive Meeting: only meetings the login organises or is invited to, and tasks it made or was given.
- Marketing: the login's own campaigns; an owner's or admin's, the whole company's (`company_scope.owner_ids`).
- AI SDR: the login's own leads, calls and AI answers.
- Documents: HR's documents as HR shows them to this login (by role and record), Frontline's company documents and
  the private ones given to it, Operations' by plain keyword search (no AI is used to search).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from core.assistant.lookups import ROWS, Fact, Lookup, Refused, _date, _day, _one, _range, _when

DOCUMENT_MODULES = ('hr_agent', 'frontline_agent', 'operations_agent')


def _aware_range(ctx, args, *, default_days=7, back=False):
    """[start, end) as instants in the company's zone; `back` counts the default days back from today."""
    if back and not args.get('start') and not args.get('end'):
        args = {**args, 'start': (ctx.today - timedelta(days=default_days - 1)).isoformat(),
                'end': ctx.today.isoformat()}
    start, end = _range(ctx, args, default_days=default_days)
    return (start, end, datetime.combine(start, time(0), tzinfo=ctx.zone),
            datetime.combine(end + timedelta(days=1), time(0), tzinfo=ctx.zone))


def _span(start, end):
    return _date(start) + ('' if start == end else f' to {_date(end)}')


def _match(rows, name, attr):
    """Rows whose `attr` matches `name`: exact first, then containing it. Refused when none."""
    query = str(name or '').strip().lower()
    exact = [r for r in rows if (getattr(r, attr) or '').strip().lower() == query]
    found = exact or [r for r in rows if query in (getattr(r, attr) or '').lower()]
    if not found:
        raise Refused(f'Nothing called "{name}" was found.')
    return found


# ---- Recruitment ---------------------------------------------------------------------------------------------------

def _candidate(cv):
    app = cv.job_application
    if app is not None and (app.first_name or app.last_name):
        return f'{app.first_name} {app.last_name}'.strip()
    from api.views.recruitment_agent import _get_parsed_email_and_name
    import json
    try:
        parsed = json.loads(cv.parsed_json or '{}')
    except ValueError:
        parsed = {}
    return _get_parsed_email_and_name(parsed)[1]


def jobs(ctx, args):
    from recruitment_agent import sharing
    rows = list(sharing.jobs(ctx.company_user).order_by('-id')[:60])
    if args.get('job'):
        rows = _match(rows, args['job'], 'title')[:3]
    link = '/recruitment/job-descriptions'
    facts = [Fact(f'{len(rows)} job(s)' + (f' matching "{args["job"]}"' if args.get('job') else '') + '.', 'Recruitment', link)]
    cvs = sharing.cvs(ctx.company_user)
    interviews = sharing.interviews(ctx.company_user)
    for job in rows[:ROWS]:
        mine = cvs.filter(job_description=job)
        decisions = {r['qualification_decision'] or 'not screened': r['n']
                     for r in mine.values('qualification_decision').annotate(n=Count('id'))}
        ivs = interviews.filter(cv_record__job_description=job)
        by_status = {r['status']: r['n'] for r in ivs.values('status').annotate(n=Count('id'))}
        hired = ivs.filter(outcome='HIRED').count()
        state = 'open' if job.is_active else 'closed'
        facts.append(Fact(
            f'Job "{job.title}" ({state}): {mine.count()} candidate(s); screening: '
            + (', '.join(f'{k.lower()} {v}' for k, v in sorted(decisions.items())) or 'none') + '; interviews: '
            + (', '.join(f'{k.lower()} {v}' for k, v in sorted(by_status.items())) or 'none') + f'; hired {hired}.',
            'Recruitment', link))
    return facts


def candidates(ctx, args):
    from recruitment_agent import sharing
    qs = sharing.cvs(ctx.company_user).select_related('job_description', 'job_application')
    link = '/recruitment/candidates'
    if args.get('job'):
        job_ids = [j.pk for j in _match(list(sharing.jobs(ctx.company_user)[:200]), args['job'], 'title')]
        qs = qs.filter(job_description_id__in=job_ids)
    rows = list(qs.order_by('-role_fit_score', '-created_at')[:300])
    if args.get('candidate'):
        query = str(args['candidate']).strip().lower()
        rows = [cv for cv in rows if query in _candidate(cv).lower()]
        if not rows:
            raise Refused(f'No candidate called "{args["candidate"]}" was found.')
    facts = [Fact(f'{len(rows)} candidate(s)' + (f' for "{args["job"]}"' if args.get('job') else '') + ', best score first.',
                  'Recruitment', link)]
    for cv in rows[:ROWS]:
        applied = cv.job_application.applied_at if cv.job_application_id else cv.created_at
        # Their latest interview, so "when was their interview?" needs no second guess at dates.
        iv = cv.interviews.exclude(status='CANCELLED').order_by('-scheduled_datetime').first()
        interview = (f'; interview {_when(ctx, iv.scheduled_datetime)}, {iv.get_status_display()}'
                     + (f', outcome {iv.get_outcome_display()}' if iv.outcome else '')
                     if iv and iv.scheduled_datetime else '; no interview booked')
        facts.append(Fact(f'{_candidate(cv)} — {cv.job_description.title if cv.job_description_id else "no job"}, score '
                          f'{cv.role_fit_score if cv.role_fit_score is not None else "not scored"}, decision '
                          f'{(cv.qualification_decision or "not screened").lower()}, applied {_when(ctx, applied)}'
                          f'{interview}', 'Recruitment', f'/recruitment/candidates/{cv.pk}'))
    return facts


def interviews(ctx, args):
    from recruitment_agent import sharing
    if not args.get('start') and not args.get('end'):     # with no dates: the last and the next 30 days
        args = {**args, 'start': (ctx.today - timedelta(days=30)).isoformat(),
                'end': (ctx.today + timedelta(days=30)).isoformat()}
    start, end, begins, ends = _aware_range(ctx, args)
    qs = (sharing.interviews(ctx.company_user).filter(scheduled_datetime__gte=begins, scheduled_datetime__lt=ends)
          .exclude(status='CANCELLED').select_related('company_user').order_by('scheduled_datetime'))
    if args.get('person'):
        p = _one(ctx, args['person'])
        qs = qs.filter(Q(company_user=p.company_user) if p.company_user else Q(pk__in=[]))
    rows = list(qs[:80])
    link = '/recruitment/interviews'
    facts = [Fact(f'{len(rows)} interview(s) from {_span(start, end)}.', 'Recruitment', link)]
    for iv in rows[:ROWS]:
        runs = iv.company_user.full_name if iv.company_user_id else 'nobody named'
        facts.append(Fact(f'{_when(ctx, iv.scheduled_datetime)}: {iv.candidate_name} for {iv.job_role}, '
                          f'{iv.get_status_display()}, run by {runs}', 'Recruitment', link))
    return facts


# ---- Executive Meeting ---------------------------------------------------------------------------------------------

def exec_meetings(ctx, args):
    from meeting_agent.models import ExecutiveMeeting
    start, end, begins, ends = _aware_range(ctx, args)
    cu = ctx.company_user
    qs = (ExecutiveMeeting.objects.filter(Q(organizer=cu) | Q(participants__company_user=cu))
          .filter(scheduled_at__gte=begins, scheduled_at__lt=ends).exclude(status='cancelled')
          .select_related('organizer').distinct().order_by('scheduled_at'))
    rows = list(qs[:60])
    link = '/exec-meeting/dashboard?tab=meetings'
    facts = [Fact(f'{len(rows)} executive meeting(s) you organise or are invited to, {_span(start, end)}.',
                  'Executive Meeting', link)]
    for m in rows[:ROWS]:
        agenda = [str(a.get('title') if isinstance(a, dict) else a) for a in (m.agenda or [])][:5]
        facts.append(Fact(f'{_when(ctx, m.scheduled_at)}: "{m.title}", organised by {m.organizer.full_name}, '
                          f'{m.get_status_display()}' + (f'; agenda: {"; ".join(agenda)}' if agenda else ''),
                          'Executive Meeting', link))
    return facts


def exec_tasks(ctx, args):
    from meeting_agent.models import ExecutiveTask, MeetingActionItem
    cu = ctx.company_user
    tasks = (ExecutiveTask.objects.filter(Q(company_user=cu) | Q(assignees=cu)).exclude(status='done')
             .distinct().order_by('due_date', 'id'))
    items = (MeetingActionItem.objects.filter(meeting__organizer=cu).exclude(status__in=('done', 'cancelled'))
             .select_related('assignee', 'meeting').order_by('due_date', 'id'))
    link = '/exec-meeting/dashboard?tab=tasks'
    facts = [Fact(f'{tasks.count()} open executive task(s) you made or were given; {items.count()} open action '
                  f'item(s) from meetings you organised.', 'Executive Meeting', link)]
    for t in tasks[:ROWS]:
        late = ' (late)' if t.due_date and t.due_date < ctx.today else ''
        facts.append(Fact(f'Task "{t.title}" — {t.get_status_display()}, {t.get_priority_display()} priority'
                          + (f', due {_date(t.due_date)}{late}' if t.due_date else ''), 'Executive Meeting', link))
    for a in items[:ROWS]:
        who = a.assignee.full_name if a.assignee_id else (a.owner_name or 'nobody')
        facts.append(Fact(f'Action item "{a.title}" from "{a.meeting.title}" — {who}'
                          + (f', due {_date(a.due_date)}' if a.due_date else ''), 'Executive Meeting',
                          '/exec-meeting/dashboard?tab=meetings'))
    return facts


# ---- Operations ----------------------------------------------------------------------------------------------------

def ops_deadlines(ctx, args):
    from operations_agent.models import OperationsDocumentSummary
    from operations_agent.signals import _parse_deadline_date
    start, end = _range(ctx, args, default_days=30)
    found = []
    for s in (OperationsDocumentSummary.objects.filter(company=ctx.company).exclude(deadlines=[])
              .select_related('document').order_by('-id')[:300]):
        for d in s.deadlines or []:
            if not isinstance(d, dict):
                continue
            when = _parse_deadline_date(d.get('date') or d.get('deadline'))
            if when and start <= when <= end:
                what = d.get('description') or d.get('title') or d.get('text') or 'a deadline'
                source = getattr(s.document, 'title', None) or getattr(s, 'title', '') or 'a summary'
                found.append((when, what, source))
    found.sort()
    link = '/operations/analytics'
    facts = [Fact(f'{len(found)} deadline(s) in the company\'s documents from {_span(start, end)}.', 'Operations', link)]
    facts += [Fact(f'{_date(w)}: {what} (from "{src}")', 'Operations', link) for w, what, src in found[:ROWS]]
    return facts


def ops_documents(ctx, args):
    from operations_agent.models import OperationsDocument
    qs = OperationsDocument.objects.filter(company=ctx.company)
    by_status = {r['processing_status']: r['n'] for r in qs.values('processing_status').annotate(n=Count('id'))}
    link = '/operations/documents'
    facts = [Fact(f'{qs.count()} Operations document(s): ' + ', '.join(f'{k} {v}' for k, v in sorted(by_status.items()))
                  + '.', 'Operations', link)]
    for d in qs.order_by('-created_at')[:ROWS]:
        facts.append(Fact(f'"{d.title or d.original_filename}" — {d.get_document_type_display()}, uploaded '
                          f'{_when(ctx, d.created_at)}, {d.processing_status}', 'Operations', f'/operations/documents/{d.pk}'))
    return facts


# ---- Marketing -----------------------------------------------------------------------------------------------------

def _campaigns(ctx):
    from core.logins import user_for
    from marketing_agent.models import Campaign
    from marketing_agent.services.company_scope import owner_ids
    user = user_for(ctx.company_user)
    return Campaign.objects.filter(owner_id__in=owner_ids(ctx.company_user, user))


def campaigns(ctx, args):
    from marketing_agent.services.campaign_numbers import numbers
    rows = list(_campaigns(ctx).order_by('-id')[:60])
    if args.get('campaign'):
        rows = _match(rows, args['campaign'], 'name')[:3]
    facts = [Fact(f'{len(rows)} campaign(s) you can see' + (f' matching "{args["campaign"]}"' if args.get('campaign') else '')
                  + '.', 'Marketing', '/marketing/dashboard?tab=campaigns')]
    for c in rows[:12]:
        n = numbers(c)
        breakdown = n.get('reply_breakdown') or {}
        facts.append(Fact(
            f'Campaign "{c.name}" ({c.get_status_display()}): {n.get("leads", 0)} lead(s), {n.get("sent", 0)} email(s) '
            f'sent, {n.get("opened", 0)} opened, {n.get("clicked", 0)} clicked, {n.get("replied_leads", 0)} people '
            f'replied, {n.get("bounced", 0)} bounced'
            + (f'; replies by kind: ' + ', '.join(f'{k} {v}' for k, v in sorted(breakdown.items()) if v) if breakdown else '')
            + '.', 'Marketing', f'/marketing/dashboard/campaign/{c.pk}'))
    return facts


def campaign_replies(ctx, args):
    from marketing_agent.models import Reply
    start, end, begins, ends = _aware_range(ctx, args, back=True)
    qs = (Reply.objects.filter(campaign__in=_campaigns(ctx), replied_at__gte=begins, replied_at__lt=ends)
          .select_related('lead', 'campaign').order_by('-replied_at'))
    kinds = {r['interest_level']: r['n'] for r in qs.values('interest_level').annotate(n=Count('id'))}
    facts = [Fact(f'{qs.count()} campaign repl(ies) from {_span(start, end)}: '
                  + (', '.join(f'{k} {v}' for k, v in sorted(kinds.items())) or 'none') + '.',
                  'Marketing', '/marketing/dashboard?tab=campaigns')]
    for r in qs.exclude(interest_level='unsubscribe')[:ROWS]:
        who = f'{r.lead.first_name} {r.lead.last_name}'.strip() or r.lead.email if r.lead_id else 'someone'
        facts.append(Fact(f'{_when(ctx, r.replied_at)}: {who} replied to "{r.campaign.name}", read as '
                          f'{r.get_interest_level_display()}', 'Marketing',
                          f'/marketing/dashboard/campaign/{r.campaign_id}/email-status'))
    return facts


# ---- AI SDR --------------------------------------------------------------------------------------------------------

def sdr_leads(ctx, args):
    from ai_sdr_agent.models import SDRLead
    qs = SDRLead.objects.filter(company_user=ctx.company_user)
    by_status = {r['status']: r['n'] for r in qs.values('status').annotate(n=Count('id'))}
    by_temp = {r['temperature'] or 'unscored': r['n'] for r in qs.values('temperature').annotate(n=Count('id'))}
    facts = [Fact(f'{qs.count()} of your AI SDR lead(s); by stage: ' + (', '.join(f'{k} {v}' for k, v in sorted(by_status.items())) or 'none')
                  + '; by temperature: ' + (', '.join(f'{k} {v}' for k, v in sorted(by_temp.items())) or 'none') + '.',
                  'AI SDR', '/ai-sdr/leads')]
    for lead in qs.order_by('-score', '-id')[:ROWS]:
        facts.append(Fact(f'{lead.full_name or lead.email} ({lead.company_name or "no company"}) — {lead.get_status_display()}, '
                          f'score {lead.score if lead.score is not None else "none"}, {lead.temperature or "unscored"}',
                          'AI SDR', '/ai-sdr/leads'))
    return facts


def sdr_calls(ctx, args):
    from ai_sdr_agent.models import SDRMeeting
    start, end, begins, ends = _aware_range(ctx, args, default_days=14)
    qs = (SDRMeeting.objects.filter(company_user=ctx.company_user, scheduled_at__gte=begins, scheduled_at__lt=ends)
          .exclude(status='cancelled').select_related('lead').order_by('scheduled_at'))
    facts = [Fact(f'{qs.count()} of your sales call(s) from {_span(start, end)}.', 'AI SDR', '/ai-sdr/meetings')]
    for m in qs[:ROWS]:
        facts.append(Fact(f'{_when(ctx, m.scheduled_at)}: {m.lead.full_name or m.lead.email} '
                          f'({m.lead.company_name or "no company"}), {m.get_status_display()}', 'AI SDR', '/ai-sdr/meetings'))
    return facts


def sdr_waiting(ctx, args):
    from ai_sdr_agent.models import SDRReplyDraft
    qs = (SDRReplyDraft.objects.filter(enrollment__campaign__company_user=ctx.company_user, status='pending')
          .select_related('enrollment__lead', 'enrollment__campaign').order_by('created_at'))
    facts = [Fact(f'{qs.count()} AI answer(s) to your leads waiting for your review.', 'AI SDR', '/ai-sdr/outreach')]
    for d in qs[:ROWS]:
        lead = d.enrollment.lead
        facts.append(Fact(f'{lead.full_name or lead.email} in "{d.enrollment.campaign.name}", since '
                          f'{_when(ctx, d.created_at)}', 'AI SDR', '/ai-sdr/outreach'))
    return facts


# ---- Reply Draft ---------------------------------------------------------------------------------------------------

def _mailbox(ctx):
    from api.views.reply_draft_agent import _get_reply_account
    from core.logins import company_user_ids
    return _get_reply_account(company_user_ids(ctx.company))


def inbox(ctx, args):
    from reply_draft_agent.models import InboxEmail, ReplyDraft
    account = _mailbox(ctx)
    if account is None:
        raise Refused('Reply Draft has no mailbox connected yet.')
    start, end, begins, ends = _aware_range(ctx, args, back=True)
    mail = InboxEmail.objects.filter(email_account=account, direction='in', received_at__gte=begins, received_at__lt=ends)
    answered = set(ReplyDraft.objects.filter(inbox_email__in=mail, status='sent').values_list('inbox_email_id', flat=True))
    waiting = [e for e in mail.filter(needs_reply=True).order_by('-received_at')[:200] if e.pk not in answered]
    urgent = [e for e in waiting if e.priority in ('urgent', 'high')]
    kinds = {r['category'] or 'not read yet': r['n'] for r in mail.values('category').annotate(n=Count('id'))}
    link = '/reply-draft/emails'
    facts = [Fact(f'{mail.count()} email(s) in from {_span(start, end)}; by kind: '
                  + (', '.join(f'{k} {v}' for k, v in sorted(kinds.items())) or 'none')
                  + f'; {len(waiting)} still need an answer, {len(urgent)} of them urgent or high priority.',
                  'Reply Draft', link)]
    for e in (urgent + [w for w in waiting if w not in urgent])[:ROWS]:
        facts.append(Fact(f'{_when(ctx, e.received_at)}: from {e.from_name or e.from_email}, "{e.subject}" — '
                          f'{e.priority or "no"} priority, {e.category or "not read yet"}'
                          + (f'; the AI read it as: {e.ai_summary}' if e.ai_summary else ''), 'Reply Draft', link))
    return facts


# ---- CRM Sync ------------------------------------------------------------------------------------------------------

def crm_status(ctx, args):
    from crm_sync_agent.models import CRMIntegration, CRMSyncQueue
    from django.db.models import F
    facts = []
    for crm in CRMIntegration.objects.filter(company=ctx.company):
        problems = [p for p in (
            'the key was refused' if crm.key_refused_at else '',
            f'a permission is missing ({crm.missing_permission})' if crm.missing_permission else '',
            'its plan is full' if crm.limit_reached else '',
        ) if p]
        state = 'connected' if crm.last_ping_ok else ('connection failed' if crm.last_ping_at else 'not tested yet')
        facts.append(Fact(f'{crm.get_provider_display()}: {state}' + (f'; {"; ".join(problems)}' if problems else ''),
                          'CRM Sync', '/crm-sync'))
    if not facts:
        return [Fact('No CRM is connected.', 'CRM Sync', '/crm-sync')]
    qs = CRMSyncQueue.objects.filter(company=ctx.company)
    retrying = Q(status='failed', attempts__lt=F('max_attempts'))
    pending = qs.filter(Q(status='pending') | retrying).count()
    failed = qs.filter(status='failed', attempts__gte=F('max_attempts')).count()
    facts.insert(0, Fact(f'Sync queue: {qs.filter(status="done").count()} sent, {pending} waiting, {failed} failed.',
                         'CRM Sync', '/crm-sync'))
    return facts


# ---- Documents -----------------------------------------------------------------------------------------------------

def documents(ctx, args):
    query = str(args.get('query') or '').strip()
    if not query:
        raise Refused('Say what to look for in the documents.')
    facts = []
    if 'hr_agent' in ctx.modules:
        try:
            from api.views.hr_agent import _resolve_asker_role
            from core.HR_agent.services import HRKnowledgeService
            me = ctx.my_employee
            for hit in HRKnowledgeService(ctx.company.pk).search_knowledge(
                    query, asker_role=_resolve_asker_role(ctx.company_user),
                    asker_employee_id=me.pk if me else None, max_results=4):
                facts.append(Fact(f'HR document "{hit.get("title")}": {str(hit.get("content") or "")[:600]}', 'HR documents',
                                  '/hr/dashboard?tab=documents'))
        except Exception:
            facts.append(Fact('HR documents could not be searched just now.', 'Assistant'))
    if 'frontline_agent' in ctx.modules:
        try:
            from core.Frontline_agent.services import KnowledgeService
            out = KnowledgeService(ctx.company.pk).search_knowledge(query, max_results=4, company_id=ctx.company.pk,
                                                                   company_user_id=ctx.company_user.pk)
            for hit in (out or {}).get('results') or []:
                facts.append(Fact(f'Frontline document "{hit.get("title") or hit.get("document_title")}": '
                                  f'{str(hit.get("content") or hit.get("text") or "")[:600]}', 'Frontline documents',
                                  '/frontline/dashboard?tab=knowledge'))
        except Exception:
            facts.append(Fact('Frontline documents could not be searched just now.', 'Assistant'))
    if 'operations_agent' in ctx.modules:
        try:
            from operations_agent.agents.knowledge_qa_agent import OperationsKnowledgeQAAgent
            text, sources, found = OperationsKnowledgeQAAgent()._build_context(query, ctx.company.pk, None)
            if found and text:
                names = ', '.join(str(s.get('title') or s.get('document_title') or '') for s in (sources or [])[:4] if s)
                # Enough of the passages to answer from: cut at 1,500 characters, an agreement's payment terms were
                # past the cut, and the answer filled them in (the number check flagged them).
                facts.append(Fact(f'Operations documents ({names}): {text[:6000]}', 'Operations documents', '/operations/documents'))
        except Exception:
            facts.append(Fact('Operations documents could not be searched just now.', 'Assistant'))
    return facts or [Fact(f'Nothing about "{query}" was found in the documents you can see.', 'Assistant')]


# ---- This week, across the agents ----------------------------------------------------------------------------------

def week(ctx, args):
    """One line per agent for the period (default: the last 7 days), each read under its agent's rule."""
    start, end, begins, ends = _aware_range(ctx, args, back=True)
    m, cu, facts = ctx.modules, ctx.company_user, []

    def line(source, link, build):
        try:
            text = build()
            if text:
                facts.append(Fact(text, source, link))
        except Exception:
            facts.append(Fact(f'{source} could not be read just now.', 'Assistant'))

    if 'project_manager_agent' in m:
        from core.tenancy import tasks_for_company_user
        line('Project Manager', '/project-manager/dashboard?tab=tasks', lambda: (
            f'Project Manager: {tasks_for_company_user(cu).filter(completed_at__gte=begins, completed_at__lt=ends).count()} '
            f'task(s) done, {tasks_for_company_user(cu).filter(created_at__gte=begins, created_at__lt=ends).count()} added.'))
    if 'frontline_agent' in m:
        def frontline():
            from api.views.frontline_agent import _tickets_of
            from django.contrib.auth import get_user_model
            me = get_user_model().objects.filter(pk=cu.login_user_id).first() if cu.login_user_id else None
            if me is None:
                return ''
            qs = _tickets_of(cu, me)
            return (f'Frontline: {qs.filter(created_at__gte=begins, created_at__lt=ends).count()} ticket(s) opened, '
                    f'{qs.filter(resolved_at__gte=begins, resolved_at__lt=ends).count()} resolved (of the tickets you see).')
        line('Frontline', '/frontline/dashboard?tab=tickets', frontline)
    if 'hr_agent' in m:
        def hr():
            from hr_agent.models import LeaveRequest
            away = LeaveRequest.objects.filter(employee__company=ctx.company, status='approved', start_date__lte=end,
                                               end_date__gte=start).values('employee').distinct().count()
            return f'HR: {away} person(s) on approved leave for part of it.'
        line('HR', '/hr/dashboard?tab=leave', hr)
    if 'recruitment_agent' in m:
        def recruitment():
            from recruitment_agent import sharing
            cvs = sharing.cvs(cu).filter(created_at__gte=begins, created_at__lt=ends).count()
            ivs = sharing.interviews(cu).filter(scheduled_datetime__gte=begins, scheduled_datetime__lt=ends)
            return (f'Recruitment: {cvs} new candidate(s), {ivs.exclude(status="CANCELLED").count()} interview(s), '
                    f'{ivs.filter(outcome="HIRED").count()} hired.')
        line('Recruitment', '/recruitment/dashboard', recruitment)
    if 'exec_meeting_agent' in m:
        def executive():
            from meeting_agent.models import ExecutiveMeeting
            held = (ExecutiveMeeting.objects.filter(Q(organizer=cu) | Q(participants__company_user=cu))
                    .filter(scheduled_at__gte=begins, scheduled_at__lt=ends).exclude(status='cancelled').distinct().count())
            return f'Executive Meeting: {held} meeting(s) you organised or were invited to.'
        line('Executive Meeting', '/exec-meeting/dashboard?tab=meetings', executive)
    if 'marketing_agent' in m:
        def marketing():
            from marketing_agent.models import Reply
            replies = Reply.objects.filter(campaign__in=_campaigns(ctx), replied_at__gte=begins, replied_at__lt=ends)
            return (f'Marketing: {replies.count()} campaign repl(ies), {replies.filter(interest_level="positive").count()} '
                    f'interested (campaigns you can see).')
        line('Marketing', '/marketing/dashboard?tab=campaigns', marketing)
    if 'ai_sdr_agent' in m:
        def sdr():
            from ai_sdr_agent.models import SDRMeeting
            booked = SDRMeeting.objects.filter(company_user=cu, created_at__gte=begins, created_at__lt=ends).count()
            return f'AI SDR: {booked} sales call(s) booked with your leads.'
        line('AI SDR', '/ai-sdr/meetings', sdr)
    if 'reply_draft_agent' in m:
        def reply_draft():
            from reply_draft_agent.models import InboxEmail, ReplyDraft
            account = _mailbox(ctx)
            if account is None:
                return ''
            got = InboxEmail.objects.filter(email_account=account, direction='in', received_at__gte=begins,
                                            received_at__lt=ends).count()
            sent = ReplyDraft.objects.filter(inbox_email__email_account=account, status='sent', sent_at__gte=begins,
                                             sent_at__lt=ends).count()
            return f'Reply Draft: {got} email(s) in, {sent} repl(ies) sent.'
        line('Reply Draft', '/reply-draft/emails', reply_draft)
    if 'operations_agent' in m:
        def operations():
            from operations_agent.models import OperationsDocument
            n = OperationsDocument.objects.filter(company=ctx.company, created_at__gte=begins, created_at__lt=ends).count()
            return f'Operations: {n} document(s) uploaded.'
        line('Operations', '/operations/documents', operations)
    if 'crm_sync_agent' in m:
        def crm():
            from crm_sync_agent.models import CRMSyncQueue
            n = CRMSyncQueue.objects.filter(company=ctx.company, status='done', last_attempted_at__gte=begins,
                                            last_attempted_at__lt=ends).count()
            return f'CRM Sync: {n} item(s) sent to the CRM.'
        line('CRM Sync', '/crm-sync', crm)
    return [Fact(f'What happened from {_span(start, end)}, agent by agent:', 'Assistant')] + facts


MORE = (
    Lookup('jobs', 'recruitment_agent', "Jobs and each one's pipeline: candidates, screening decisions, interviews, "
           'hires.', {'job': 'a job title, optional'}, jobs),
    Lookup('candidates', 'recruitment_agent', 'Candidates, best score first: for one job, or one candidate by name.',
           {'job': 'optional', 'candidate': 'a name, optional'}, candidates),
    Lookup('interviews', 'recruitment_agent', 'Recruitment interviews in a date range and who runs them.',
           {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD', 'person': 'the interviewer, optional'}, interviews),
    Lookup('exec_meetings', 'exec_meeting_agent', 'Executive meetings the asker organises or is invited to, with '
           'agendas, in a date range.', {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}, exec_meetings),
    Lookup('exec_tasks', 'exec_meeting_agent', "The asker's open executive tasks, and open action items from meetings "
           'they organised.', {}, exec_tasks),
    Lookup('ops_deadlines', 'operations_agent', "Deadlines found in the company's Operations documents in a date range.",
           {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}, ops_deadlines),
    Lookup('ops_documents', 'operations_agent', 'Operations documents: how many, their state, the latest.', {},
           ops_documents),
    Lookup('campaigns', 'marketing_agent', "Marketing campaigns and their results (sent, opened, replies), or one "
           'campaign.', {'campaign': 'a name, optional'}, campaigns),
    Lookup('campaign_replies', 'marketing_agent', 'Replies to Marketing campaigns in a date range (default the last 7 '
           'days), by how the AI read them.', {'start': 'optional', 'end': 'optional'}, campaign_replies),
    Lookup('sdr_leads', 'ai_sdr_agent', "The asker's AI SDR leads by stage and temperature, best first.", {}, sdr_leads),
    Lookup('sdr_calls', 'ai_sdr_agent', "The asker's booked sales calls in a date range.",
           {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}, sdr_calls),
    Lookup('sdr_waiting', 'ai_sdr_agent', 'AI answers to the asker\'s leads waiting for review.', {}, sdr_waiting),
    Lookup('inbox', 'reply_draft_agent', "The company's Reply Draft inbox in a date range (default the last 7 days): "
           'mail by kind, what still needs an answer, urgent mail.', {'start': 'optional', 'end': 'optional'}, inbox),
    Lookup('crm_status', 'crm_sync_agent', 'Whether the CRMs are connected, their problems, and the sync queue.', {},
           crm_status),
    Lookup('documents', 'documents', "What the company's documents say (HR policies, Frontline articles, Operations "
           'files): the passages that match.', {'query': 'what to look for, in English'}, documents),
    Lookup('week', 'week', 'What happened in a period (default the last 7 days), one line per agent.',
           {'start': 'optional', 'end': 'optional'}, week),
)
