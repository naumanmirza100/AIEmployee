"""Checks of a company's live AI SDR, run from AI SDR → Tests by its owner or admin.

The automated tests (admin_checks.py) prove the code is right, on a throwaway database. These look at the real
thing, for the company that asks:

  Health checks   read-only: is the AI key accepted, are leads being scored, has the scheduler run, do the
                  campaigns' mailboxes log in, are emails going out, does the CRM answer.
  Live tests      do the work for real, with the company's own AI key, mailbox and CRM: score a lead, write an
                  email, send one, open the inbox, read the website, look a contact up in the CRM.

No live test saves a lead: a saved lead goes to the company's CRM at once (crm_sync_agent.signals), and no CRM
connector can delete a contact again. The test lead is a plain dict and nothing is written but the AI usage. The
only email sent goes to the address the person types, and the do-not-email list still applies to it.

Each check returns {status, summary, details}; status is passed, warning, failed or skipped.
"""
import imaplib
import logging
import time
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

from ai_sdr_agent.models import (
    SDRAgentSettings, SDRCampaign, SDRIcpProfile, SDRJobLock, SDRLead, SDROutreachLog,
)

logger = logging.getLogger(__name__)

PASSED, WARNING, FAILED, SKIPPED = 'passed', 'warning', 'failed', 'skipped'
MAILBOX_LIMIT = 10  # campaigns whose mailbox one health check logs in to


class CheckProblem(Exception):
    """A check cannot go on; the message is for the person who pressed Run."""


def _result(status, summary, details=None):
    return {'status': status, 'summary': summary, 'details': [d for d in (details or []) if d]}


def _ago(when):
    if not when:
        return 'never'
    minutes = int((timezone.now() - when).total_seconds() // 60)
    if minutes < 1:
        return 'just now'
    if minutes < 120:
        return f'{minutes} min ago'
    hours = minutes // 60
    return f'{hours} h ago' if hours < 48 else f'{hours // 24} days ago'


def _leads(company):
    return SDRLead.objects.filter(company_user__company=company)


def _campaigns(company):
    return SDRCampaign.objects.filter(company_user__company=company)


def _mailbox_campaigns(company):
    return _campaigns(company).exclude(smtp_host='').exclude(smtp_username='').order_by('-updated_at')


def _campaign(company, campaign_id):
    try:
        return _mailbox_campaigns(company).get(pk=int(campaign_id))
    except (TypeError, ValueError, SDRCampaign.DoesNotExist):
        raise CheckProblem('Choose one of your campaigns that has a mailbox set up.')


def _ai_client(company):
    """The company's AI client, as the AI SDR gets it. Problems with the key come back as CheckProblem."""
    from ai_sdr_agent.agents.sdr_key_resolver import resolve_sdr_groq_client
    from core.api_key_service import KeyServiceError
    try:
        client, _ctx = resolve_sdr_groq_client(company)
    except KeyServiceError as exc:
        raise CheckProblem(f'No AI key can be used: {exc}')
    if client is None:
        raise CheckProblem('The AI client could not be started on the server.')
    return client


def _ai_problem(exc):
    """What went wrong with an AI call, in words."""
    from core.api_key_service import KeyServiceError
    code = getattr(exc, 'status_code', None)
    if code in (401, 403) or type(exc).__name__ == 'BadAPIKey':
        return 'The AI key was rejected by the provider.'
    if code == 429:
        return 'The AI provider says the key is over its rate or usage limit.'
    if isinstance(exc, KeyServiceError):
        return f'No AI key can be used: {exc}'
    return f'The AI call failed: {exc}'


# --- Health checks: read-only -----------------------------------------------------------------------------------

def check_ai_key(company_user, params):
    client = _ai_client(company_user.company)
    try:
        models = client.models.list()  # costs nothing; a wrong key is refused here
    except Exception as exc:  # noqa: BLE001 — every failure is reported, none is fatal
        return _result(FAILED, _ai_problem(exc))
    count = len(getattr(models, 'data', []) or [])
    return _result(PASSED, 'The AI key is accepted.', [f'{count} models available to it.' if count else None])


def check_qualification_queue(company_user, params):
    company, now = company_user.company, timezone.now()
    leads = _leads(company)
    waiting = leads.filter(qualification_status='pending')
    oldest = waiting.order_by('qualification_queued_at').values_list('qualification_queued_at', flat=True).first()
    stuck = leads.filter(qualification_status='processing', updated_at__lt=now - timedelta(minutes=15)).count()
    gave_up = leads.filter(qualification_status='failed', qualification_attempts__gte=3)
    recent_failures = gave_up.filter(updated_at__gte=now - timedelta(days=1)).count()
    last_error = gave_up.exclude(qualification_error='').order_by('-updated_at') \
        .values_list('qualification_error', flat=True).first()
    last_scored = leads.filter(qualification_status='done').order_by('-qualified_at') \
        .values_list('qualified_at', flat=True).first()
    has_icp = SDRIcpProfile.objects.filter(company_user__company=company, is_active=True).exists()

    details = [
        f'{waiting.count()} lead(s) waiting to be scored' + (f', the oldest since {_ago(oldest)}.' if oldest else '.'),
        f'Last lead scored: {_ago(last_scored)}.',
        f'{stuck} lead(s) stuck while being scored.' if stuck else None,
        f'{gave_up.count()} lead(s) could not be scored after 3 tries ({recent_failures} in the last day).'
        if gave_up.exists() else None,
        f'Latest reason: {last_error}' if last_error else None,
        None if has_icp else 'No active ICP: leads cannot be scored until one is set up in Settings.',
    ]
    if not has_icp and waiting.exists():
        return _result(FAILED, 'Leads are waiting, but there is no active ICP to score them against.', details)
    if recent_failures:
        return _result(FAILED, f'{recent_failures} lead(s) failed to be scored in the last day.', details)
    if stuck or (oldest and now - oldest > timedelta(hours=1)):
        return _result(WARNING, 'Some leads have been waiting more than an hour to be scored.', details)
    return _result(PASSED, 'Leads are being scored.', details)


# The scheduler's jobs that matter to a company, with how often each should run (ai_sdr_agent/scheduler.py).
SCHEDULER_JOBS = [
    ('send_due_steps', 'Sending due emails', 300),
    ('qualify_queue', 'Scoring leads', 120),
    ('check_inbox', 'Reading replies', 300),
    ('enrich_queue', 'Enriching leads', 180),
]


def check_scheduler(company_user, params):
    now = timezone.now()
    last = dict(SDRJobLock.objects.filter(name__in=[j[0] for j in SCHEDULER_JOBS]).values_list('name', 'last_run_at'))
    late, details = [], []
    for name, label, every in SCHEDULER_JOBS:
        ran = last.get(name)
        if not ran or now - ran > timedelta(seconds=max(every * 3, 900)):
            late.append(label)
        details.append(f'{label}: last ran {_ago(ran)} (runs every {every // 60} min).')
    if late:
        return _result(FAILED, f"The scheduler hasn't run lately: {', '.join(late)}.", details)
    return _result(PASSED, 'The scheduler is running.', details)


def check_mailboxes(company_user, params):
    from ai_sdr_agent.agents.outreach_agent import imap_credentials, try_mailbox_logins
    campaigns = list(_mailbox_campaigns(company_user.company).filter(status__in=('active', 'scheduled', 'paused'))
                     [:MAILBOX_LIMIT])
    if not campaigns:
        return _result(SKIPPED, 'No running, scheduled or paused campaign has a mailbox set up.')
    details, bad = [], 0
    for campaign in campaigns:
        imap_host, imap_port, _user, _password = imap_credentials(campaign)
        problem = try_mailbox_logins(campaign.smtp_host, campaign.smtp_port, campaign.smtp_use_tls,
                                     campaign.smtp_username, campaign.smtp_password, imap_host, imap_port)
        if problem:
            bad += 1
            details.append(f'✗ {campaign.name} ({campaign.smtp_username}): {problem}')
        else:
            details.append(f'✓ {campaign.name} ({campaign.smtp_username}): sending and inbox logins work.')
        if campaign.inbox_error:
            details.append(f'  Last reply check on {campaign.name} failed {_ago(campaign.inbox_error_at)}: '
                           f'{campaign.inbox_error}')
    if bad:
        return _result(FAILED, f'{bad} of {len(campaigns)} mailbox(es) cannot log in.', details)
    return _result(PASSED, f'All {len(campaigns)} mailbox(es) log in.', details)


def check_sending(company_user, params):
    since = timezone.now() - timedelta(days=1)
    logs = SDROutreachLog.objects.filter(enrollment__campaign__company_user__company=company_user.company,
                                         action_type='email', created_at__gte=since)
    sent, failed = logs.filter(status='sent').count(), logs.filter(status='failed').count()
    last_error = logs.filter(status='failed').exclude(error_message='').order_by('-created_at') \
        .values_list('error_message', flat=True).first()
    details = [f'Last 24 hours: {sent} sent, {failed} failed.', f'Latest failure: {last_error}' if last_error else None]
    if failed and not sent:
        return _result(FAILED, 'Every email in the last 24 hours failed to send.', details)
    if failed:
        return _result(WARNING, f'{failed} email(s) failed to send in the last 24 hours.', details)
    if not sent:
        return _result(PASSED, 'No email failed; none were due in the last 24 hours.', details)
    return _result(PASSED, f'{sent} email(s) sent in the last 24 hours, none failed.', details)


def _crm_connectors(company):
    from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent
    from crm_sync_agent.models import CRMIntegration
    integrations = list(CRMIntegration.objects.filter(company=company, is_active=True))
    if not integrations:
        return []
    agent = CRMSyncAgent(company)
    return [(integration, agent._get_connector(integration)) for integration in integrations]


def check_crm(company_user, params):
    from crm_sync_agent.models import CRMSyncQueue
    company = company_user.company
    connectors = _crm_connectors(company)
    if not connectors:
        return _result(SKIPPED, 'No CRM is connected.')
    details, refused = [], 0
    for integration, connector in connectors:
        reason = connector.check()
        name = integration.get_provider_display()
        refused += bool(reason)
        details.append(f'✗ {name}: {reason}' if reason else f'✓ {name} answers.')
    queue = CRMSyncQueue.objects.filter(company=company)
    gave_up = [q for q in queue.filter(status='failed').only('attempts', 'max_attempts') if q.attempts >= q.max_attempts]
    old_pending = queue.filter(status='pending', created_at__lt=timezone.now() - timedelta(hours=1)).count()
    details += [f'{len(gave_up)} item(s) failed for good in the sync queue.' if gave_up else None,
                f'{old_pending} item(s) waiting over an hour to be sent.' if old_pending else None]
    if refused:
        return _result(FAILED, 'The CRM refused the connection.', details)
    if gave_up or old_pending:
        return _result(WARNING, 'The CRM answers, but the sync queue has problems.', details)
    return _result(PASSED, 'The CRM answers and nothing is stuck.', details)


def check_research_setup(company_user, params):
    from django.conf import settings
    own = SDRAgentSettings.objects.filter(company_user__company=company_user.company) \
        .exclude(apify_api_token='').exists()
    if own or getattr(settings, 'APIFY_API_TOKEN', ''):
        return _result(PASSED, 'Lead search has an Apify key.',
                       ['Your own key, from AI SDR Settings.' if own else "The platform's key."])
    return _result(WARNING, 'Lead search has no Apify key; it falls back to free web search with fewer results.',
                   ['Add an Apify key in AI SDR → Settings.'])


# --- Live tests: do the work for real ---------------------------------------------------------------------------

SAMPLE_LEAD = {
    'full_name': 'Sam Testwell', 'first_name': 'Sam', 'job_title': 'Head of Sales', 'seniority_level': 'director',
    'company_name': 'Example Software Ltd', 'company_industry': 'Software', 'company_size': 120,
    'email': 'sam.testwell@example.com', 'company_website': 'https://example.com', 'location': 'London, UK',
}


def _icp(company_user):
    icp = (SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()
           or SDRIcpProfile.objects.filter(company_user__company=company_user.company, is_active=True).first())
    if icp:
        return icp, f'Scored against your ICP "{getattr(icp, "name", "") or "active ICP"}".'
    return SDRIcpProfile(industries=['Software'], job_titles=['Head of Sales'], company_size_min=50,
                         company_size_max=500, hot_threshold=75, warm_threshold=60), \
        'No active ICP, so a sample one (software companies, sales leaders) was used.'


def live_qualification(company_user, params):
    from ai_sdr_agent.agents.lead_qualification_agent import LeadQualificationAgent
    _ai_client(company_user.company)
    agent = LeadQualificationAgent(company=company_user.company)
    icp, icp_note = _icp(company_user)
    lead = {**SAMPLE_LEAD, 'company_industry': (icp.industries or ['Software'])[0],
            'job_title': (icp.job_titles or ['Head of Sales'])[0]}
    try:
        # The AI step itself: qualify_lead would fall back to rules and hide a broken AI.
        scored = agent._ai_qualify(lead, icp)
    except Exception as exc:  # noqa: BLE001
        return _result(FAILED, _ai_problem(exc), [icp_note])
    score, temperature = scored.get('score'), scored.get('temperature')
    if not isinstance(score, (int, float)) or not 0 <= score <= 100 or temperature not in ('hot', 'warm', 'cold'):
        return _result(FAILED, 'The AI answered, but not with a usable score.', [icp_note, f'Answer: {scored}'])
    return _result(PASSED, f'The AI scored a sample lead {int(score)} ({temperature}).', [
        icp_note, f"Test lead: {lead['full_name']}, {lead['job_title']} at {lead['company_name']} (not saved).",
        f"Reasoning: {scored.get('qualification_reasoning', '')}"[:600],
    ])


def live_email_writing(company_user, params):
    from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
    company = company_user.company
    _ai_client(company)
    offer = _campaigns(company).exclude(description='').order_by('-updated_at') \
        .values_list('description', flat=True).first() or (getattr(company, 'description', '') or '')
    prospect = {'name': SAMPLE_LEAD['full_name'], 'title': SAMPLE_LEAD['job_title'],
                'company': SAMPLE_LEAD['company_name'], 'industry': SAMPLE_LEAD['company_industry']}
    sender = {'name': company_user.full_name or '', 'title': '', 'company': company.name}
    try:
        email = EmailAssistantAgent(company).write_email('first_email', 'professional', prospect, sender, offer)
    except Exception as exc:  # noqa: BLE001
        return _result(FAILED, _ai_problem(exc))
    subject, body = (email.get('subject') or '').strip(), (email.get('body') or '').strip()
    if not subject or not body:
        return _result(FAILED, 'The AI answered without a subject or body.')
    return _result(PASSED, 'The AI wrote a first email to a sample lead (not sent).',
                   [f'Subject: {subject}', body[:1500],
                    None if offer else 'No campaign description was found, so the AI knew nothing about the offer.'])


def _test_address(params):
    email = (params.get('email') or '').strip()
    try:
        validate_email(email)
    except ValidationError:
        raise CheckProblem('Type the email address the test email should go to.')
    return email


def live_send(company_user, params):
    from ai_sdr_agent.agents.outreach_agent import OnDoNotEmailList, OutreachAgent
    to = _test_address(params)
    campaign = _campaign(company_user.company, params.get('campaign_id'))
    stamp = timezone.localtime().strftime('%d %b %Y, %H:%M')
    subject = f'AI SDR test email ({stamp})'
    body = (f'This is a test email from the AI SDR, sent by {company_user.full_name or company_user.email} from '
            f'AI SDR → Tests through the mailbox of the campaign "{campaign.name}".\n\n'
            'If you can read it, the campaign can send email. No reply is needed.')
    try:
        OutreachAgent(company=company_user.company, needs_ai=False).send_email(campaign, to, subject, body)
    except OnDoNotEmailList:
        return _result(FAILED, f'{to} is on your do-not-email list, so nothing was sent.')
    except Exception as exc:  # noqa: BLE001
        return _result(FAILED, f'The mail server did not take the email: {exc}',
                       [f'From {campaign.from_email or campaign.smtp_username} via {campaign.smtp_host}.'])
    return _result(PASSED, f'The mail server accepted a test email to {to}.', [
        f'From {campaign.from_email or campaign.smtp_username} via {campaign.smtp_host}:{campaign.smtp_port}.',
        f'Subject: {subject}', 'Check that it arrived, and not in spam.'])


def live_inbox(company_user, params):
    from ai_sdr_agent.agents.outreach_agent import imap_credentials
    campaign = _campaign(company_user.company, params.get('campaign_id'))
    host, port, username, password = imap_credentials(campaign)
    if not host:
        return _result(FAILED, 'The campaign has no inbox server, so replies cannot be read.')
    try:
        inbox = imaplib.IMAP4_SSL(host, port, timeout=20)
        try:
            inbox.login(username, password)
            status, data = inbox.select('INBOX', readonly=True)  # read-only: nothing is marked as read
            if status != 'OK':
                return _result(FAILED, f'Logged in, but the inbox could not be opened: {data}')
            total = int((data or [b'0'])[0] or 0)
            _ok, unseen = inbox.search(None, 'UNSEEN')
            since = (timezone.now() - timedelta(days=1)).strftime('%d-%b-%Y')
            _ok, recent = inbox.search(None, f'SINCE {since}')
        finally:
            try:
                inbox.logout()
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        return _result(FAILED, f'The inbox could not be read: {exc}', [f'{username} at {host}:{port}.'])
    count = lambda found: len((found or [b''])[0].split())  # noqa: E731
    return _result(PASSED, f'The inbox of "{campaign.name}" was opened and read.', [
        f'{username} at {host}:{port}.', f'{total} message(s) in the inbox, {count(unseen)} unread, '
        f'{count(recent)} since yesterday.', 'Opened read-only: nothing was marked as read.'])


def live_research(company_user, params):
    from ai_sdr_agent.agents.lead_research_tools import WebpageExtractor
    website = (getattr(company_user.company, 'website', '') or '').strip()
    if not website:
        return _result(SKIPPED, "Add your company's website in the company profile to test reading a website.")
    started = time.monotonic()
    found = WebpageExtractor().extract_company_site(website) or []
    pages = [p for p in found if p.get('page_type') != 'unreachable']
    took = f'{time.monotonic() - started:.1f}s'
    if not pages:
        return _result(FAILED, f'No page of {website} could be read.',
                       ['The site may be down or blocking robots, or the address may be wrong.'])
    return _result(PASSED, f'Read {len(pages)} page(s) of {website} in {took}.',
                   [f"{p.get('url', '')} ({p.get('page_type') or 'page'})" for p in pages[:8]])


def live_crm_lookup(company_user, params):
    connectors = _crm_connectors(company_user.company)
    if not connectors:
        return _result(SKIPPED, 'No CRM is connected.')
    email = (params.get('email') or '').strip() or company_user.email
    details, failed = [], 0
    for integration, connector in connectors:
        name = integration.get_provider_display()
        try:
            found = connector.find_contact_by_email(email)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            details.append(f'✗ {name}: {exc}')
            continue
        details.append(f"✓ {name}: {email} {'is' if found else 'is not'} a contact"
                       + (f" (id {found.get('id')})." if found else '.'))
    details.append('Looked up only: nothing was created in the CRM. A test contact could not be deleted again.')
    if failed:
        return _result(FAILED, 'The CRM could not be searched.', details)
    return _result(PASSED, 'The CRM was searched for a contact.', details)


HEALTH = [
    {'key': 'ai_key', 'title': 'AI key', 'fn': check_ai_key,
     'description': 'The AI key the AI SDR uses is accepted by the provider.'},
    {'key': 'qualification', 'title': 'Lead scoring', 'fn': check_qualification_queue,
     'description': 'Leads are being scored, none are stuck, none failed.'},
    {'key': 'scheduler', 'title': 'Scheduler', 'fn': check_scheduler,
     'description': 'The background jobs that send, score and read replies ran recently.'},
    {'key': 'mailboxes', 'title': 'Campaign mailboxes', 'fn': check_mailboxes,
     'description': "Each campaign's mailbox logs in for sending and for reading replies. Nothing is sent."},
    {'key': 'sending', 'title': 'Sending', 'fn': check_sending,
     'description': 'Emails sent and failed in the last 24 hours.'},
    {'key': 'crm', 'title': 'CRM', 'fn': check_crm,
     'description': 'The connected CRM answers and its sync queue is not stuck.'},
    {'key': 'research', 'title': 'Lead search setup', 'fn': check_research_setup,
     'description': 'Lead search has the Apify key it needs.'},
]

LIVE = [
    {'key': 'live_qualification', 'title': 'Score a lead', 'fn': live_qualification, 'needs': [],
     'description': 'The live AI scores a sample lead against your ICP. The lead is not saved.'},
    {'key': 'live_email_writing', 'title': 'Write an email', 'fn': live_email_writing, 'needs': [],
     'description': 'The live AI writes a first email to a sample lead. Nothing is sent.'},
    {'key': 'live_send', 'title': 'Send an email', 'fn': live_send, 'needs': ['email', 'campaign'],
     'description': "Sends one real test email to the address you type, through a campaign's mailbox."},
    {'key': 'live_inbox', 'title': 'Read the inbox', 'fn': live_inbox, 'needs': ['campaign'],
     'description': "Opens a campaign's inbox read-only and counts its messages, as reply checking does."},
    {'key': 'live_research', 'title': 'Read a website', 'fn': live_research, 'needs': [],
     'description': "Reads your company's website the way lead research reads a lead's."},
    {'key': 'live_crm_lookup', 'title': 'Search the CRM', 'fn': live_crm_lookup, 'needs': ['email'],
     'description': 'Looks a contact up in your CRM by email. Nothing is created there.'},
]

CHECKS = {c['key']: c for c in HEALTH + LIVE}


def run(key, company_user, params):
    check = CHECKS[key]
    started = time.monotonic()
    try:
        outcome = check['fn'](company_user, params or {})
    except CheckProblem as problem:
        outcome = _result(FAILED, str(problem))
    except Exception as exc:  # noqa: BLE001 — a broken check is a result, not a 500
        logger.exception('AI SDR live check %s failed', key)
        outcome = _result(FAILED, f'The check itself broke: {type(exc).__name__}: {exc}')
    return {**outcome, 'key': key, 'duration_ms': int((time.monotonic() - started) * 1000),
            'checked_at': timezone.now().isoformat()}
