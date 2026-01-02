"""
Views for Email Sending Status and Monitoring
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta, datetime

from .models import Campaign, CampaignContact, EmailSendHistory, EmailSequence


# @login_required
# def email_sending_status(request, campaign_id):
#     campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)

#     now = timezone.now()
#     last_24_hours = now - timedelta(hours=24)
#     horizon = now + timedelta(hours=24)

#     # Show what actually got sent recently (don’t over-filter)
#     sequence_emails = (
#         EmailSendHistory.objects
#         .filter(campaign=campaign, sent_at__gte=last_24_hours)
#         .order_by('-sent_at')
#     )

#     pending_emails = []
#     upcoming_sequence_sends = []

#     if campaign.status == 'active':
#         contacts = (
#             CampaignContact.objects
#             .filter(
#                 campaign=campaign,
#                 sequence__is_active=True,
#                 sequence__isnull=False,
#                 completed=False,
#                 replied=False,
#             )
#             .select_related('lead', 'sequence')
#             .prefetch_related('sequence__steps__template')
#         )[:200]

#         for contact in contacts:
#             sequence = contact.sequence
#             steps = list(sequence.steps.all())
#             next_step_number = contact.current_step + 1
#             next_step = next((s for s in steps if s.step_order == next_step_number), None)
#             if not next_step:
#                 continue

#             # Reference time matches scheduler logic
#             if contact.current_step == 0:
#                 if campaign.start_date:
#                     reference_time = timezone.make_aware(datetime.combine(campaign.start_date, datetime.min.time()))
#                 else:
#                     reference_time = getattr(campaign, 'created_at', now)
#             else:
#                 reference_time = contact.last_sent_at or getattr(campaign, 'created_at', now)

#             delay = timedelta(
#                 days=next_step.delay_days,
#                 hours=next_step.delay_hours,
#                 minutes=next_step.delay_minutes,
#             )
#             next_send_time = reference_time + delay

#             already_sent = EmailSendHistory.objects.filter(
#                 campaign=campaign,
#                 lead=contact.lead,
#                 email_template=next_step.template,
#             ).exists()
#             if already_sent:
#                 continue

#             if next_send_time <= now:
#                 pending_emails.append({
#                     'recipient_email': contact.lead.email,
#                     'subject': next_step.template.subject,
#                 })
#             elif next_send_time <= horizon:
#                 upcoming_sequence_sends.append({
#                     'lead': contact.lead,
#                     'sequence': sequence,
#                     'next_step': next_step,
#                     'next_send_time': next_send_time,
#                 })

#     upcoming_sequence_sends.sort(key=lambda x: x['next_send_time'])

#     stats = {
#         'total_sequence_sent': sequence_emails.count(),
#         'pending_count': len(pending_emails),
#         'upcoming_count': len(upcoming_sequence_sends),
#         'recent_activity': sequence_emails.count(),
#     }

#     currently_sending = {
#         'sequences': (len(pending_emails) > 0) or sequence_emails.filter(sent_at__gte=now - timedelta(minutes=5)).exists(),
#     }

#     context = {
#         'campaign': campaign,
#         'sequence_emails': sequence_emails[:20],
#         'pending_emails': pending_emails[:10],
#         'upcoming_sequence_sends': upcoming_sequence_sends[:20],
#         'stats': stats,
#         'currently_sending': currently_sending,
#     }
#     return render(request, 'marketing/email_sending_status.html', context)


@login_required
def email_sending_status(request, campaign_id):
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)

    now = timezone.now()
    last_24_hours = now - timedelta(hours=24)
    horizon = now + timedelta(hours=24)

    # ✅ ONLY recent emails
    recent_sequence_emails = (
        EmailSendHistory.objects
        .filter(campaign=campaign, sent_at__gte=last_24_hours)
        .order_by('-sent_at')
    )

    pending_emails = []
    upcoming_sequence_sends = []

    if campaign.status == 'active':
        contacts = (
            CampaignContact.objects
            .filter(
                campaign=campaign,
                sequence__is_active=True,
                sequence__isnull=False,
                completed=False,
                replied=False,
            )
            .select_related('lead', 'sequence')
            .prefetch_related('sequence__steps__template')
        )[:200]

        for contact in contacts:
            sequence = contact.sequence
            steps = list(sequence.steps.all())
            next_step = next(
                (s for s in steps if s.step_order == contact.current_step + 1),
                None
            )
            if not next_step:
                continue

            reference_time = (
                timezone.make_aware(datetime.combine(campaign.start_date, datetime.min.time()))
                if contact.current_step == 0 and campaign.start_date
                else contact.last_sent_at or campaign.created_at
            )

            next_send_time = reference_time + timedelta(
                days=next_step.delay_days,
                hours=next_step.delay_hours,
                minutes=next_step.delay_minutes,
            )

            already_sent = EmailSendHistory.objects.filter(
                campaign=campaign,
                lead=contact.lead,
                email_template=next_step.template,
            ).exists()

            if already_sent:
                continue

            if next_send_time <= now:
                pending_emails.append({
                    'recipient_email': contact.lead.email,
                    'subject': next_step.template.subject,
                })
            elif next_send_time <= horizon:
                upcoming_sequence_sends.append({
                    'lead': contact.lead,
                    'sequence': sequence,
                    'next_step': next_step,
                    'next_send_time': next_send_time,
                })

    upcoming_sequence_sends.sort(key=lambda x: x['next_send_time'])

    context = {
        'campaign': campaign,
        'sequence_emails': recent_sequence_emails[:20],  # ✅ recent only
        'pending_emails': pending_emails[:10],
        'upcoming_sequence_sends': upcoming_sequence_sends[:20],
    }

    return render(request, 'marketing/email_sending_status.html', context)



# @login_required
# def email_status_api(request, campaign_id):
#     campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)

#     now = timezone.now()
#     last_5_min = now - timedelta(minutes=5)

#     recent_sequence = EmailSendHistory.objects.filter(
#         campaign=campaign,
#         sent_at__gte=last_5_min
#     ).count()

#     pending_count = 0
#     if campaign.status == 'active':
#         contacts = (
#             CampaignContact.objects
#             .filter(
#                 campaign=campaign,
#                 sequence__is_active=True,
#                 sequence__isnull=False,
#                 completed=False,
#                 replied=False,
#             )
#             .select_related('lead', 'sequence')
#             .prefetch_related('sequence__steps__template')
#         )[:200]

#         for contact in contacts:
#             steps = list(contact.sequence.steps.all())
#             next_step = next((s for s in steps if s.step_order == contact.current_step + 1), None)
#             if not next_step:
#                 continue

#             if contact.current_step == 0:
#                 if campaign.start_date:
#                     reference_time = timezone.make_aware(datetime.combine(campaign.start_date, datetime.min.time()))
#                 else:
#                     reference_time = getattr(campaign, 'created_at', now)
#             else:
#                 reference_time = contact.last_sent_at or getattr(campaign, 'created_at', now)

#             next_send_time = reference_time + timedelta(
#                 days=next_step.delay_days,
#                 hours=next_step.delay_hours,
#                 minutes=next_step.delay_minutes,
#             )

#             already_sent = EmailSendHistory.objects.filter(
#                 campaign=campaign,
#                 lead=contact.lead,
#                 email_template=next_step.template,
#             ).exists()

#             if (not already_sent) and (next_send_time <= now):
#                 pending_count += 1
#             print("pending_count", pending_count)
#             print("next_send_time", next_send_time)
#             print("now", now)
#             print("Sequence", recent_sequence)
#     return JsonResponse({
#         'success': True,
#         'sequence_sending': recent_sequence > 0,
#         'pending_count': pending_count,
#         'recent_sequence_count': recent_sequence,
#         'timestamp': now.isoformat(),
#     })

@login_required
def email_status_api(request, campaign_id):
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)

    now = timezone.now()
    last_5_min = now - timedelta(minutes=5)

    # ALL email history
    all_sent_emails = EmailSendHistory.objects.filter(
        campaign=campaign
    )

    # Detect active sending (last 5 minutes)
    recent_sequence_count = all_sent_emails.filter(
        sent_at__gte=last_5_min
    ).count()

    pending_count = 0
    if campaign.status == 'active':
        contacts = (
            CampaignContact.objects
            .filter(
                campaign=campaign,
                sequence__is_active=True,
                sequence__isnull=False,
                completed=False,
                replied=False,
            )
            .select_related('lead', 'sequence')
            .prefetch_related('sequence__steps__template')
        )[:200]

        for contact in contacts:
            steps = list(contact.sequence.steps.all())
            next_step = next(
                (s for s in steps if s.step_order == contact.current_step + 1),
                None
            )
            if not next_step:
                continue

            reference_time = (
                timezone.make_aware(datetime.combine(campaign.start_date, datetime.min.time()))
                if contact.current_step == 0 and campaign.start_date
                else contact.last_sent_at or campaign.created_at
            )

            next_send_time = reference_time + timedelta(
                days=next_step.delay_days,
                hours=next_step.delay_hours,
                minutes=next_step.delay_minutes,
            )

            already_sent = EmailSendHistory.objects.filter(
                campaign=campaign,
                lead=contact.lead,
                email_template=next_step.template,
            ).exists()

            if not already_sent and next_send_time <= now:
                pending_count += 1

    return JsonResponse({
        'success': True,

        # 🔑 MATCH TEMPLATE EXPECTATIONS
        'currently_sending': {
            'sequences': recent_sequence_count > 0
        },

        'stats': {
            'pending_count': pending_count,
            'total_sequence_sent': all_sent_emails.count(),
                    # 'upcoming_count': upcoming_sequence_count,  # calculate upcoming emails in next 24h

        },

        # Optional debug/info
        'recent_sequence_count': recent_sequence_count,
        'timestamp': now.isoformat(),
    })
