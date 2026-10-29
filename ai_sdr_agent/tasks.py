"""
AI SDR Agent — Background tasks
=================================
Each task is implemented as a plain Python function (_impl) so the embedded
scheduler (threading.Timer, no Celery worker needed) can call it directly.
The Celery shared_tasks simply delegate to those _impl functions.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

SDR_MODULE = 'ai_sdr_agent'


def _send_limits():
    """(per-campaign emails per scheduler cycle, per-campaign emails per day)."""
    from django.conf import settings
    return (
        int(getattr(settings, 'SDR_MAX_EMAILS_PER_CAMPAIGN_PER_CYCLE', 25)),
        int(getattr(settings, 'SDR_MAX_EMAILS_PER_CAMPAIGN_PER_DAY', 300)),
    )


def _has_sdr_access(company, cache: dict) -> bool:
    """True if ``company`` has an active AI SDR subscription.

    The API is gated by ModuleAccessMiddleware, but background jobs never pass
    through it - without this a lapsed company keeps sending mail and spending
    tokens. ``cache`` (one dict per run) avoids re-querying per campaign.
    """
    if company is None:
        return False
    if company.id not in cache:
        from api.middleware.module_access import ModuleAccessMiddleware
        try:
            cache[company.id] = bool(ModuleAccessMiddleware._has_module(company, SDR_MODULE))
        except Exception as exc:
            logger.error("SDR subscription check failed for company=%s: %s", company.id, exc)
            cache[company.id] = False   # fail closed: never send on an unknown state
    return cache[company.id]


# ---------------------------------------------------------------------------
# Core implementations (plain Python — no Celery dependency)
# ---------------------------------------------------------------------------

def send_due_steps_impl():
    """Send the next due step for every active enrollment whose next_action_at has arrived."""
    from ai_sdr_agent.models import SDRCampaign
    from ai_sdr_agent.agents.outreach_agent import OutreachAgent

    from ai_sdr_agent.models import SDRCampaignEnrollment

    now = timezone.now()
    access_cache: dict = {}

    # Resume out-of-office pauses whose return date has arrived. Only OOO pauses
    # are auto-resumed - a manual pause or a send_failed pause stays paused.
    resumed = SDRCampaignEnrollment.objects.filter(
        status='paused', reply_sentiment='out_of_office',
        next_action_at__lte=now, campaign__status='active',
    ).update(status='active', reply_sentiment='')
    if resumed:
        logger.info("SDR [send-due-steps] resumed %d out-of-office enrollments", resumed)

    # Never for a login that has been switched off: its campaigns are paused then
    # (ai_sdr_agent/leavers.py), and this holds for any that were missed.
    active_campaigns = (SDRCampaign.objects.filter(status='active', company_user__is_active=True)
                        .select_related('company_user__company'))
    total_processed = 0
    total_sent = 0
    total_failed = 0

    logger.info(
        "SDR [send-due-steps] START — time=%s active_campaigns=%d",
        now.isoformat(), active_campaigns.count(),
    )

    # One email address must receive at most ONE email per scheduler cycle.
    # This prevents duplicate sends when the same address exists in:
    #   - multiple lead records enrolled in the same campaign
    #   - multiple active campaigns simultaneously
    sent_emails_this_run: set = set()

    for campaign in active_campaigns:
        if not _has_sdr_access(campaign.company_user.company, access_cache):
            logger.warning(
                "SDR [send-due-steps] campaign=%d SKIPPED — no active AI SDR subscription",
                campaign.id,
            )
            continue

        # Resolve key per campaign owner — each campaign belongs to a company_user
        try:
            _company = campaign.company_user.company
            agent = OutreachAgent(company=_company)
        except Exception as _key_exc:
            from core.api_key_service import KeyServiceError
            if isinstance(_key_exc, KeyServiceError):
                logger.warning(
                    "SDR [send-due-steps] campaign=%d SKIPPED — key blocked: %s",
                    campaign.id, _key_exc.reason,
                )
                continue
            logger.error("SDR [send-due-steps] campaign=%d agent init failed: %s", campaign.id, _key_exc)
            continue

        due_qs = campaign.enrollments.filter(
            status='active', lead__is_deleted=False,
        ).filter(
            Q(next_action_at__lte=now) | Q(next_action_at__isnull=True)
        ).select_related('lead')

        # Send throttle: a big campaign must not blast every lead in one burst
        # (each send is an LLM call + an SMTP round trip, and bursts hurt deliverability).
        from ai_sdr_agent.models import SDROutreachLog as _Log
        cycle_cap, daily_cap = _send_limits()
        sent_today = _Log.objects.filter(
            enrollment__campaign=campaign, status='sent', action_type='email',
            sent_at__gte=now.replace(hour=0, minute=0, second=0, microsecond=0),
        ).count()
        campaign_budget = max(0, min(cycle_cap, daily_cap - sent_today))
        campaign_sent = 0
        if campaign_budget == 0:
            logger.info("SDR [send-due-steps] campaign=%d daily send limit reached (%d)", campaign.id, daily_cap)
            continue

        due_count = due_qs.count()
        logger.info(
            "SDR [send-due-steps] campaign=%d (%s) due_enrollments=%d",
            campaign.id, campaign.name, due_count,
        )

        for enrollment in due_qs:
            if campaign_sent >= campaign_budget:
                logger.info(
                    "SDR [send-due-steps] campaign=%d send limit for this cycle reached (%d) - rest next cycle",
                    campaign.id, campaign_budget,
                )
                break
            lead_email = (enrollment.lead.email or '').strip().lower()
            lead_name = enrollment.lead.display_name

            logger.debug(
                "SDR [send-due-steps] considering enrollment=%d lead=%s email=%s "
                "current_step=%d next_action_at=%s",
                enrollment.id, lead_name, lead_email,
                enrollment.current_step, enrollment.next_action_at,
            )

            # Hard dedup: skip this enrollment if we already sent to this address
            if lead_email and lead_email in sent_emails_this_run:
                logger.warning(
                    "SDR [DEDUP-CYCLE] enrollment=%d lead=%s email=%s — "
                    "SKIPPED: already sent to this address in this scheduler cycle",
                    enrollment.id, lead_name, lead_email,
                )
                continue

            # ── Cross-campaign daily guard ───────────────────────────────────
            # A lead enrolled in multiple campaigns must receive at most ONE
            # email per day across ALL campaigns. This prevents a lead in
            # Campaign A and Campaign B from getting 2 emails on Day 1.
            if lead_email:
                from ai_sdr_agent.models import SDROutreachLog
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                already_emailed_today = SDROutreachLog.objects.filter(
                    enrollment__lead__email__iexact=lead_email,
                    status='sent',
                    sent_at__gte=today_start,
                ).exclude(enrollment__campaign=campaign).exists()
                if already_emailed_today:
                    logger.warning(
                        "SDR [CROSS-CAMPAIGN-DAILY] enrollment=%d lead=%s email=%s "
                        "campaign=%d — SKIPPED: already emailed from another campaign today",
                        enrollment.id, lead_name, lead_email, campaign.id,
                    )
                    continue
            # ────────────────────────────────────────────────────────────────

            # Lock this email address NOW — before the call — so that even if
            # process_enrollment throws an exception the address is still blocked
            # for all subsequent enrollments in this same scheduler cycle.
            if lead_email:
                sent_emails_this_run.add(lead_email)

            try:
                result = agent.process_enrollment(enrollment)
                total_processed += 1
                status = result.get('status')
                logger.info(
                    "SDR [send-due-steps] enrollment=%d lead=%s email=%s → status=%s",
                    enrollment.id, lead_name, lead_email, status,
                )
                if status == 'mailbox_refused':
                    # The campaign's own mailbox will not send and has been paused
                    # (OutreachAgent.process_enrollment). The next lead would get
                    # the same answer, so this campaign's run ends here.
                    total_failed += 1
                    break
                if status == 'sent':
                    total_sent += 1
                    campaign_sent += 1
                elif status == 'failed':
                    total_failed += 1
                    logger.error(
                        "SDR [SEND-FAIL] enrollment=%d lead=%s email=%s error=%s",
                        enrollment.id, lead_name, lead_email, result.get('error'),
                    )
            except Exception as exc:
                logger.error(
                    "SDR [SEND-EXCEPTION] enrollment=%d lead=%s email=%s — %s",
                    enrollment.id, lead_name, lead_email, exc, exc_info=True,
                )
                total_failed += 1

    logger.info(
        "SDR [send-due-steps] END — campaigns=%d processed=%d sent=%d failed=%d",
        active_campaigns.count(), total_processed, total_sent, total_failed,
    )
    return {
        'campaigns': active_campaigns.count(),
        'processed': total_processed,
        'sent': total_sent,
        'failed': total_failed,
    }


REPLY_WINDOW_DAYS = 30


def campaigns_to_read_replies(**filters):
    """Campaigns whose inbox is read: active ones, and paused or completed ones that sent an email in the last 30
    days. A reply often comes after the last step, and a finished campaign was not read at all (CO-143)."""
    from django.db.models import Max
    from ai_sdr_agent.models import SDRCampaign
    since = timezone.now() - timedelta(days=REPLY_WINDOW_DAYS)
    return (SDRCampaign.objects.filter(auto_check_replies=True, **filters)
            .annotate(last_sent=Max('enrollments__logs__sent_at'))
            .filter(Q(status='active') | Q(status__in=['paused', 'completed'], last_sent__gte=since)))


def check_inbox_replies_impl():
    """Poll IMAP inbox for replies on every campaign campaigns_to_read_replies() gives."""
    from ai_sdr_agent.agents.outreach_agent import OutreachAgent
    from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
    from ai_sdr_agent.reply_actions import handle_inbox_reply

    campaigns = campaigns_to_read_replies(
        company_user__is_active=True,       # a switched-off login's mailbox is not read, nor its leads answered
    ).select_related('company_user__company')

    total_replies = 0
    total_meetings = 0
    access_cache: dict = {}

    logger.info(
        "SDR [check-inbox] START — checking %d campaigns for replies",
        campaigns.count(),
    )

    for campaign in campaigns:
        if not _has_sdr_access(campaign.company_user.company, access_cache):
            logger.warning(
                "SDR [check-inbox] campaign=%d SKIPPED — no active AI SDR subscription",
                campaign.id,
            )
            continue

        # Resolve keys per campaign owner
        try:
            _company = campaign.company_user.company
            agent = OutreachAgent(company=_company)
            email_agent = EmailAssistantAgent(company=_company)
        except Exception as _key_exc:
            from core.api_key_service import KeyServiceError
            if isinstance(_key_exc, KeyServiceError):
                logger.warning(
                    "SDR [check-inbox] campaign=%d SKIPPED — key blocked: %s",
                    campaign.id, getattr(_key_exc, 'reason', str(_key_exc)),
                )
                continue
            logger.error("SDR [check-inbox] campaign=%d agent init failed: %s", campaign.id, _key_exc)
            continue

        try:
            enrollments = list(
                campaign.enrollments
                .filter(status__in=['active', 'paused', 'completed', 'replied'])
                .exclude(lead__email='')
                .select_related('lead')
                .prefetch_related('logs')
            )
            logger.info(
                "SDR [check-inbox] campaign=%d (%s) checking %d enrollments via IMAP",
                campaign.id, campaign.name, len(enrollments),
            )

            if not enrollments:
                continue

            replies = agent.check_inbox_for_replies(campaign, enrollments)
            logger.info(
                "SDR [check-inbox] campaign=%d IMAP returned %d candidate replies",
                campaign.id, len(replies),
            )

            for r in replies:
                # The shared reply rules (ai_sdr_agent/reply_actions.py), as the Check Replies buttons use.
                result = handle_inbox_reply(campaign, r, email_agent=email_agent, outreach_agent=agent)
                if not result:
                    continue
                logger.info("SDR [check-inbox] enrollment=%d lead=%s → %s (%s)", r['enrollment'].id,
                            r['sender_email'], result['action'], result.get('category'))
                if result['action'] in ('unsubscribed', 'not_interested', 'sent_more_info', 'answer_waiting',
                                        'meeting_created'):
                    total_replies += 1
                if result.get('meeting_created'):
                    total_meetings += 1

            campaign.last_replies_checked_at = timezone.now()
            campaign.save(update_fields=['replies_received', 'meetings_booked', 'last_replies_checked_at'])

        except Exception as exc:
            logger.error(
                "SDR [check-inbox] campaign=%d FAILED: %s", campaign.id, exc, exc_info=True,
            )

    logger.info(
        "SDR [check-inbox] END — campaigns=%d replies=%d meetings=%d",
        campaigns.count(), total_replies, total_meetings,
    )
    return {'campaigns': campaigns.count(), 'replies': total_replies, 'meetings': total_meetings}


def auto_start_campaigns_impl():
    """Activate scheduled campaigns whose start_date has arrived."""
    from ai_sdr_agent.models import SDRCampaign

    today = timezone.now().date()
    qs = SDRCampaign.objects.filter(status='scheduled', start_date__lte=today, company_user__is_active=True)

    started = 0
    skipped_no_steps = 0

    for campaign in qs:
        has_steps = campaign.steps.filter(is_active=True).exists()
        if not has_steps:
            skipped_no_steps += 1
            logger.warning("SDR auto-start: campaign %s skipped — no steps", campaign.id)
            continue
        campaign.status = 'active'
        campaign.activated_at = timezone.now()
        campaign.end_date = campaign.derive_end_date()
        campaign.save(update_fields=['status', 'activated_at', 'end_date'])
        started += 1
        logger.info("SDR auto-start: campaign %s (%s) activated", campaign.id, campaign.name)

    return {'started': started, 'skipped_no_steps': skipped_no_steps}


def auto_pause_expired_campaigns_impl():
    """Mark campaign 'completed' when all enrollments are done OR end_date has passed."""
    from ai_sdr_agent.models import SDRCampaign

    today = timezone.now().date()
    completed = 0

    # end_date is derived from the campaign start, so leads enrolled later must not
    # be cut off by it: expire each enrollment against ITS OWN window
    # (enrolled_at + longest step delay). The campaign completes below once no
    # enrollment is left open.
    from django.db.models import Max
    expired = SDRCampaign.objects.filter(status='active', end_date__lt=today)
    for campaign in expired:
        max_delay = campaign.steps.aggregate(m=Max('delay_days'))['m'] or 10
        cutoff = timezone.now() - timedelta(days=max_delay)
        campaign.enrollments.filter(status='active', enrolled_at__lt=cutoff).update(
            status='completed', completed_at=timezone.now(),
        )

    active = SDRCampaign.objects.filter(status='active')
    for campaign in active:
        open_qs = campaign.enrollments.filter(
            Q(status='active') | Q(status='paused', reply_sentiment='out_of_office')
        )
        if not open_qs.exists() and campaign.enrollments.exists():
            campaign.status = 'completed'
            campaign.save(update_fields=['status'])
            completed += 1
            logger.info("SDR auto-complete: campaign %s — all enrollments done", campaign.id)

    return {'completed': completed}


def send_meeting_reminders_impl():
    """Send 24-hour reminder emails for meetings scheduled within the next 24–26 hours."""
    from ai_sdr_agent.models import SDRMeeting
    from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent

    agent = MeetingSchedulingAgent()
    now = timezone.now()
    access_cache: dict = {}
    window_start = now + timedelta(hours=24)
    window_end = now + timedelta(hours=26)

    due = SDRMeeting.objects.filter(
        status='scheduled',
        scheduled_at__gte=window_start,
        scheduled_at__lte=window_end,
        reminder_sent_at__isnull=True,
        company_user__is_active=True,       # not on behalf of someone whose login is switched off
    ).select_related('lead', 'enrollment__campaign', 'company_user__company')

    sent = failed = 0
    for meeting in due:
        if not meeting.enrollment or not meeting.enrollment.campaign:
            continue
        if not _has_sdr_access(meeting.company_user.company, access_cache):
            continue
        campaign = meeting.enrollment.campaign
        try:
            agent.send_reminder_email(campaign, meeting.lead, meeting)
            meeting.reminder_sent_at = now
            meeting.save(update_fields=['reminder_sent_at'])
            sent += 1
            logger.info("SDR reminder sent for meeting %s (%s)", meeting.id, meeting.lead.email)
        except Exception as exc:
            logger.error("SDR reminder failed for meeting %s: %s", meeting.id, exc)
            failed += 1

    logger.info("SDR meeting-reminders: sent=%d failed=%d", sent, failed)
    return {'sent': sent, 'failed': failed}


# ---------------------------------------------------------------------------
# Analytics — daily summary + low-meetings alert
# ---------------------------------------------------------------------------

def send_daily_analytics_impl():
    """
    Send daily summary email + low-meetings alert to every company user
    who has at least one active SDR campaign.
    Runs once per day via the scheduler.
    """
    from ai_sdr_agent.models import SDRCampaign
    from ai_sdr_agent.agents.analytics_agent import AnalyticsAgent, MEETINGS_ALERT_THRESHOLD

    agent = AnalyticsAgent()
    processed = 0
    alerts_sent = 0
    access_cache: dict = {}

    # Find distinct company users with at least one active campaign
    company_user_ids = (
        SDRCampaign.objects.filter(status='active', company_user__is_active=True)
        .values_list('company_user_id', flat=True)
        .distinct()
    )

    logger.info('SDR [daily-analytics] sending summaries to %d company users', len(company_user_ids))

    for cu_id in company_user_ids:
        try:
            from core.models import CompanyUser
            company_user = CompanyUser.objects.get(pk=cu_id)
        except Exception as exc:
            logger.error('SDR [daily-analytics] cannot load company_user=%d: %s', cu_id, exc)
            continue

        if not _has_sdr_access(company_user.company, access_cache):
            continue

        try:
            sent = agent.send_daily_summary(company_user)
            if sent:
                processed += 1

            # Check low-meetings alert
            metrics = agent.compute_metrics(company_user)
            if metrics['low_meetings_alert']:
                alert_sent = agent.send_low_meetings_alert(company_user, metrics['meetings_week'])
                if alert_sent:
                    alerts_sent += 1
                    logger.warning(
                        'SDR [daily-analytics] LOW-MEETINGS ALERT sent to company_user=%d '
                        '(meetings_week=%d < threshold=%d)',
                        cu_id, metrics['meetings_week'], MEETINGS_ALERT_THRESHOLD,
                    )
        except Exception as exc:
            logger.error('SDR [daily-analytics] failed for company_user=%d: %s', cu_id, exc, exc_info=True)

    logger.info('SDR [daily-analytics] done — summaries=%d alerts=%d', processed, alerts_sent)
    return {'summaries_sent': processed, 'alerts_sent': alerts_sent}


# ---------------------------------------------------------------------------
# Celery tasks (delegate to _impl functions above)
# ---------------------------------------------------------------------------

@shared_task(bind=True, name='ai_sdr_agent.tasks.sdr_send_due_steps_task',
             max_retries=3, default_retry_delay=300)
def sdr_send_due_steps_task(self):
    return send_due_steps_impl()


@shared_task(bind=True, name='ai_sdr_agent.tasks.sdr_check_inbox_replies_task',
             max_retries=2, default_retry_delay=600)
def sdr_check_inbox_replies_task(self):
    return check_inbox_replies_impl()


@shared_task(bind=True, name='ai_sdr_agent.tasks.sdr_auto_start_campaigns_task',
             max_retries=2, default_retry_delay=300)
def sdr_auto_start_campaigns_task(self):
    return auto_start_campaigns_impl()


@shared_task(bind=True, name='ai_sdr_agent.tasks.sdr_auto_complete_campaigns_task',
             max_retries=2, default_retry_delay=600)
def sdr_auto_complete_campaigns_task(self):
    return auto_pause_expired_campaigns_impl()


@shared_task(bind=True, name='ai_sdr_agent.tasks.sdr_send_meeting_reminders_task',
             max_retries=2, default_retry_delay=600)
def sdr_send_meeting_reminders_task(self):
    return send_meeting_reminders_impl()


@shared_task(bind=True, name='ai_sdr_agent.tasks.sdr_daily_analytics_task', max_retries=1)
def sdr_daily_analytics_task(self):
    return send_daily_analytics_impl()


# ---------------------------------------------------------------------------
# Apify Auto Lead Research
# ---------------------------------------------------------------------------

def auto_research_leads_impl(leads_per_run: int = 10):
    """
    Automatically fetch leads from Apify for all company users who have:
    - An active ICP profile
    - Apify token configured in settings
    """
    import os
    from django.conf import settings
    from django.utils import timezone as tz

    apify_token = (
        getattr(settings, 'APIFY_API_TOKEN', None)
        or os.environ.get('APIFY_API_TOKEN', '')
    ).strip()

    if not apify_token:
        logger.info("Apify auto-research skipped: APIFY_API_TOKEN not set")
        return {'skipped': True, 'reason': 'No APIFY_API_TOKEN'}

    from ai_sdr_agent.models import SDRIcpProfile, SDRLead, SDRLeadResearchJob
    from ai_sdr_agent.agents.lead_research_agent import LeadResearchAgent

    researcher = LeadResearchAgent()
    total_created = 0
    errors = 0
    access_cache: dict = {}

    active_icps = SDRIcpProfile.objects.filter(is_active=True).select_related('company_user__company')
    logger.info("Apify auto-research: found %d active ICP profiles", active_icps.count())

    for icp in active_icps:
        company_user = icp.company_user
        if not _has_sdr_access(company_user.company, access_cache):
            continue
        try:
            job = SDRLeadResearchJob.objects.create(
                company_user=company_user,
                icp_profile=icp,
                status='running',
                source='apify',
                search_params={'count': leads_per_run, 'source': 'apify', 'auto': True},
                started_at=tz.now(),
            )

            raw_leads = researcher.search_leads(icp, count=leads_per_run, source='apify')
            created = 0

            for ld in raw_leads:
                email = ld.get('email', '').strip().lower()
                full_name = ld.get('full_name') or f"{ld.get('first_name','')} {ld.get('last_name','')}".strip()
                if email:
                    is_dup = SDRLead.all_objects.filter(company_user=company_user, email=email).exists()
                else:
                    # No email to match on: fall back to LinkedIn URL, then name + company,
                    # so the same person isn't re-inserted on every run.
                    linkedin = (ld.get('linkedin_url') or '').strip()
                    if linkedin:
                        is_dup = SDRLead.all_objects.filter(company_user=company_user, linkedin_url=linkedin).exists()
                    else:
                        is_dup = bool(full_name) and SDRLead.all_objects.filter(
                            company_user=company_user, full_name__iexact=full_name,
                            company_name__iexact=ld.get('company_name', ''),
                        ).exists()
                if is_dup:
                    continue  # skip duplicate

                SDRLead.objects.create(
                    company_user=company_user,
                    icp_profile=icp,
                    first_name=ld.get('first_name', ''),
                    last_name=ld.get('last_name', ''),
                    full_name=full_name,
                    email=email,
                    phone=ld.get('phone', ''),
                    job_title=ld.get('job_title', ''),
                    seniority_level=ld.get('seniority_level', ''),
                    department=ld.get('department', ''),
                    company_name=ld.get('company_name', ''),
                    company_domain=ld.get('company_domain', ''),
                    company_industry=ld.get('company_industry', ''),
                    company_size=ld.get('company_size'),
                    company_location=ld.get('company_location', ''),
                    linkedin_url=ld.get('linkedin_url', ''),
                    company_website=ld.get('company_website', ''),
                    source='apify',
                    temperature='cold',
                    status='new',
                )
                created += 1

            job.status = 'completed'
            job.leads_created = created
            job.completed_at = tz.now()
            job.save(update_fields=['status', 'leads_created', 'completed_at'])

            total_created += created
            logger.info("Apify auto-research: company_user=%d created=%d leads", company_user.pk, created)

        except Exception as exc:
            errors += 1
            logger.error("Apify auto-research failed for company_user=%d: %s", company_user.pk, exc)
            try:
                SDRLeadResearchJob.objects.filter(
                    company_user=company_user, status='running'
                ).update(status='failed', error_message=str(exc))
            except Exception:
                pass

    return {'total_created': total_created, 'errors': errors}


@shared_task(bind=True, name='ai_sdr_agent.tasks.auto_research_leads_task', max_retries=1)
def auto_research_leads_task(self):
    return auto_research_leads_impl()


# ---------------------------------------------------------------------------
# Lead qualification queue — background, batched, self-retrying
# ---------------------------------------------------------------------------
QUALIFY_BATCH_SIZE = 5        # leads scored per scheduler tick
QUALIFY_MAX_ATTEMPTS = 3      # give up after this many failed attempts
QUALIFY_STUCK_MINUTES = 15    # a 'processing' lead older than this is retried


def qualify_queue_impl():
    """Score a small batch of queued leads. Runs every ~2 min via the scheduler.

    - Picks the oldest 'pending' (or retryable 'failed') leads across all
      companies, capped at QUALIFY_BATCH_SIZE, so AI tokens are spent gradually
      instead of all at once.
    - On a key/quota error for a company, that company's leads are left 'pending'
      and retried on the next tick (never burns the whole batch on a dead key).
    - Other errors bump the attempt count; after QUALIFY_MAX_ATTEMPTS the lead is
      marked 'failed' and stops retrying.
    """
    from django.db.models import Q as _Q
    from ai_sdr_agent.models import SDRLead, SDRIcpProfile
    from core.api_key_service import KeyServiceError
    from api.views.ai_sdr_agent import _get_qualification_agent

    now = timezone.now()
    # pending, or failed-but-still-retryable, oldest first.
    # 'processing' rows untouched for a while were abandoned by a crashed run.
    stuck_before = now - timedelta(minutes=QUALIFY_STUCK_MINUTES)
    batch = list(
        SDRLead.objects.filter(
            _Q(qualification_status='pending')
            | _Q(qualification_status='failed', qualification_attempts__lt=QUALIFY_MAX_ATTEMPTS)
            | _Q(qualification_status='processing', updated_at__lt=stuck_before)
        )
        .select_related('company_user__company')
        .order_by('qualification_queued_at', 'created_at')[:QUALIFY_BATCH_SIZE]
    )
    if not batch:
        return {'processed': 0, 'qualified': 0, 'failed': 0, 'pending': 0}

    qualified = 0
    failed = 0
    access_cache: dict = {}
    # Cache one agent + active ICP per company; skip companies whose key is out.
    agents: dict = {}
    icps: dict = {}
    blocked_companies: set = set()

    for lead in batch:
        company = lead.company_user.company
        cu_id = lead.company_user_id
        if cu_id in blocked_companies:
            continue  # key already out for this company this tick
        if not _has_sdr_access(company, access_cache):
            # Lapsed subscription: leave the lead pending, but send it to the back
            # of the queue so it doesn't hog the batch every tick.
            SDRLead.objects.filter(pk=lead.pk).update(qualification_queued_at=now)
            continue

        try:
            if cu_id not in agents:
                agents[cu_id] = _get_qualification_agent(company)
                icps[cu_id] = SDRIcpProfile.objects.filter(
                    company_user=lead.company_user, is_active=True
                ).first()

            if icps[cu_id] is None:
                # Nothing to score against - fail once with a clear reason instead
                # of raising on every tick. "Qualify all" re-queues it after an ICP exists.
                lead.qualification_status = 'failed'
                lead.qualification_attempts = QUALIFY_MAX_ATTEMPTS
                lead.qualification_error = 'No active ICP profile - set one up, then qualify again.'
                lead.save(update_fields=[
                    'qualification_status', 'qualification_attempts', 'qualification_error', 'updated_at',
                ])
                failed += 1
                continue

            lead.qualification_status = 'processing'
            lead.save(update_fields=['qualification_status', 'updated_at'])

            result = agents[cu_id].qualify_lead(lead, icps[cu_id])
            lead.score = result['score']
            lead.temperature = result['temperature']
            lead.score_breakdown = result.get('score_breakdown', {})
            lead.qualification_reasoning = result.get('qualification_reasoning', '')
            lead.key_strengths = result.get('key_strengths', [])
            lead.concerns = result.get('concerns', [])
            lead.outreach_strategy = result.get('outreach_strategy', '')
            lead.qualified_at = now
            if lead.status in ('new', 'qualified'):   # never regress contacted/replied/etc.
                lead.status = 'qualified'
            lead.qualification_status = 'done'
            lead.qualification_error = ''
            lead.save()
            qualified += 1
        except KeyServiceError as exc:
            # Tokens/key exhausted for this company — leave the lead pending and
            # stop touching this company for the rest of the tick.
            lead.qualification_status = 'pending'
            lead.qualification_error = 'AI tokens exhausted — will retry.'
            lead.qualification_queued_at = now   # back of the queue so other companies aren't starved
            lead.save(update_fields=['qualification_status', 'qualification_error', 'qualification_queued_at', 'updated_at'])
            blocked_companies.add(cu_id)
            logger.warning("SDR qualify-queue: key/quota out for company_user=%s: %s", cu_id, exc)
        except Exception as exc:
            lead.qualification_attempts = (lead.qualification_attempts or 0) + 1
            lead.qualification_error = str(exc)[:500]
            lead.qualification_status = (
                'failed' if lead.qualification_attempts >= QUALIFY_MAX_ATTEMPTS else 'pending'
            )
            lead.save(update_fields=[
                'qualification_attempts', 'qualification_error', 'qualification_status', 'updated_at',
            ])
            failed += 1
            logger.error("SDR qualify-queue: lead %s attempt %s failed: %s",
                         lead.id, lead.qualification_attempts, exc)

    remaining = SDRLead.objects.filter(qualification_status='pending').count()
    logger.info("SDR [qualify-queue] processed=%d qualified=%d failed=%d pending_left=%d",
                len(batch), qualified, failed, remaining)
    return {'processed': len(batch), 'qualified': qualified, 'failed': failed, 'pending': remaining}


@shared_task(bind=True, name='ai_sdr_agent.tasks.qualify_queue_task', max_retries=1)
def qualify_queue_task(self):
    return qualify_queue_impl()
