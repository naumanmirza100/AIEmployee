"""
Views for Email Sending Status and Monitoring
"""
import logging
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta, datetime

from .models import Campaign, CampaignContact, EmailSendHistory, EmailSequence

logger = logging.getLogger(__name__)


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

            # Calculate reference time for delay calculation
            if contact.current_step == 0:
                # First step: use contact creation time or started_at as reference
                # This ensures delays are calculated from when contact was added, not from current time
                # If started_at is set, use it; otherwise use created_at
                reference_time = contact.started_at if contact.started_at else contact.created_at
            else:
                # Subsequent steps: use last_sent_at if available and recent, otherwise use now
                if contact.last_sent_at and contact.last_sent_at <= now:
                    # Check if last_sent_at is too old (more than 24 hours ago) - might be stale data
                    time_since_last = now - contact.last_sent_at
                    if time_since_last > timedelta(hours=24):
                        # last_sent_at is too old, use current time instead
                        reference_time = now
                    else:
                        # last_sent_at exists and is recent, use it
                        reference_time = contact.last_sent_at
                else:
                    # No last_sent_at or it's in the future (data issue), use current time
                    reference_time = now

            next_send_time = reference_time + timedelta(
                days=next_step.delay_days,
                hours=next_step.delay_hours,
                minutes=next_step.delay_minutes,
            )
            
            # Final safeguard: if next_send_time is in the past (for step 0, this means delay already passed)
            # For step 0, if send_time is in the past, it's ready to send (don't recalculate)
            # For subsequent steps, if send_time is way in the past, recalculate from now
            if contact.current_step == 0:
                # For step 0, if send_time is in the past, it means the delay has passed - ready to send
                # Don't recalculate, just let it be ready
                pass
            elif next_send_time < now - timedelta(hours=1):
                # For subsequent steps, if send_time is way in the past, recalculate from now
                reference_time = now
                next_send_time = reference_time + timedelta(
                    days=next_step.delay_days,
                    hours=next_step.delay_hours,
                    minutes=next_step.delay_minutes,
                )

            # Check if email was already sent successfully
            existing_email = EmailSendHistory.objects.filter(
                campaign=campaign,
                lead=contact.lead,
                email_template=next_step.template,
            ).first()

            # If email exists with successful status, skip it
            if existing_email and existing_email.status in ['sent', 'delivered', 'opened', 'clicked']:
                continue

            # If email is ready to send (time has passed)
            if next_send_time <= now:
                # Check if this is a retry (pending/failed email)
                is_retry = existing_email and existing_email.status in ['pending', 'failed']
                
                pending_emails.append({
                    'recipient_email': contact.lead.email,
                    'subject': next_step.template.subject,
                    'template': next_step.template,
                    'lead': contact.lead,
                    'sequence': sequence,
                    'next_step': next_step,
                    'is_retry': is_retry,
                    'previous_status': existing_email.status if existing_email else None,
                    'is_sub_sequence': False,  # This is a regular sequence email
                })
            elif next_send_time <= horizon:
                upcoming_sequence_sends.append({
                    'lead': contact.lead,
                    'sequence': sequence,
                    'next_step': next_step,
                    'next_send_time': next_send_time,
                    'delay_days': next_step.delay_days,
                    'delay_hours': next_step.delay_hours,
                    'delay_minutes': next_step.delay_minutes,
                    'is_sub_sequence': False,  # This is a regular sequence email
                })

    # Handle sub-sequences for pending and upcoming emails
    if campaign.status == 'active':
        # First, get contacts with sub-sequences (existing logic for current sub-sequence progress)
        sub_sequence_contacts = (
            CampaignContact.objects
            .filter(
                campaign=campaign,
                sub_sequence__is_active=True,
                sub_sequence__isnull=False,
                sub_sequence_completed=False,
                replied=True,  # Sub-sequences only apply to replied contacts
            )
            .select_related('lead', 'sequence', 'sub_sequence', 'sub_sequence__parent_sequence')  # Load sub_sequence and its parent_sequence
            .prefetch_related('sub_sequence__steps__template', 'replies')
        )[:200]
        
        # Track which contact+sub-sequence combinations we've already processed
        processed_contact_subseq = set()

        for contact in sub_sequence_contacts:
            sub_sequence = contact.sub_sequence
            if not sub_sequence:
                continue
            
            # CRITICAL: Always get parent sequence from sub_sequence.parent_sequence
            # Reload from database to ensure we have the latest data
            parent_sequence = None
            try:
                # Reload sub_sequence with parent_sequence to ensure it's loaded correctly
                sub_sequence_fresh = EmailSequence.objects.select_related('parent_sequence').get(id=sub_sequence.id)
                
                # Get parent sequence - this is the CORRECT parent sequence from the database
                if sub_sequence_fresh.parent_sequence:
                    parent_sequence = sub_sequence_fresh.parent_sequence
                    # Verify this parent_sequence matches contact.sequence (data integrity check)
                    if contact.sequence and parent_sequence.id != contact.sequence.id:
                        # Parent sequence doesn't match contact.sequence - use parent_sequence from DB (more reliable)
                        logger.warning(
                            f"Mismatch: Sub-sequence {sub_sequence_fresh.id} parent is {parent_sequence.id} "
                            f"but contact.sequence is {contact.sequence.id}. Using parent_sequence from DB."
                        )
                else:
                    # If parent_sequence is not set, try contact.sequence as fallback
                    # But verify that this sub_sequence actually belongs to this sequence
                    if contact.sequence:
                        # Verify: check if sub_sequence was created as child of contact.sequence
                        # (by checking if sub_sequence.name or any other identifier suggests it belongs)
                        # For now, use contact.sequence but log the issue
                        parent_sequence = contact.sequence
                        logger.warning(
                            f"Sub-sequence {sub_sequence_fresh.id} ({sub_sequence_fresh.name}) has no parent_sequence in DB. "
                            f"Using contact.sequence {contact.sequence.id} as fallback for {contact.lead.email}"
                        )
                    else:
                        logger.error(
                            f"Sub-sequence {sub_sequence_fresh.id} has no parent_sequence AND contact has no sequence. "
                            f"Contact: {contact.lead.email}"
                        )
                        continue
                
                # Update sub_sequence to use fresh data
                sub_sequence = sub_sequence_fresh
                
            except EmailSequence.DoesNotExist:
                # Sub-sequence doesn't exist anymore, skip
                logger.warning(f"Sub-sequence {sub_sequence.id} not found in database for contact {contact.lead.email}")
                continue
            except Exception as e:
                logger.error(f"Error loading sub-sequence {sub_sequence.id}: {str(e)}")
                continue
            
            if not parent_sequence:
                logger.error(f"Could not determine parent_sequence for sub-sequence {sub_sequence.id}, contact {contact.lead.email}")
                continue
            steps = list(sub_sequence.steps.all())
            next_step = next(
                (s for s in steps if s.step_order == contact.sub_sequence_step + 1),
                None
            )
            if not next_step:
                continue

            # Calculate reference time for delay calculation (use sub_sequence_last_sent_at)
            if contact.sub_sequence_step == 0:
                # First step in sub-sequence: use replied_at or now
                reference_time = contact.replied_at if contact.replied_at else contact.updated_at
            else:
                # Subsequent steps: use sub_sequence_last_sent_at
                if contact.sub_sequence_last_sent_at and contact.sub_sequence_last_sent_at <= now:
                    time_since_last = now - contact.sub_sequence_last_sent_at
                    if time_since_last > timedelta(hours=24):
                        reference_time = now
                    else:
                        reference_time = contact.sub_sequence_last_sent_at
                else:
                    reference_time = now

            next_send_time = reference_time + timedelta(
                days=next_step.delay_days,
                hours=next_step.delay_hours,
                minutes=next_step.delay_minutes,
            )
            
            # Final safeguard: if next_send_time is way in the past, recalculate from now
            if contact.sub_sequence_step > 0 and next_send_time < now - timedelta(hours=1):
                reference_time = now
                next_send_time = reference_time + timedelta(
                    days=next_step.delay_days,
                    hours=next_step.delay_hours,
                    minutes=next_step.delay_minutes,
                )

            # Check if email was already sent successfully
            existing_email = EmailSendHistory.objects.filter(
                campaign=campaign,
                lead=contact.lead,
                email_template=next_step.template,
            ).first()

            # If email exists with successful status, skip it
            if existing_email and existing_email.status in ['sent', 'delivered', 'opened', 'clicked']:
                continue

            # If email is ready to send (time has passed)
            if next_send_time <= now:
                # Check if this is a retry (pending/failed email)
                is_retry = existing_email and existing_email.status in ['pending', 'failed']
                
                pending_emails.append({
                    'recipient_email': contact.lead.email,
                    'subject': next_step.template.subject,
                    'template': next_step.template,
                    'lead': contact.lead,
                    'sequence': parent_sequence,  # Use parent sequence for grouping
                    'next_step': next_step,
                    'is_retry': is_retry,
                    'previous_status': existing_email.status if existing_email else None,
                    'is_sub_sequence': True,  # This is a sub-sequence email
                    'sub_sequence': sub_sequence,  # Store sub-sequence reference
                })
                # Mark this contact+sub-sequence combination as processed
                processed_contact_subseq.add((contact.id, sub_sequence.id))
            elif next_send_time <= horizon:
                upcoming_sequence_sends.append({
                    'lead': contact.lead,
                    'sequence': parent_sequence,  # Use parent sequence for grouping
                    'next_step': next_step,
                    'next_send_time': next_send_time,
                    'delay_days': next_step.delay_days,
                    'delay_hours': next_step.delay_hours,
                    'delay_minutes': next_step.delay_minutes,
                    'is_sub_sequence': True,  # This is a sub-sequence email
                    'sub_sequence': sub_sequence,  # Store sub-sequence reference
                })
                processed_contact_subseq.add((contact.id, sub_sequence.id))

        # NOW: Also check Reply records for replies that should trigger sub-sequence emails
        # This handles cases where a contact replied multiple times - each reply should get sub-sequence emails
        # IMPORTANT: Only replies to MAIN SEQUENCE emails should trigger sub-sequences
        # Replies to SUB-SEQUENCE emails should NOT trigger new sub-sequences
        from marketing_agent.models import Reply
        
        # Get all main sequence replies that should trigger sub-sequences
        # IMPORTANT: reply.sub_sequence field indicates which sub-sequence email was replied to
        # If sub_sequence__isnull=True, it means this reply was to a MAIN sequence email
        # We check ALL such replies, even if matching sub-sequence was created AFTER the reply
        # We verify if the matching sub-sequence email was actually sent for each reply
        main_sequence_replies = Reply.objects.filter(
            campaign=campaign,
            sequence__isnull=False,  # Has a sequence (main sequence)
            sequence__is_sub_sequence=False,  # Main sequence reply (not sub-sequence reply)
            sub_sequence__isnull=True,  # CRITICAL: Reply was to MAIN sequence email (not sub-sequence email)
            interest_level__in=['positive', 'negative', 'neutral', 'requested_info', 'objection', 'unsubscribe'],  # Valid interest levels (including unsubscribe)
        ).select_related(
            'contact', 'lead', 'sequence', 'contact__sub_sequence'
        ).prefetch_related(
            'sequence__sub_sequences__steps__template'
        ).order_by('-replied_at')[:200]  # Check more replies to catch old ones (created before sub-sequence)
        
        for reply in main_sequence_replies:
            contact = reply.contact
            if not contact or not contact.sequence:
                continue
            
            # Find the appropriate sub-sequence for this reply based on interest_level
            target_interest = reply.interest_level if reply.interest_level != 'not_analyzed' else 'neutral'
            
            # Map interest levels (same as in views.py)
            interest_mapping = {
                'positive': 'positive',
                'negative': 'negative',
                'neutral': 'neutral',
                'requested_info': 'requested_info',
                'objection': 'objection',
                'unsubscribe': 'unsubscribe',
            }
            target_interest = interest_mapping.get(target_interest, target_interest)
            
            # Find matching sub-sequence
            sub_sequences = EmailSequence.objects.filter(
                parent_sequence=contact.sequence,
                is_sub_sequence=True,
                is_active=True,
                interest_level=target_interest
            )
            
            # If no exact match, try 'any'
            if not sub_sequences.exists() and target_interest != 'any':
                sub_sequences = EmailSequence.objects.filter(
                    parent_sequence=contact.sequence,
                    is_sub_sequence=True,
                    is_active=True,
                    interest_level='any'
                )
            
            if not sub_sequences.exists():
                continue
                
            sub_sequence = sub_sequences.first()
            
            # Skip if we already processed this contact+sub-sequence combination
            if (contact.id, sub_sequence.id) in processed_contact_subseq:
                continue
            
            # Get parent sequence
            parent_sequence = sub_sequence.parent_sequence or contact.sequence
            if not parent_sequence:
                continue
            
            # Get first step of sub-sequence
            steps = list(sub_sequence.steps.all().order_by('step_order'))
            if not steps:
                continue
            
            first_step = steps[0]  # Step 1 (step_order=1, but we get first in order)
            
            # Check if first email has already been sent for THIS specific reply
            # We check if any sub-sequence email was sent AFTER this reply was made
            reply_time = reply.replied_at or reply.created_at
            existing_emails = EmailSendHistory.objects.filter(
                campaign=campaign,
                lead=contact.lead,
                email_template=first_step.template,
                sent_at__gte=reply_time  # Sent after this reply
            )
            
            # Skip if first email was already sent for this reply
            if existing_emails.filter(status__in=['sent', 'delivered', 'opened', 'clicked']).exists():
                continue
            
            # Check if it's time to send (based on reply time + delay)
            delay = timedelta(
                days=first_step.delay_days,
                hours=first_step.delay_hours,
                minutes=first_step.delay_minutes
            )
            next_send_time = reply_time + delay
            
            # If ready to send, add to pending
            if next_send_time <= now:
                # Check if this email is already in pending list (avoid duplicates)
                already_pending = any(
                    e.get('lead') == contact.lead and 
                    e.get('template') == first_step.template and
                    e.get('is_sub_sequence') == True
                    for e in pending_emails
                )
                
                if not already_pending:
                    pending_emails.append({
                        'recipient_email': contact.lead.email,
                        'subject': first_step.template.subject,
                        'template': first_step.template,
                        'lead': contact.lead,
                        'sequence': parent_sequence,
                        'next_step': first_step,
                        'is_retry': False,
                        'previous_status': None,
                        'is_sub_sequence': True,
                        'sub_sequence': sub_sequence,
                        'reply_id': reply.id,  # Track which reply this is for
                    })
                    processed_contact_subseq.add((contact.id, sub_sequence.id))
            elif next_send_time <= horizon:
                # Add to upcoming if not already there
                already_upcoming = any(
                    e.get('lead') == contact.lead and
                    e.get('next_step') == first_step and
                    e.get('is_sub_sequence') == True
                    for e in upcoming_sequence_sends
                )
                
                if not already_upcoming:
                    upcoming_sequence_sends.append({
                        'lead': contact.lead,
                        'sequence': parent_sequence,
                        'next_step': first_step,
                        'next_send_time': next_send_time,
                        'delay_days': first_step.delay_days,
                        'delay_hours': first_step.delay_hours,
                        'delay_minutes': first_step.delay_minutes,
                        'is_sub_sequence': True,
                        'sub_sequence': sub_sequence,
                        'reply_id': reply.id,
                    })

    upcoming_sequence_sends.sort(key=lambda x: x['next_send_time'])

    # Also include standalone EmailSendHistory records with status 'pending' or 'failed' that need retry
    # These are emails that were attempted but didn't send successfully
    pending_email_history = EmailSendHistory.objects.filter(
        campaign=campaign,
        status__in=['pending', 'failed'],
        sent_at__isnull=True,  # Never successfully sent
    ).select_related('lead', 'email_template')[:50]
    
    for email_history in pending_email_history:
        # Check if this email is already in pending_emails list (from sequence logic above)
        already_in_list = any(
            e.get('lead') and email_history.lead and e['lead'].id == email_history.lead.id and
            e.get('template') and email_history.email_template and e['template'].id == email_history.email_template.id
            for e in pending_emails
        )
        
        if not already_in_list and email_history.lead and email_history.email_template:
            pending_emails.append({
                'recipient_email': email_history.recipient_email,
                'subject': email_history.subject,
                'template': email_history.email_template,
                'lead': email_history.lead,
                'sequence': None,
                'next_step': None,
                'is_retry': True,
                'previous_status': email_history.status,
                'email_history_id': email_history.id,
            })

    # Get all replies (from Reply model) - shows all reply history, not just latest
    # Use try/except in case Reply model doesn't exist yet (migration not applied)
    all_replies = []
    replies_by_sequence = {}  # Organize replies by sequence
    try:
        from marketing_agent.models import Reply
        all_replies = list(Reply.objects.filter(
            campaign=campaign
        ).select_related('lead', 'contact', 'sequence', 'sub_sequence').order_by('-replied_at')[:100])
        
        # Organize replies by sequence
        for reply in all_replies:
            seq_key = reply.sequence.id if reply.sequence else 'no_sequence'
            if seq_key not in replies_by_sequence:
                replies_by_sequence[seq_key] = {
                    'sequence': reply.sequence,
                    'sequence_name': reply.sequence.name if reply.sequence else 'No Sequence',
                    'replies': []
                }
            replies_by_sequence[seq_key]['replies'].append(reply)
    except (ImportError, AttributeError, Exception) as e:
        # Reply model doesn't exist yet, migration not applied, or database error - use empty list
        # This allows the page to still load using replied_contacts as fallback
        try:
            logger.warning(f'Reply model not available: {str(e)}')
        except:
            pass  # Logger might not be available
        all_replies = []
        replies_by_sequence = {}
    
    # Update stats with total replies count
    email_stats['total_replied'] = len(all_replies) if all_replies else CampaignContact.objects.filter(campaign=campaign, replied=True).count()
    
    # Get replied contacts (for backward compatibility and quick stats)
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
    
    # Map replies to emails using Reply.triggering_email (most accurate)
    # This handles multiple replies from the same lead correctly
    replied_email_ids = set()  # Emails that have replies
    email_replies_map = {}  # Map email_id -> list of Reply objects for that email
    
    try:
        from marketing_agent.models import Reply
        # Get all replies with their triggering emails
        replies_with_emails = Reply.objects.filter(
            campaign=campaign,
            triggering_email__isnull=False
        ).select_related('triggering_email', 'lead', 'sequence', 'sub_sequence')
        
        for reply in replies_with_emails:
            email_id = reply.triggering_email.id
            replied_email_ids.add(email_id)
            
            # Store all replies for this email
            if email_id not in email_replies_map:
                email_replies_map[email_id] = []
            email_replies_map[email_id].append(reply)
    except (ImportError, AttributeError, Exception) as e:
        # Fallback: use old method if Reply model not available
        logger.warning(f'Could not use Reply.triggering_email: {str(e)}')
        for lead_id, contact in replied_contacts_dict.items():
            reply_timestamp = contact.replied_at if contact.replied_at else contact.updated_at
            if reply_timestamp:
                triggering_emails = all_email_history_queryset.filter(
                    lead_id=lead_id,
                    sent_at__lt=reply_timestamp,
                    sent_at__gte=reply_timestamp - timedelta(days=30)
                ).order_by('-sent_at')
                if triggering_emails.exists():
                    most_recent_email = triggering_emails.first()
                    replied_email_ids.add(most_recent_email.id)
    
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
        # Check if this email has replies (using Reply.triggering_email)
        is_replied = email.id in replied_email_ids
        
        # Get the reply(ies) for this email
        email_replies = email_replies_map.get(email.id, [])
        # Get the most recent reply for display
        latest_reply = email_replies[0] if email_replies else None
        
        # Get contact info from reply or fallback to replied_contacts_dict
        contact = None
        if latest_reply:
            # Use contact from the reply
            contact = latest_reply.contact
        elif is_replied:
            # Fallback: use replied_contacts_dict
            contact = replied_contacts_dict.get(email.lead_id)
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
        
        # Get replies for this email
        email_replies = email_replies_map.get(email.id, [])
        latest_reply = email_replies[0] if email_replies else None
        
        email_dict = {
            'email': email,
            'is_replied': is_replied,
            'contact': contact,
            'latest_reply': latest_reply,  # Most recent reply for this email
            'all_replies': email_replies,  # All replies for this email (if multiple)
            'is_sequence_email': email.is_followup or (email.email_template and email.email_template.sequence_steps.exists()),
            'is_sub_sequence_email': is_sub_sequence_email,
        }
        all_email_history_list.append(email_dict)
    
    # Also add this info to recent sequence emails
    recent_sequence_emails_list = []
    for email in recent_sequence_emails:
        # Check if this email has replies
        is_replied = email.id in replied_email_ids
        
        # Get the reply(ies) for this email
        email_replies = email_replies_map.get(email.id, [])
        latest_reply = email_replies[0] if email_replies else None
        
        # Get contact info
        contact = None
        if latest_reply:
            contact = latest_reply.contact
        elif is_replied:
            contact = replied_contacts_dict.get(email.lead_id)
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
            'latest_reply': latest_reply,  # Most recent reply for this email
            'all_replies': email_replies,  # All replies for this email (if multiple)
            'is_sequence_email': email.is_followup or (email.email_template and email.email_template.sequence_steps.exists()),
            'is_sub_sequence_email': is_sub_sequence_email,
        }
        recent_sequence_emails_list.append(email_dict)
    
    # Organize email history by sequence
    # Key principle: determine which sequence an email belongs to by checking
    # which sequence the lead was in when the email was sent
    emails_by_sequence = {}
    
    # Pre-fetch all contacts for this campaign to determine sequences
    all_contacts = CampaignContact.objects.filter(campaign=campaign).select_related(
        'sequence', 'sub_sequence', 'sub_sequence__parent_sequence'
    )
    
    # Build a map of lead_id -> list of contacts (sorted by created_at)
    contacts_by_lead = {}
    for contact in all_contacts:
        if contact.lead_id:
            if contact.lead_id not in contacts_by_lead:
                contacts_by_lead[contact.lead_id] = []
            contacts_by_lead[contact.lead_id].append(contact)
    
    for email_data in all_email_history_list:
        email = email_data['email']
        sequence = None
        
        # Method 1: Find which sequence step uses this template, then verify the lead was in that sequence
        if email.lead_id and email.email_template and email.sent_at:
            # Get all sequence steps that use this template
            template_steps = email.email_template.sequence_steps.filter(
                sequence__campaign=campaign
            ).select_related('sequence', 'sequence__parent_sequence').all()
            
            if template_steps.exists():
                # Check each sequence step to see if the lead was in that sequence when email was sent
                for step in template_steps:
                    step_sequence = step.sequence
                    
                    # For regular sequences, check if contact's sequence matches
                    if not step_sequence.is_sub_sequence:
                        contact_match = CampaignContact.objects.filter(
                            campaign=campaign,
                            lead_id=email.lead_id,
                            sequence=step_sequence  # Must match exactly
                        ).first()
                        
                        if contact_match:
                            # Verify timing - email should be sent after contact was created
                            if not contact_match.created_at or email.sent_at >= contact_match.created_at:
                                # This is the correct sequence - use it directly
                                sequence = step_sequence
                                break
                    else:
                        # For sub-sequences, check sub_sequence field
                        # CRITICAL: Find the contact that has THIS sub_sequence set AND was active when email was sent
                        # Use replied_at (when sub-sequence started) to determine which contact was active
                        contact_match = CampaignContact.objects.filter(
                            campaign=campaign,
                            lead_id=email.lead_id,
                            sub_sequence=step_sequence  # Must match exactly - this is the sub-sequence
                        ).select_related('sub_sequence__parent_sequence', 'sequence').order_by('-replied_at', '-created_at').first()
                        
                        if contact_match:
                            # Verify timing - email should be sent AFTER sub-sequence started (replied_at)
                            # and BEFORE sub-sequence ended (if completed)
                            timing_valid = False
                            if contact_match.replied_at:
                                # Email should be sent after reply (when sub-sequence started)
                                if email.sent_at >= contact_match.replied_at:
                                    # Check if sub-sequence is not completed, or email was sent before completion
                                    if not contact_match.sub_sequence_completed or (contact_match.sub_sequence_last_sent_at and email.sent_at <= contact_match.sub_sequence_last_sent_at):
                                        timing_valid = True
                            elif contact_match.created_at:
                                # Fallback to created_at if replied_at not set
                                timing_valid = email.sent_at >= contact_match.created_at
                            else:
                                # If no timestamp, assume valid (shouldn't happen but handle gracefully)
                                timing_valid = True
                            
                            if timing_valid:
                                # Sub-sequence email - use parent for grouping
                                # CRITICAL: Always reload sub_sequence to get fresh parent_sequence from DB
                                try:
                                    sub_seq_fresh = EmailSequence.objects.select_related('parent_sequence').get(id=step_sequence.id)
                                    # Use parent_sequence from database (this is the CORRECT parent)
                                    if sub_seq_fresh.parent_sequence:
                                        sequence = sub_seq_fresh.parent_sequence
                                        logger.info(
                                            f"Sub-sequence email '{email.subject}' for {email.recipient_email} (sent: {email.sent_at}): "
                                            f"Found parent_sequence {sequence.id} ({sequence.name}) from sub_sequence {sub_seq_fresh.id} ({sub_seq_fresh.name}). "
                                            f"Contact ID: {contact_match.id}, Contact.sequence: {contact_match.sequence_id if contact_match.sequence else 'None'}, "
                                            f"Contact.replied_at: {contact_match.replied_at}"
                                        )
                                    else:
                                        # If parent_sequence is not set, log error and use contact.sequence as fallback
                                        logger.error(
                                            f"Sub-sequence {sub_seq_fresh.id} ({sub_seq_fresh.name}) has no parent_sequence! "
                                            f"Email: {email.subject}, Contact: {contact_match.lead.email}, "
                                            f"Contact.sequence: {contact_match.sequence_id if contact_match.sequence else 'None'}"
                                        )
                                        if contact_match.sequence:
                                            sequence = contact_match.sequence
                                        else:
                                            sequence = step_sequence
                                except EmailSequence.DoesNotExist:
                                    # Fallback to contact_match.sequence if sub_sequence not found
                                    logger.error(f"Sub-sequence {step_sequence.id} not found in database for email {email.id}")
                                    if contact_match.sequence:
                                        sequence = contact_match.sequence
                                    else:
                                        sequence = step_sequence
                                break
        
        # Method 2: If still not found, check contacts directly (for emails without sent_at)
        if not sequence and email.lead_id and email.email_template and email.lead_id in contacts_by_lead:
            contacts = contacts_by_lead[email.lead_id]
            
            # Get all sequence steps for this template
            template_steps = email.email_template.sequence_steps.filter(
                sequence__campaign=campaign
            ).select_related('sequence', 'sequence__parent_sequence').all()
            
            # PRIORITY 1: Check sub-sequences first (most specific match)
            # CRITICAL: If same template is used in multiple sub-sequences, find which contact was active
            # Find ALL contacts that have sub_sequences matching the template
            sub_sequence_contacts = []
            for contact in contacts:
                if contact.sub_sequence:
                    # Check if template step matches this contact's sub_sequence
                    matching_step = template_steps.filter(sequence=contact.sub_sequence).first()
                    if matching_step:
                        sub_sequence_contacts.append((contact, matching_step.sequence))
            
            # If multiple contacts found, pick the one that was most recently active (most recent replied_at)
            if sub_sequence_contacts:
                # Sort by replied_at (most recent first) to find the active contact when email was sent
                sub_sequence_contacts.sort(key=lambda x: x[0].replied_at or x[0].created_at, reverse=True)
                matching_contact, sub_seq_obj = sub_sequence_contacts[0]  # Get most recent
                
                # CRITICAL: Reload sub_sequence to get fresh parent_sequence from DB
                try:
                    sub_seq_fresh = EmailSequence.objects.select_related('parent_sequence').get(id=sub_seq_obj.id)
                    if sub_seq_fresh.parent_sequence:
                        # Use parent_sequence from database (this is the CORRECT parent)
                        sequence = sub_seq_fresh.parent_sequence
                        logger.info(
                            f"Sub-sequence email '{email.subject}' for {email.recipient_email}: "
                            f"Found parent_sequence {sequence.id} ({sequence.name}) "
                            f"from contact's sub_sequence {sub_seq_fresh.id} ({sub_seq_fresh.name}). "
                            f"Contact ID: {matching_contact.id}, Contact.sequence: {matching_contact.sequence_id if matching_contact.sequence else 'None'}, "
                            f"Contact.replied_at: {matching_contact.replied_at}"
                        )
                    elif matching_contact.sequence:
                        sequence = matching_contact.sequence
                        logger.warning(
                            f"Sub-sequence {sub_seq_fresh.id} has no parent_sequence in DB, "
                            f"using contact.sequence {matching_contact.sequence.id} for email {email.id}"
                        )
                except EmailSequence.DoesNotExist:
                    logger.error(f"Sub-sequence {sub_seq_obj.id} not found in database")
                    if matching_contact.sequence:
                        sequence = matching_contact.sequence
            
            # PRIORITY 2: If no sub-sequence match found, check main sequences
            if not sequence:
                for contact in contacts:
                    if contact.sequence:
                        matching_main_seq_step = template_steps.filter(sequence=contact.sequence).first()
                        if matching_main_seq_step:
                            sequence = contact.sequence
                            break
        
        # Method 3: Last resort - if only one sequence uses this template, use it
        if not sequence and email.email_template:
            template_steps = email.email_template.sequence_steps.filter(
                sequence__campaign=campaign
            ).select_related('sequence', 'sequence__parent_sequence').all()
            
            if template_steps.count() == 1:
                seq = template_steps.first().sequence
                if seq.is_sub_sequence and seq.parent_sequence:
                    sequence = seq.parent_sequence
                else:
                    sequence = seq
        
        seq_key = sequence.id if sequence else 'no_sequence'
        if seq_key not in emails_by_sequence:
            emails_by_sequence[seq_key] = {
                'sequence': sequence,
                'sequence_name': sequence.name if sequence else 'No Sequence',
                'emails': []
            }
        emails_by_sequence[seq_key]['emails'].append(email_data)
    
    # Organize pending emails by sequence
    # Ensure sub-sequence emails are grouped under their parent sequence
    pending_by_sequence = {}
    for email_data in pending_emails:
        sequence = email_data.get('sequence')
        is_sub_seq = email_data.get('is_sub_sequence', False)
        
        # For sub-sequence emails, the sequence should already be the parent sequence
        # (we set it to parent_sequence when creating the email_data)
        # But double-check to ensure it's not a sub-sequence itself
        if is_sub_seq and sequence:
            # Verify the sequence is not a sub-sequence (it should be the parent)
            if hasattr(sequence, 'is_sub_sequence') and sequence.is_sub_sequence:
                # This shouldn't happen, but if it does, get the parent
                try:
                    seq_obj = EmailSequence.objects.select_related('parent_sequence').get(id=sequence.id)
                    if seq_obj.is_sub_sequence and seq_obj.parent_sequence:
                        sequence = seq_obj.parent_sequence
                except EmailSequence.DoesNotExist:
                    # If the sequence cannot be reloaded, skip regrouping and keep using
                    # the original sequence for organizing pending emails.
                    pass
        
        # For regular sequence emails (is_sub_sequence=False), use the sequence directly
        # No modifications needed - it should already be the correct sequence (seq1, seq2, etc.)
        # The sequence comes from contact.sequence which is the correct sequence for that contact
        
        seq_key = sequence.id if sequence else 'no_sequence'
        if seq_key not in pending_by_sequence:
            pending_by_sequence[seq_key] = {
                'sequence': sequence,
                'sequence_name': sequence.name if sequence else 'No Sequence',
                'emails': []
            }
        pending_by_sequence[seq_key]['emails'].append(email_data)
    
    # Organize upcoming emails by sequence
    # Ensure sub-sequence emails are grouped under their parent sequence
    upcoming_by_sequence = {}
    for email_data in upcoming_sequence_sends:
        sequence = email_data.get('sequence')
        # If sequence is a sub-sequence, get its parent sequence for grouping
        if sequence and sequence.is_sub_sequence:
            if hasattr(sequence, 'parent_sequence') and sequence.parent_sequence:
                sequence = sequence.parent_sequence
            else:
                # Reload with parent_sequence if not loaded
                try:
                    sequence = EmailSequence.objects.select_related('parent_sequence').get(id=sequence.id)
                    if sequence.is_sub_sequence and sequence.parent_sequence:
                        sequence = sequence.parent_sequence
                except EmailSequence.DoesNotExist:
                    # If the sequence was deleted or is otherwise missing, continue with the existing sequence.
                    logger.warning(
                        "EmailSequence with id %s does not exist while grouping upcoming emails.",
                        getattr(sequence, "id", None),
                    )
        
        seq_key = sequence.id if sequence else 'no_sequence'
        if seq_key not in upcoming_by_sequence:
            upcoming_by_sequence[seq_key] = {
                'sequence': sequence,
                'sequence_name': sequence.name if sequence else 'No Sequence',
                'emails': []
            }
        upcoming_by_sequence[seq_key]['emails'].append(email_data)
    
    context = {
        'campaign': campaign,
        'all_email_history': all_email_history_list,  # Now includes replied/sequence info
        'emails_by_sequence': emails_by_sequence,  # Emails organized by sequence
        'sequence_emails': recent_sequence_emails_list,  # Now includes replied/sequence info
        'pending_emails': pending_emails,
        'pending_by_sequence': pending_by_sequence,  # Pending emails organized by sequence
        'upcoming_sequence_sends': upcoming_sequence_sends,
        'upcoming_by_sequence': upcoming_by_sequence,  # Upcoming emails organized by sequence
        'replied_contacts': replied_contacts,  # For backward compatibility
        'all_replies': all_replies,  # All reply history from Reply model
        'replies_by_sequence': replies_by_sequence,  # Replies organized by sequence
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

            # Calculate reference time for delay calculation
            if contact.current_step == 0:
                # First step: use contact creation time or started_at as reference
                # This ensures delays are calculated from when contact was added, not from current time
                # If started_at is set, use it; otherwise use created_at
                reference_time = contact.started_at if contact.started_at else contact.created_at
            else:
                # Subsequent steps: use last_sent_at if available and recent, otherwise use now
                if contact.last_sent_at and contact.last_sent_at <= now:
                    # Check if last_sent_at is too old (more than 24 hours ago) - might be stale data
                    time_since_last = now - contact.last_sent_at
                    if time_since_last > timedelta(hours=24):
                        # last_sent_at is too old, use current time instead
                        reference_time = now
                    else:
                        # last_sent_at exists and is recent, use it
                        reference_time = contact.last_sent_at
                else:
                    # No last_sent_at or it's in the future (data issue), use current time
                    reference_time = now

            next_send_time = reference_time + timedelta(
                days=next_step.delay_days,
                hours=next_step.delay_hours,
                minutes=next_step.delay_minutes,
            )
            
            # Final safeguard: if next_send_time is in the past (for step 0, this means delay already passed)
            # For step 0, if send_time is in the past, it's ready to send (don't recalculate)
            # For subsequent steps, if send_time is way in the past, recalculate from now
            if contact.current_step == 0:
                # For step 0, if send_time is in the past, it means the delay has passed - ready to send
                # Don't recalculate, just let it be ready
                pass
            elif next_send_time < now - timedelta(hours=1):
                # For subsequent steps, if send_time is way in the past, recalculate from now
                reference_time = now
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


@login_required
def debug_sequence_times(request, campaign_id):
    """Debug view to show actual database time values for sequences and sub-sequences"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    now = timezone.now()
    
    contacts = CampaignContact.objects.filter(
        campaign=campaign
    ).select_related('lead', 'sequence', 'sub_sequence').order_by('-created_at')[:50]
    
    debug_data = []
    for contact in contacts:
        # Get all emails sent to this contact in this campaign
        sent_emails = EmailSendHistory.objects.filter(
            campaign=campaign,
            lead=contact.lead
        ).select_related('email_template').order_by('-sent_at', '-created_at')
        
        email_history = []
        for email in sent_emails:
            email_history.append({
                'subject': email.subject,
                'template_name': email.email_template.name if email.email_template else None,
                'status': email.status,
                'sent_at': email.sent_at.isoformat() if email.sent_at else None,
                'created_at': email.created_at.isoformat(),
                'delivered_at': email.delivered_at.isoformat() if email.delivered_at else None,
                'opened_at': email.opened_at.isoformat() if email.opened_at else None,
            })
        
        debug_data.append({
            'lead_email': contact.lead.email,
            'current_step': contact.current_step,
            'sub_sequence_step': contact.sub_sequence_step,
            'sequence_name': contact.sequence.name if contact.sequence else None,
            'sub_sequence_name': contact.sub_sequence.name if contact.sub_sequence else None,
            'last_sent_at': contact.last_sent_at.isoformat() if contact.last_sent_at else None,
            'sub_sequence_last_sent_at': contact.sub_sequence_last_sent_at.isoformat() if contact.sub_sequence_last_sent_at else None,
            'started_at': contact.started_at.isoformat() if contact.started_at else None,
            'replied_at': contact.replied_at.isoformat() if contact.replied_at else None,
            'created_at': contact.created_at.isoformat(),
            'updated_at': contact.updated_at.isoformat(),
            'completed': contact.completed,
            'replied': contact.replied,
            'time_since_last_sent': str(now - contact.last_sent_at) if contact.last_sent_at else None,
            'time_since_sub_last_sent': str(now - contact.sub_sequence_last_sent_at) if contact.sub_sequence_last_sent_at else None,
            'sent_emails': email_history,  # All emails actually sent to this contact
            'total_emails_sent': len(email_history),
        })
    
    return JsonResponse({
        'success': True,
        'campaign_id': campaign.id,
        'campaign_name': campaign.name,
        'current_time': now.isoformat(),
        'contacts': debug_data,
    })
