"""
Service function to process email replies directly (without HTTP request)
Used by sync_inbox command to avoid middleware issues
"""
from django.utils import timezone
from datetime import timedelta
from marketing_agent.models import Campaign, Lead, CampaignContact, EmailSequence, Reply, EmailSendHistory
from marketing_agent.utils.reply_analyzer import ReplyAnalyzer
import logging
import re

logger = logging.getLogger(__name__)


def process_reply_directly(campaign, lead, reply_subject, reply_content, reply_date=None):
    """
    Process an email reply directly (without HTTP request)
    This is the core logic extracted from mark_contact_replied view
    
    Args:
        campaign: Campaign instance
        lead: Lead instance
        reply_subject: Reply email subject
        reply_content: Reply email content
        reply_date: Reply date (optional, defaults to now)
    
    Returns:
        dict: {'success': bool, 'message': str, 'error': str (if failed)}
    """
    try:
        # Get all contacts for this lead in campaign (there can be multiple)
        all_contacts = list(CampaignContact.objects.filter(
            campaign=campaign,
            lead=lead
        ).select_related('sequence', 'sub_sequence', 'sub_sequence__parent_sequence'))
        
        contact = all_contacts[0] if all_contacts else None
        if not contact:
            contact = CampaignContact.objects.create(
                campaign=campaign,
                lead=lead,
                current_step=0
            )
            all_contacts = [contact]
        
        # Use current time if no date provided
        if not reply_date:
            reply_date = timezone.now()
        
        # Determine which sequence this reply is for FIRST
        # This is critical: we need to know if it's a sub-sequence reply BEFORE analyzing
        is_sub_sequence_reply = False
        reply_sequence = None
        reply_sub_sequence = None
        triggering_email = None
        
        try:
            # Get reply subject for matching
            reply_subject_clean = re.sub(r'^(re:|fw:|fwd:)\s*', '', reply_subject, flags=re.IGNORECASE).strip() if reply_subject else ''
            
            # Get all emails sent to this lead
            all_sent_emails = EmailSendHistory.objects.filter(
                campaign=campaign,
                lead=lead,
                sent_at__isnull=False
            ).order_by('-sent_at').select_related('email_template')
            
            # Try to match reply subject with sent email subjects
            triggering_email = None
            best_match_score = 0
            
            for email in all_sent_emails:
                if email.email_template and email.email_template.subject:
                    email_subject = email.email_template.subject.strip()
                    if reply_subject_clean:
                        if reply_subject_clean.lower() in email_subject.lower() or email_subject.lower() in reply_subject_clean.lower():
                            match_score = len(email_subject) if email_subject.lower() in reply_subject_clean.lower() else len(reply_subject_clean)
                            if email.sent_at and (timezone.now() - email.sent_at) < timedelta(days=7):
                                match_score += 10
                            if match_score > best_match_score:
                                best_match_score = match_score
                                triggering_email = email
            
            # If no subject match, use most recent email
            if not triggering_email:
                most_recent_email = all_sent_emails.first()
                if most_recent_email:
                    is_recent = most_recent_email.sent_at and (timezone.now() - most_recent_email.sent_at) < timedelta(hours=48)
                    if is_recent:
                        triggering_email = most_recent_email
                    else:
                        # Look for main sequence emails
                        main_seq_emails = [
                            e for e in all_sent_emails[:10]
                            if e.email_template and e.email_template.sequence_steps.exists() and
                            not e.email_template.sequence_steps.first().sequence.is_sub_sequence and
                            e.sent_at and (timezone.now() - e.sent_at) < timedelta(days=14)
                        ]
                        if main_seq_emails:
                            triggering_email = main_seq_emails[0]
                        else:
                            triggering_email = most_recent_email
            
            # Resolve which contact "owns" this reply. Check SUB-SEQUENCE first: if the email was sent after
            # a contact's reply and template is in their sub_sequence, do not analyze (sub-sequence reply).
            # Only then check main sequence so we don't wrongly analyze sub-sequence replies when multiple contacts exist.
            email_sent_at = getattr(triggering_email, 'sent_at', None) if triggering_email else None
            if triggering_email and triggering_email.email_template and email_sent_at:
                sequence_steps = list(triggering_email.email_template.sequence_steps.select_related('sequence', 'sequence__parent_sequence').all())
                main_seq_ids = {s.sequence_id for s in sequence_steps if not s.sequence.is_sub_sequence}
                sub_seq_ids = {s.sequence_id for s in sequence_steps if s.sequence.is_sub_sequence}
                resolved_contact = None
                # First: sub-sequence reply (email sent after they replied, template in sub_sequence) -> do not analyze
                if sub_seq_ids:
                    for c in all_contacts:
                        if c.sub_sequence_id and c.sub_sequence_id in sub_seq_ids and c.replied_at and email_sent_at >= c.replied_at:
                            resolved_contact = c
                            is_sub_sequence_reply = True
                            reply_sub_sequence = next((s.sequence for s in sequence_steps if s.sequence_id == c.sub_sequence_id), None)
                            if reply_sub_sequence:
                                reply_sequence = getattr(reply_sub_sequence, 'parent_sequence', None) or reply_sub_sequence
                                logger.info(f"Detected sub-sequence reply (resolved contact): {lead.email} - email sent after reply - sub '{reply_sub_sequence.name}'")
                            break
                # Only if not sub-sequence: main sequence (template in main sequence, send before their reply or first reply)
                if resolved_contact is None:
                    for c in all_contacts:
                        if c.sequence_id and c.sequence_id in main_seq_ids:
                            if c.replied_at is None or email_sent_at < c.replied_at:
                                resolved_contact = c
                                is_sub_sequence_reply = False
                                reply_sequence = next((s.sequence for s in sequence_steps if s.sequence_id == c.sequence_id), None)
                                if reply_sequence:
                                    logger.info(f"Detected main sequence reply (resolved contact): {lead.email} - email sent before reply - sequence '{reply_sequence.name}'")
                                break
                if resolved_contact is not None:
                    contact = resolved_contact
                elif sequence_steps:
                    # Fallback: use first contact and previous timing logic
                    contact_replied_at = getattr(contact, 'replied_at', None)
                    if contact_replied_at and email_sent_at and email_sent_at >= contact_replied_at and getattr(contact, 'sub_sequence_id', None):
                        for step in sequence_steps:
                            if step.sequence_id == contact.sub_sequence_id:
                                is_sub_sequence_reply = True
                                reply_sub_sequence = step.sequence
                                reply_sequence = getattr(step.sequence, 'parent_sequence', None) or step.sequence
                                break
                    if not is_sub_sequence_reply:
                        for step in sequence_steps:
                            if not step.sequence.is_sub_sequence:
                                reply_sequence = step.sequence
                                break
                        if reply_sequence is None and sequence_steps:
                            step = sequence_steps[0]
                            reply_sequence = step.sequence.parent_sequence if step.sequence.is_sub_sequence else step.sequence
                            if step.sequence.is_sub_sequence and contact_replied_at and email_sent_at >= contact_replied_at:
                                reply_sub_sequence = step.sequence
                                is_sub_sequence_reply = True
            elif triggering_email and triggering_email.email_template:
                sequence_steps = list(triggering_email.email_template.sequence_steps.select_related('sequence', 'sequence__parent_sequence').all())
                if sequence_steps:
                    for step in sequence_steps:
                        if not step.sequence.is_sub_sequence:
                            reply_sequence = step.sequence
                            break
                    if reply_sequence is None and sequence_steps:
                        step = sequence_steps[0]
                        reply_sequence = step.sequence.parent_sequence if step.sequence.is_sub_sequence else step.sequence
                else:
                    reply_sequence = contact.sequence
            else:
                # No triggering email found - check most recent email
                reply_sequence = contact.sequence
                if all_sent_emails.exists():
                    most_recent = all_sent_emails.first()
                    if most_recent and most_recent.email_template:
                        sequence_steps = most_recent.email_template.sequence_steps.all()
                        if sequence_steps.exists():
                            seq_step = sequence_steps.first()
                            if seq_step and seq_step.sequence and seq_step.sequence.is_sub_sequence:
                                # Most recent email is from sub-sequence - this is a sub-sequence reply
                                is_sub_sequence_reply = True
                                reply_sub_sequence = seq_step.sequence
                                reply_sequence = seq_step.sequence.parent_sequence
                                logger.info(f"Detected sub-sequence reply (fallback): {lead.email} - most recent email is from sub-sequence '{reply_sub_sequence.name}'")
        except Exception as e:
            logger.warning(f'Could not determine reply sequence: {str(e)}')
            reply_sequence = contact.sequence
            # Only assume sub-sequence reply if they had already replied before (context)
            if contact.sub_sequence and getattr(contact, 'replied_at', None):
                is_sub_sequence_reply = True
                reply_sub_sequence = contact.sub_sequence
                logger.warning(f'Using fallback: marking as sub-sequence reply for {lead.email}')
        
        # IMPORTANT: Only analyze replies to MAIN sequence emails
        # Sub-sequence replies should NOT be analyzed (no further sub-sequences exist)
        interest_level = 'not_analyzed'
        analysis = ''
        
        if not is_sub_sequence_reply:
            # This is a reply to MAIN sequence email - analyze it
            if reply_content or reply_subject:
                try:
                    analyzer = ReplyAnalyzer()
                    analysis_result = analyzer.analyze_reply(
                        reply_subject=reply_subject,
                        reply_content=reply_content,
                        campaign_name=campaign.name
                    )
                    interest_level = analysis_result.get('interest_level', 'neutral')
                    analysis = analysis_result.get('analysis', '')
                    logger.info(f"AI analyzed reply for {lead.email}: {interest_level}")
                except Exception as e:
                    logger.error(f"Error analyzing reply with AI: {str(e)}")
                    interest_level = 'not_analyzed'
                    analysis = f'AI analysis failed: {str(e)}'
        else:
            # This is a reply to SUB-SEQUENCE email - just record it, don't analyze
            logger.info(f"Reply to sub-sequence email from {lead.email} - skipping AI analysis (no further sub-sequences)")
            interest_level = 'not_analyzed'
            analysis = 'Reply to sub-sequence email (not analyzed - no further sub-sequences)'
        
        # Create Reply record
        try:
            reply_record = Reply.objects.create(
                contact=contact,
                campaign=campaign,
                lead=lead,
                sequence=reply_sequence,
                sub_sequence=reply_sub_sequence,
                reply_subject=reply_subject,
                reply_content=reply_content,
                interest_level=interest_level,
                analysis=analysis,
                triggering_email=triggering_email,
                replied_at=reply_date
            )
            logger.info(f"Created Reply record #{reply_record.id} for {lead.email} - {'Sub-sequence reply (not analyzed)' if is_sub_sequence_reply else 'Main sequence reply (analyzed)'}")
        except Exception as e:
            logger.warning(f'Could not create Reply record: {str(e)}')
        
        # Find sub-sequence for main sequence replies ONLY
        # Sub-sequence replies should NOT trigger new sub-sequences
        sub_sequence = None
        if not is_sub_sequence_reply and contact.sequence:
            target_interest = interest_level if interest_level and interest_level != 'not_analyzed' else 'neutral'
            
            interest_mapping = {
                'positive': 'positive',
                'negative': 'negative',
                'neutral': 'neutral',
                'requested_info': 'requested_info',
                'objection': 'objection',
                'unsubscribe': 'unsubscribe',
                'not_analyzed': 'any'
            }
            target_interest = interest_mapping.get(target_interest, target_interest if target_interest in ['positive', 'negative', 'neutral', 'requested_info', 'objection', 'unsubscribe'] else 'any')
            
            sub_sequences = EmailSequence.objects.filter(
                parent_sequence=contact.sequence,
                is_sub_sequence=True,
                is_active=True,
                interest_level=target_interest
            )
            
            if not sub_sequences.exists() and target_interest != 'any':
                sub_sequences = EmailSequence.objects.filter(
                    parent_sequence=contact.sequence,
                    is_sub_sequence=True,
                    is_active=True,
                    interest_level='any'
                )
            
            if sub_sequences.exists():
                sub_sequence = sub_sequences.first()
                logger.info(f"Found sub-sequence '{sub_sequence.name}' for contact {lead.email}")
        
        # Mark as replied
        was_already_in_sub_sequence = bool(contact.sub_sequence)
        existing_sub_sequence_id = contact.sub_sequence.id if contact.sub_sequence else None
        
        contact.mark_replied(
            reply_subject=reply_subject,
            reply_content=reply_content,
            reply_at=reply_date,  # Pass the reply date so delay calculations use correct time
            interest_level=interest_level,
            analysis=analysis,
            sub_sequence=sub_sequence if not is_sub_sequence_reply else None
        )
        
        # Build message
        if is_sub_sequence_reply:
            message = f'Reply received from {lead.email} for sub-sequence email. Reply recorded.'
        else:
            message = f'Contact {lead.email} marked as replied. Main sequence stopped.'
            if sub_sequence:
                if was_already_in_sub_sequence and existing_sub_sequence_id == sub_sequence.id:
                    message += f' Sub-sequence "{sub_sequence.name}" restarted.'
                else:
                    message += f' Sub-sequence "{sub_sequence.name}" started.'
        
        return {
            'success': True,
            'message': message,
            'contact_id': contact.id,
            'interest_level': interest_level,
            'analysis': analysis,
            'sub_sequence_started': sub_sequence is not None,
            'sub_sequence_name': sub_sequence.name if sub_sequence else None
        }
        
    except Exception as e:
        logger.error(f"Error processing reply: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }

