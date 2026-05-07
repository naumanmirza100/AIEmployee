"""
AI SDR Agent — Background tasks
=================================
Each task is implemented as a plain Python function (_impl) so the embedded
scheduler (threading.Timer, no Celery worker needed) can call it directly.
The Celery shared_tasks simply delegate to those _impl functions.
"""

import logging

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core implementations (plain Python — no Celery dependency)
# ---------------------------------------------------------------------------

def send_due_steps_impl():
    """Send the next due step for every active enrollment whose next_action_at has arrived."""
    from ai_sdr_agent.models import SDRCampaign
    from ai_sdr_agent.agents.outreach_agent import OutreachAgent

    now = timezone.now()
    agent = OutreachAgent()

    active_campaigns = SDRCampaign.objects.filter(status='active')
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
        due_qs = campaign.enrollments.filter(
            status='active'
        ).filter(
            Q(next_action_at__lte=now) | Q(next_action_at__isnull=True)
        ).select_related('lead')

        due_count = due_qs.count()
        logger.info(
            "SDR [send-due-steps] campaign=%d (%s) due_enrollments=%d",
            campaign.id, campaign.name, due_count,
        )

        for enrollment in due_qs:
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
                if status == 'sent':
                    total_sent += 1
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


def check_inbox_replies_impl():
    """Poll IMAP inbox for replies on every active campaign with auto_check_replies=True."""
    from ai_sdr_agent.models import SDRCampaign, SDRMeeting
    from ai_sdr_agent.agents.outreach_agent import OutreachAgent

    agent = OutreachAgent()
    campaigns = SDRCampaign.objects.filter(status='active', auto_check_replies=True)

    total_replies = 0
    total_meetings = 0

    logger.info(
        "SDR [check-inbox] START — checking %d active campaigns for replies",
        campaigns.count(),
    )

    for campaign in campaigns:
        try:
            # Include all non-replied enrollments that have a lead email — even step 0
            # (reply could arrive before the second scheduler cycle advances the step)
            enrollments = list(
                campaign.enrollments
                .filter(status__in=['active', 'completed'])
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
                enrollment = r['enrollment']
                lead_email = r['sender_email']
                subject = r.get('subject', '')

                logger.info(
                    "SDR [check-inbox] processing reply from=%s subject='%s' "
                    "enrollment=%d current_status=%s",
                    lead_email, subject, enrollment.id, enrollment.status,
                )

                if enrollment.status == 'replied':
                    logger.warning(
                        "SDR [DEDUP-REPLY] enrollment=%d lead=%s — "
                        "SKIPPED: enrollment already marked replied (would have sent duplicate)",
                        enrollment.id, lead_email,
                    )
                    continue

                reply_text = r['reply_text']
                sentiment_result = agent.analyze_reply_sentiment(reply_text)
                sentiment = sentiment_result['sentiment']
                is_interested = sentiment_result['is_interested']

                logger.info(
                    "SDR [check-inbox] enrollment=%d lead=%s sentiment=%s "
                    "is_interested=%s reason='%s'",
                    enrollment.id, lead_email, sentiment,
                    is_interested, sentiment_result.get('reason', ''),
                )

                enrollment.status = 'replied'
                enrollment.replied_at = timezone.now()
                enrollment.reply_content = reply_text[:2000]
                enrollment.reply_sentiment = sentiment
                enrollment.save()

                campaign.replies_received = (campaign.replies_received or 0) + 1
                total_replies += 1

                if is_interested:
                    enrollment.lead.status = 'replied'
                    enrollment.lead.save(update_fields=['status'])

                    meeting, created = SDRMeeting.objects.get_or_create(
                        enrollment=enrollment,
                        defaults={
                            'company_user': campaign.company_user,
                            'lead': enrollment.lead,
                            'title': f'Discovery Call with {enrollment.lead.display_name}',
                            'reply_snippet': reply_text[:500],
                            'calendar_link': campaign.calendar_link or '',
                            'status': 'pending',
                        }
                    )

                    if created:
                        total_meetings += 1
                        campaign.meetings_booked = (campaign.meetings_booked or 0) + 1
                        logger.info(
                            "SDR [check-inbox] NEW meeting created for enrollment=%d lead=%s — "
                            "sending scheduling email",
                            enrollment.id, lead_email,
                        )
                        try:
                            from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent
                            sched_agent = MeetingSchedulingAgent()
                            prep_notes = sched_agent.generate_prep_notes(
                                enrollment.lead, enrollment, reply_text
                            )
                            # send_scheduling_email_once is atomic — only one caller sends
                            sent = sched_agent.send_scheduling_email_once(
                                campaign, enrollment.lead, meeting, prep_notes
                            )
                            if sent:
                                meeting.prep_notes = prep_notes
                                meeting.save(update_fields=['prep_notes'])
                        except Exception as exc:
                            logger.warning(
                                "SDR [check-inbox] scheduling email FAILED for %s: %s",
                                lead_email, exc,
                            )
                    else:
                        logger.warning(
                            "SDR [DEDUP-MEETING] enrollment=%d lead=%s — "
                            "meeting already existed (id=%d, status=%s) — "
                            "scheduling email NOT sent again",
                            enrollment.id, lead_email, meeting.id, meeting.status,
                        )

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
    qs = SDRCampaign.objects.filter(status='scheduled', start_date__lte=today)

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

    expired = SDRCampaign.objects.filter(status='active', end_date__lt=today)
    for campaign in expired:
        active_enrollments = campaign.enrollments.filter(status='active')
        for e in active_enrollments:
            e.status = 'completed'
            e.completed_at = timezone.now()
            e.save(update_fields=['status', 'completed_at'])
        campaign.status = 'completed'
        campaign.save(update_fields=['status'])
        completed += 1
        logger.info("SDR auto-complete: campaign %s expired (end_date passed)", campaign.id)

    active = SDRCampaign.objects.filter(status='active').exclude(end_date__lt=today)
    for campaign in active:
        if not campaign.enrollments.filter(status='active').exists() and campaign.enrollments.exists():
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
    window_start = now + timezone.timedelta(hours=24)
    window_end = now + timezone.timedelta(hours=26)

    due = SDRMeeting.objects.filter(
        status='scheduled',
        scheduled_at__gte=window_start,
        scheduled_at__lte=window_end,
        reminder_sent_at__isnull=True,
    ).select_related('lead', 'enrollment__campaign')

    sent = failed = 0
    for meeting in due:
        if not meeting.enrollment or not meeting.enrollment.campaign:
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
