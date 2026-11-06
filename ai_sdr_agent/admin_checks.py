"""AI SDR checks run from the dashboard: by a platform admin, or by a company's owner or admin on the AI SDR's
Tests page.

The admin picks a part of the AI SDR (qualification, replies, CRM sync …) and
presses Run; the automated tests for that part run and the page shows which
passed. The tests run in their own process with the test settings
(`project_manager_ai.settings_test`: an in-memory SQLite database, no email,
no scheduler), never inside the web process: Django's test runner swaps the
database connection for a test one, which would take the live site with it.

Each run is one JSON file in SDR_CHECKS_DIR (default logs/sdr_checks), with the
process's output beside it in a .log file. The web process writes the file
when the run is asked for; from then on only the test process writes it.
"""
import json
import os
import re
import secrets
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

TEST_SETTINGS = 'project_manager_ai.settings_test'
KEEP_RUNS = 50
# A run still "running" this long after it was asked for died without saying so.
STALE_AFTER = timedelta(minutes=15)
FINISHED = ('passed', 'failed', 'error')
# The run's count of each outcome, by the outcome a test is given.
OUTCOMES = {'passed': 'passed', 'failed': 'failed', 'errors': 'error', 'skipped': 'skipped'}
RUN_ID = re.compile(r'^\d{8}-\d{6}-[0-9a-f]{6}$')

_T = 'ai_sdr_agent.tests'
_R29 = 'ai_sdr_agent.tests_replies_29_oct'
_FUN = 'ai_sdr_agent.tests_funnel_fixes'
_RES = 'ai_sdr_agent.tests_research'
_LEADS = 'ai_sdr_agent.tests_api_leads'
_CAMP = 'ai_sdr_agent.tests_api_campaigns'
_MEET = 'ai_sdr_agent.tests_api_meetings'
# Sign-in is not part of the AI SDR's code, but it is how a user reaches it.
SIGN_IN = ['api.tests_company_sign_in', 'api.tests_sign_in_gaps', 'api.tests_session_check', 'api.tests_module_access',
           'core.tests_reset_code', 'core.tests_company_logins']

# Labels are test labels as `manage.py test` takes them: a module, a class or one test. A test may sit in more
# than one part (the qualification tests are spread over several files); every test class in ai_sdr_agent is in
# at least one, which tests_admin_checks holds the catalog to.
SUITES = [
    {
        'key': 'research',
        'title': 'Lead research',
        'description': 'Finding leads (Apify, web search, CSV), reading their websites, and refusing made-up or '
                       'unverified people and companies.',
        'labels': [
            _RES,
            f'{_FUN}.ResearchJobSourceTests', f'{_FUN}.ResearchAsyncTests', f'{_FUN}.BadKeyTerminalTests',
            f'{_T}.ApifyApprovalTests', f'{_T}.ApifyErrorItemTests', f'{_T}.NoMadeUpLeadsTests',
            f'{_R29}.ApifyKeyTests', f'{_LEADS}.ResearchOneLeadTests', f'{_LEADS}.ResearchLeadsBatchTests', f'{_LEADS}.ResearchNewLeadsTests', f'{_LEADS}.ResearchJobStatusAndSourcesTests', f'{_LEADS}.FetchApifyLeadsTests',
        ],
    },
    {
        'key': 'qualification',
        'title': 'Lead qualification & scoring',
        'description': 'Scoring leads against the ICP, hot / warm / cold status, the qualification queue and '
                       'its retries.',
        'labels': [
            f'{_FUN}.AutoResearchLeavesQualificationToTheButtonTests', f'{_FUN}.StatusFollowsTheScoreTests',
            f'{_FUN}.ScoreReconcileTests', f'{_R29}.ScoringQueueTests', f'{_RES}.ConfidenceTests',
            f'{_T}.LifecycleTests.test_qualify_queue_retries_stuck_and_keeps_lead_status',
            f'{_T}.LifecycleTests.test_qualify_queue_without_icp_fails_once_with_reason',
            f'{_RES}.LeadResearchTestCase.test_downstream_qualification_compatibility',
            f'{_RES}.ValidatorTests.test_ai_generated_record_cannot_score_well', f'{_LEADS}.IcpProfileTests', f'{_LEADS}.QualifyAllLeadsTests', f'{_LEADS}.QualifyOneLeadTests',
            f'{_LEADS}.SeveralIcpsTests', f'{_LEADS}.IcpOfNewLeadsTests', f'{_LEADS}.ScoredWithItsOwnIcpTests',
        ],
    },
    {
        'key': 'enrichment',
        'title': 'Lead enrichment',
        'description': 'Filling in missing emails and details from providers, fallbacks, conflicts between '
                       'sources, robots.txt and rate limits.',
        'labels': [
            'ai_sdr_agent.tests_enrichment_comprehensive', 'ai_sdr_agent.tests_enrichment_phase1',
            f'{_FUN}.EnrichmentReportsUpdatedFieldsTests', f'{_FUN}.AutoEnrichmentQueueTests',
            f'{_FUN}.EnrichingStatCountTests', f'{_FUN}.ContactVerifierMxTests', f'{_LEADS}.EnrichOneLeadTests', f'{_LEADS}.EnrichLeadsBatchTests',
        ],
    },
    {
        # The key stays 'categories' so runs saved before leads were filed by industry still find their part.
        'key': 'categories',
        'title': 'Leads: list, import, export & industries',
        'description': "Each lead's industry (filtering, setting it in bulk, renaming it), the category-to-industry "
                       'migration, the other list filters and CSV export.',
        'labels': [
            'ai_sdr_agent.tests_lead_industries', f'{_FUN}.LeadsExportAllTests', f'{_LEADS}.CreatingALeadTests',
            f'{_LEADS}.ListingLeadsTests', f'{_LEADS}.LeadDetailTests', f'{_LEADS}.RestoreLeadTests',
            f'{_LEADS}.BulkDeleteLeadsTests', f'{_LEADS}.BulkRestoreLeadsTests', f'{_LEADS}.IndustryEndpointsTests',
            f'{_LEADS}.BulkSetIndustryTests', f'{_LEADS}.ImportCsvTests', f'{_LEADS}.ExportCsvTests',
        ],
    },
    {
        'key': 'outreach',
        'title': 'Campaigns & email sending',
        'description': 'Enrolling leads, the sequence scheduler, send guards, campaign figures and clearing leads.',
        'labels': [
            f'{_T}.OutreachSendTests', f'{_T}.SchedulerTests', f'{_T}.SendGuardTests', f'{_T}.EmailHtmlEscapeTests',
            f'{_T}.JobLockTests', f'{_T}.LifecycleTests', f'{_T}.SchedulerStartTests',
            f'{_R29}.EnrolTests', f'{_R29}.LiveRunTests', f'{_R29}.LiveRunCampaignTests', f'{_R29}.EmailBrandTests',
            f'{_R29}.FiguresAndRegenerateTests', f'{_R29}.FilmFiguresTests', f'{_R29}.ClearingTests', f'{_CAMP}.CampaignCreateTests', f'{_CAMP}.CampaignDetailTests', f'{_CAMP}.StepListTests', f'{_CAMP}.StepDetailTests', f'{_CAMP}.GenerateStepsTests', f'{_CAMP}.EnrolTests', f'{_CAMP}.EnrolmentListTests', f'{_CAMP}.ProcessOutreachTests', f'{_CAMP}.RetryAndClearTests', f'{_CAMP}.DashboardTests', f'{_CAMP}.AnalyticsTests', f'{_CAMP}.DailySummaryTests', f'{_CAMP}.SchedulerStatusTests',
        ],
    },
    {
        'key': 'mailboxes',
        'title': 'Mailbox settings',
        'description': "The campaign's own SMTP / IMAP mailbox: validation, stored passwords, refusals from the "
                       'mail server.',
        'labels': [
            f'{_T}.MailServerValidationTests', f'{_T}.SmtpPasswordEncryptionTests',
            'ai_sdr_agent.tests_mailbox_refused', 'ai_sdr_agent.tests_mailbox_spaces',
            'ai_sdr_agent.tests_reply_mailbox', f'{_R29}.MailboxProblemTests',
        ],
    },
    {
        'key': 'replies',
        'title': 'Reply handling & AI answers',
        'description': "Reading and classifying lead replies, out-of-office, and the AI's answers (held for "
                       'approval, checked before sending).',
        'labels': [
            f'{_T}.ReplyProcessingTests', f'{_T}.ClassificationTests', f'{_T}.FinishedCampaignReplyTests',
            'ai_sdr_agent.tests_reply_answers', 'ai_sdr_agent.tests_answer_check_30_oct',
            f'{_R29}.ReadingTests', f'{_R29}.ReplyRuleTests', f'{_R29}.QuotedThreadTests', f'{_R29}.ReturnDateTests',
            f'{_R29}.EmailAssistantTests', f'{_R29}.PastTalkTests', f'{_CAMP}.MarkRepliedTests', f'{_CAMP}.ResetEnrolmentTests', f'{_CAMP}.CheckRepliesTests', f'{_CAMP}.ReplyDraftTests', f'{_CAMP}.EmailAssistantTests',
        ],
    },
    {
        'key': 'meetings',
        'title': 'Meetings & booking',
        'description': 'Booking links and pages, approving a meeting, meeting emails and prep notes.',
        'labels': [
            f'{_T}.BookingTests', f'{_T}.PublicLinkTests', f'{_FUN}.BookingLinkExpiryTests',
            f'{_FUN}.BookingConfirmSyncsToCrmTests', f'{_R29}.MeetingEmailTests', f'{_R29}.BookedCallTests',
            f'{_R29}.BookingPageTests', f'{_R29}.PrepNotesTests', f'{_R29}.BounceAndPrepTests', f'{_MEET}.MeetingListTests', f'{_MEET}.MeetingDetailTests', f'{_MEET}.ConfirmMeetingTests', f'{_MEET}.MeetingReminderTests', f'{_MEET}.MeetingPrepTests', f'{_MEET}.ResendSchedulingTests', f'{_MEET}.LeadApprovalLinkTests', f'{_MEET}.LeadSuggestLinkTests', f'{_MEET}.BookingEndpointTests', f'{_MEET}.GoogleAuthTests',
        ],
    },
    {
        'key': 'compliance',
        'title': 'Unsubscribe & do-not-email',
        'description': 'Unsubscribe links and replies, bounces and the company-wide do-not-email list.',
        'labels': [
            'ai_sdr_agent.tests_unsubscribe_link', f'{_R29}.UnsubscribeLinkTests', f'{_R29}.BounceAndPrepTests',
            f'{_MEET}.UnsubscribeEndpointTests',
            f'{_T}.PublicLinkTests',
        ],
    },
    {
        'key': 'crm',
        'title': 'CRM sync',
        'description': 'Sending leads, replies and meetings to HubSpot / Salesforce / Pipedrive, the sync queue '
                       'and the CRM connection.',
        'labels': [
            'ai_sdr_agent.tests_crm_sync', 'ai_sdr_agent.tests_crm_connection', 'ai_sdr_agent.tests_crm_gaps_30_oct',
            'ai_sdr_agent.tests_crm_live_run_31_oct',
        ],
    },
    {
        'key': 'access',
        'title': 'Access & security',
        'description': 'Who may see and change what: subscription gating, salespeople, logins that were switched off.',
        'labels': [
            f'{_T}.ApiTests', 'ai_sdr_agent.tests_leavers', f'{_R29}.SalespersonTests',
            f'{_LEADS}.OnlySignedInCompanyUsersGetInTests', f'{_LEADS}.SdrSettingsTests', f'{_CAMP}.SignInTests',
            f'{_MEET}.MeetingAuthTests',
        ],
    },
    {
        'key': 'live_checks',
        'title': 'Health checks & live tests',
        'description': 'The checks of the live AI SDR on this page: what each concludes, and that none saves a lead '
                       'or emails anyone but the address typed.',
        'labels': ['ai_sdr_agent.tests_live_checks'],
    },
    {
        'key': 'sign_in',
        'title': 'Sign-in',
        'description': 'Company login and logout: missing or wrong email and password, switched-off logins, sessions, '
                       'password reset, and that only companies with the AI SDR reach it.',
        'labels': SIGN_IN,
    },
    {
        'key': 'load',
        'title': 'Load',
        'description': 'A hundred requests twenty at a time; screens that ask the database no more for 300 leads '
                       'than for 30; importing, exporting and deleting a thousand leads.',
        'labels': ['ai_sdr_agent.tests_load'],
    },
    {
        'key': 'screens',
        'title': 'Screens (browser)',
        'description': 'A real browser signs in and uses the AI SDR screens: forms, messages, lists. Needs Node and '
                       'Chromium on the server; skipped without them.',
        'labels': ['ai_sdr_agent.tests_browser'],
    },
]

ALL = {'key': 'all', 'title': 'Everything', 'description': 'Every AI SDR test, and sign-in.',
       'labels': ['ai_sdr_agent'] + SIGN_IN}
SUITES_BY_KEY = {s['key']: s for s in SUITES + [ALL]}


def in_label(test_id, label):
    return test_id == label or test_id.startswith(label + '.')


def suites_of(test_id):
    return [s['key'] for s in SUITES if any(in_label(test_id, label) for label in s['labels'])]


def runs_dir():
    path = Path(getattr(settings, 'SDR_CHECKS_DIR', None) or Path(settings.BASE_DIR) / 'logs' / 'sdr_checks')
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_path(run_id):
    if not RUN_ID.match(run_id or ''):
        raise ValueError('not a run id')
    return runs_dir() / f'{run_id}.json'


def save(path, run):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(run), encoding='utf-8')
    os.replace(tmp, path)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _with_staleness(run):
    """A run that never finished is reported as having stopped, with the end of its output."""
    if run.get('status') not in FINISHED:
        asked = datetime.fromisoformat(run['created_at'])
        if timezone.now() - asked > STALE_AFTER:
            run = {**run, 'status': 'error', 'error': run.get('error') or 'The run stopped without finishing.'}
    if run.get('status') == 'error':
        log = Path(run_path(run['id'])).with_suffix('.log')
        if log.exists():
            lines = log.read_text(encoding='utf-8', errors='replace').splitlines()
            run = {**run, 'log_tail': '\n'.join(lines[-40:])}
    return run


def get_run(run_id):
    path = run_path(run_id)
    if not path.exists():
        return None
    return _with_staleness(load(path))


def list_runs(limit=KEEP_RUNS):
    runs = []
    for path in runs_dir().glob('*.json'):
        try:
            runs.append(_with_staleness(load(path)))
        except (ValueError, OSError, KeyError):
            continue
    runs.sort(key=lambda r: (r['created_at'], r['id']), reverse=True)  # newest first
    return runs[:limit]


def summary(run, suite_key=None):
    """The counts of a run, or of the part of it that belongs to one suite."""
    status, error = run['status'], run.get('error')
    if suite_key and run.get('suite') != suite_key:
        tests = [t for t in run.get('tests', []) if suite_key in t.get('suites', [])]
        counts = {k: sum(t['outcome'] == o for t in tests) for k, o in OUTCOMES.items()}
        total = done = len(tests)
        if status in ('passed', 'failed'):
            status = 'failed' if counts['failed'] or counts['errors'] else 'passed'
            if not tests:
                status, error = 'error', 'None of the tests for this part ran.'
    else:
        counts = {k: run.get(k, 0) for k in OUTCOMES}
        total, done = run.get('total', 0), run.get('done', 0)
    return {
        'id': run['id'], 'suite': run['suite'], 'suite_title': run.get('suite_title'), 'status': status,
        'started_by': run.get('started_by'), 'created_at': run['created_at'], 'finished_at': run.get('finished_at'),
        'total': total, 'done': done, **counts, 'error': error,
    }


def current_run(runs=None):
    for run in runs if runs is not None else list_runs():
        if run['status'] not in FINISHED:
            return run
    return None


def latest_by_suite(runs):
    """For each part, its latest finished result: from a run of that part or a run of everything."""
    latest = {}
    for run in runs:  # newest first
        if run['status'] not in FINISHED:
            continue
        for suite in SUITES:
            if suite['key'] in latest or run['suite'] not in (suite['key'], 'all'):
                continue
            latest[suite['key']] = summary(run, suite['key'])
    return latest


class AlreadyRunning(Exception):
    def __init__(self, run):
        super().__init__('A run is in progress')
        self.run = run


_start_lock = threading.Lock()


def start_run(suite_key, started_by, company_id=None):
    """Write the run's file and start the process that runs it. Only one run at a time, across all companies:
    the tests check the platform's code, not a company's data, so a run is the same whoever asks for it."""
    suite = SUITES_BY_KEY[suite_key]
    with _start_lock:
        runs = list_runs()
        running = current_run(runs)
        if running:
            raise AlreadyRunning(running)
        for old in runs[KEEP_RUNS - 1:]:
            for ext in ('.json', '.log'):
                run_path(old['id']).with_suffix(ext).unlink(missing_ok=True)

        now = timezone.now()
        run_id = f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
        path = run_path(run_id)
        run = {
            'id': run_id, 'suite': suite['key'], 'suite_title': suite['title'], 'labels': suite['labels'],
            'started_by': started_by, 'company_id': company_id, 'created_at': now.isoformat(), 'started_at': None, 'finished_at': None,
            'status': 'queued', 'error': None, 'total': 0, 'done': 0, **{k: 0 for k in OUTCOMES}, 'tests': [],
        }
        save(path, run)
        try:
            _spawn(path)
        except OSError as exc:
            run.update(status='error', error=f'Could not start the test process: {exc}',
                       finished_at=timezone.now().isoformat())
            save(path, run)
        return run


def _spawn(path):
    base = Path(settings.BASE_DIR)
    env = {
        **os.environ, 'DJANGO_SETTINGS_MODULE': TEST_SETTINGS,
        # The test process must never send the scheduled emails or start Celery.
        'SDR_SCHEDULER_ENABLED': 'false', 'CELERY_AUTOSTART': 'false', 'PYTHONIOENCODING': 'utf-8',
    }
    python = getattr(settings, 'SDR_CHECKS_PYTHON', None) or sys.executable
    cmd = [python, str(base / 'manage.py'), 'run_sdr_checks', str(path), f'--settings={TEST_SETTINGS}']
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kwargs['start_new_session'] = True
    with open(Path(path).with_suffix('.log'), 'wb') as log:
        proc = subprocess.Popen(cmd, cwd=str(base), env=env, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, **kwargs)
    # Collect the exit status so the finished process does not linger.
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc
