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
    """Full detailed email sending status page with comprehensive history"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)

    now = timezone.now()
    last_24_hours = now - timedelta(hours=24)
    horizon = now + timedelta(hours=24)

    # Get ALL email history (not just last 24 hours) for detailed view
    all_email_history_queryset = (
        EmailSendHistory.objects
        .filter(campaign=campaign)
        .select_related('email_template', 'lead')
        .prefetch_related('email_template__sequence_steps__sequence', 'email_template__sequence_steps__sequence__campaign')
        .order_by('-sent_at', '-created_at')
    )

    # Recent sequence emails (last 24 hours) - slice after filtering
    # Make sure to select_related lead for reply button functionality
    recent_sequence_emails_queryset = all_email_history_queryset.filter(sent_at__gte=last_24_hours).select_related('lead', 'email_template')
    recent_sequence_emails = list(recent_sequence_emails_queryset[:50])  # Convert to list to avoid queryset issues
    
    # Get replied status for all leads in this campaign
    from marketing_agent.models import CampaignContact
    replied_lead_ids = set(
        CampaignContact.objects.filter(
            campaign=campaign,
            replied=True
        ).values_list('lead_id', flat=True)
    )
    
    # Get sequence info for emails (check if template is part of a sequence)
    # We'll add this info to each email in the template

    # Calculate comprehensive stats (use queryset before slicing)
    # Note: 'sent' and 'delivered' are treated the same since emails are set to 'sent' on successful send
    # and there's no separate delivery tracking mechanism
    email_stats = {
        'total_sent': all_email_history_queryset.filter(status__in=['sent', 'delivered', 'opened', 'clicked']).count(),
        'total_opened': all_email_history_queryset.filter(status__in=['opened', 'clicked']).count(),
        'total_clicked': all_email_history_queryset.filter(status='clicked').count(),
        'total_failed': all_email_history_queryset.filter(status='failed').count(),
        'total_bounced': all_email_history_queryset.filter(status='bounced').count(),
        'total_replied': CampaignContact.objects.filter(campaign=campaign, replied=True).count(),
    }

    # Calculate rates (based on total_sent)
    if email_stats['total_sent'] > 0:
        email_stats['open_rate'] = (email_stats['total_opened'] / email_stats['total_sent']) * 100
        email_stats['click_rate'] = (email_stats['total_clicked'] / email_stats['total_sent']) * 100
        email_stats['bounce_rate'] = (email_stats['total_bounced'] / email_stats['total_sent']) * 100
    else:
        email_stats['open_rate'] = 0
        email_stats['click_rate'] = 0
        email_stats['bounce_rate'] = 0

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
                    'template': next_step.template,
                    'lead': contact.lead,
                    'sequence': sequence,
                    'next_step': next_step,
                })
            elif next_send_time <= horizon:
                upcoming_sequence_sends.append({
                    'lead': contact.lead,
                    'sequence': sequence,
                    'next_step': next_step,
                    'next_send_time': next_send_time,
                })

    upcoming_sequence_sends.sort(key=lambda x: x['next_send_time'])

    # Get replied contacts
    replied_contacts = CampaignContact.objects.filter(
        campaign=campaign,
        replied=True
    ).select_related('lead').order_by('-replied_at')[:20]

    # Check if currently sending (emails sent in last 5 minutes)
    last_5_min = now - timedelta(minutes=5)
    currently_sending_emails = all_email_history_queryset.filter(sent_at__gte=last_5_min).exists()
    
    # Get replied status for all leads in this campaign (for quick lookup)
    from marketing_agent.models import CampaignContact
    replied_contacts_dict = {}
    for contact in CampaignContact.objects.filter(campaign=campaign, replied=True).select_related('lead'):
        replied_contacts_dict[contact.lead_id] = contact
    
    # Find emails that were sent BEFORE each reply was received
    # Only show "Replied" on emails sent BEFORE the reply timestamp (not after)
    replied_email_ids = set()
    for lead_id, contact in replied_contacts_dict.items():
        if contact.replied_at:
            # Only find emails that were sent BEFORE the reply was received
            # This ensures we don't show "Replied" on emails sent after the reply
            triggering_emails = all_email_history_queryset.filter(
                lead_id=lead_id,
                sent_at__lt=contact.replied_at,  # Use __lt (less than) not __lte to exclude emails sent at exact same time
                sent_at__gte=contact.replied_at - timedelta(days=30)  # Within 30 days before reply
            )
            
            for email in triggering_emails:
                replied_email_ids.add(email.id)
    
    # Check which sequences are sub-sequences for identifying email types
    sub_sequence_ids = set(
        EmailSequence.objects.filter(
            campaign=campaign,
            is_sub_sequence=True
        ).values_list('id', flat=True)
    )
    
    # Add replied status and sequence info to each email
    all_email_history_list = []
    for email in all_email_history_queryset[:100]:
        # Only show "Replied" if:
        # 1. This email is in replied_email_ids (sent before a reply was received)
        # 2. The lead actually replied (has a contact in replied_contacts_dict)
        is_replied = email.id in replied_email_ids
        
        # Only get contact if this email is actually replied
        contact = None
        if is_replied:
            contact = replied_contacts_dict.get(email.lead_id)
            # Double-check: make sure this lead actually replied
            if not contact or not contact.replied:
                is_replied = False
                contact = None
        
        # Check if this is a sub-sequence email
        # An email is from a sub-sequence if its template is part of a sequence that is a sub-sequence
        is_sub_sequence_email = False
        if email.email_template:
            # Check if the template is part of a sub-sequence
            sub_seq_steps = email.email_template.sequence_steps.filter(
                sequence__is_sub_sequence=True,
                sequence__campaign=campaign
            )
            if sub_seq_steps.exists():
                is_sub_sequence_email = True
        
        email_dict = {
            'email': email,
            'is_replied': is_replied,
            'contact': contact,
            'is_sequence_email': email.is_followup or (email.email_template and email.email_template.sequence_steps.exists()),
            'is_sub_sequence_email': is_sub_sequence_email,
        }
        all_email_history_list.append(email_dict)
    
    # Also add this info to recent sequence emails
    recent_sequence_emails_list = []
    for email in recent_sequence_emails:
        # Only show "Replied" if this email was sent before a reply was received
        is_replied = email.id in replied_email_ids
        
        # Only get contact if this email is actually replied
        contact = None
        if is_replied:
            contact = replied_contacts_dict.get(email.lead_id)
            # Double-check: make sure this lead actually replied
            if not contact or not contact.replied:
                is_replied = False
                contact = None
        
        # Check if this is a sub-sequence email
        is_sub_sequence_email = False
        if email.email_template:
            sub_seq_steps = email.email_template.sequence_steps.filter(
                sequence__is_sub_sequence=True,
                sequence__campaign=campaign
            )
            if sub_seq_steps.exists():
                is_sub_sequence_email = True
        
        email_dict = {
            'email': email,
            'is_replied': is_replied,
            'contact': contact,
            'is_sequence_email': email.is_followup or (email.email_template and email.email_template.sequence_steps.exists()),
            'is_sub_sequence_email': is_sub_sequence_email,
        }
        recent_sequence_emails_list.append(email_dict)
    
    context = {
        'campaign': campaign,
        'all_email_history': all_email_history_list,  # Now includes replied/sequence info
        'sequence_emails': recent_sequence_emails_list,  # Now includes replied/sequence info
        'pending_emails': pending_emails,
        'upcoming_sequence_sends': upcoming_sequence_sends,
        'replied_contacts': replied_contacts,
        'stats': email_stats,
        'currently_sending': {
            'sequences': len(pending_emails) > 0 or currently_sending_emails,
        },
    }
    # print("context", context, '/n')
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
    """API endpoint for real-time status updates"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)

    now = timezone.now()
    last_5_min = now - timedelta(minutes=5)
    horizon = now + timedelta(hours=24)

    # ALL email history
    all_sent_emails = EmailSendHistory.objects.filter(
        campaign=campaign
    )

    # Detect active sending (last 5 minutes)
    recent_sequence_count = all_sent_emails.filter(
        sent_at__gte=last_5_min
    ).count()

    # Calculate comprehensive stats
    # Note: 'sent' and 'delivered' are treated the same since emails are set to 'sent' on successful send
    stats = {
        'total_sent': all_sent_emails.filter(status__in=['sent', 'delivered', 'opened', 'clicked']).count(),
        'total_opened': all_sent_emails.filter(status__in=['opened', 'clicked']).count(),
        'total_clicked': all_sent_emails.filter(status='clicked').count(),
        'total_bounced': all_sent_emails.filter(status='bounced').count(),
        'total_replied': CampaignContact.objects.filter(campaign=campaign, replied=True).count(),
    }

    # Calculate rates (based on total_sent)
    if stats['total_sent'] > 0:
        stats['open_rate'] = (stats['total_opened'] / stats['total_sent']) * 100
        stats['click_rate'] = (stats['total_clicked'] / stats['total_sent']) * 100
        stats['bounce_rate'] = (stats['total_bounced'] / stats['total_sent']) * 100
    else:
        stats['open_rate'] = 0
        stats['click_rate'] = 0
        stats['bounce_rate'] = 0

    pending_count = 0
    upcoming_count = 0
    
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

            if not already_sent:
                if next_send_time <= now:
                    pending_count += 1
                elif next_send_time <= horizon:
                    upcoming_count += 1

    stats['pending_count'] = pending_count
    stats['upcoming_count'] = upcoming_count
    stats['total_sequence_sent'] = all_sent_emails.count()

    return JsonResponse({
        'success': True,
        'currently_sending': {
            'sequences': recent_sequence_count > 0
        },
        'stats': stats,
        'recent_sequence_count': recent_sequence_count,
        'timestamp': now.isoformat(),
    })
