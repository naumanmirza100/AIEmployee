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
        # Get or create contact
        contact = CampaignContact.objects.filter(
            campaign=campaign,
            lead=lead
        ).first()
        
        if not contact:
            contact = CampaignContact.objects.create(
                campaign=campaign,
                lead=lead,
                current_step=0
            )
        
        # Use current time if no date provided
        if not reply_date:
            reply_date = timezone.now()
        
        # Analyze reply with AI if content is provided
        interest_level = 'not_analyzed'
        analysis = ''
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
        
        # Determine which sequence this reply is for
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
            
            if triggering_email and triggering_email.email_template:
                sequence_steps = triggering_email.email_template.sequence_steps.all()
                if sequence_steps.exists():
                    seq_step = sequence_steps.first()
                    reply_sequence = seq_step.sequence
                    if reply_sequence and reply_sequence.is_sub_sequence:
                        is_sub_sequence_reply = True
                        reply_sub_sequence = reply_sequence
                        reply_sequence = reply_sequence.parent_sequence
                else:
                    reply_sequence = contact.sequence
                    if contact.sub_sequence:
                        if triggering_email.email_template.sequence_steps.exists():
                            seq_step = triggering_email.email_template.sequence_steps.first()
                            if seq_step and seq_step.sequence and seq_step.sequence.is_sub_sequence:
                                is_sub_sequence_reply = True
                                reply_sub_sequence = contact.sub_sequence
            else:
                reply_sequence = contact.sequence
                if contact.sub_sequence and all_sent_emails.exists():
                    most_recent = all_sent_emails.first()
                    if most_recent and most_recent.email_template and most_recent.email_template.sequence_steps.exists():
                        seq_step = most_recent.email_template.sequence_steps.first()
                        if seq_step and seq_step.sequence and seq_step.sequence.is_sub_sequence:
                            if most_recent.sent_at and (timezone.now() - most_recent.sent_at) < timedelta(hours=48):
                                is_sub_sequence_reply = True
                                reply_sub_sequence = contact.sub_sequence
        except Exception as e:
            logger.warning(f'Could not determine reply sequence: {str(e)}')
            reply_sequence = contact.sequence
            if contact.sub_sequence:
                is_sub_sequence_reply = True
                reply_sub_sequence = contact.sub_sequence
        
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
            logger.info(f"Created Reply record #{reply_record.id} for {lead.email}")
        except Exception as e:
            logger.warning(f'Could not create Reply record: {str(e)}')
        
        # Find sub-sequence for main sequence replies
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

