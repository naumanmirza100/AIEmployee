"""
Service function to process email replies directly (without HTTP request)
Used by sync_inbox command to avoid middleware issues
"""
from django.utils import timezone
from datetime import timedelta, datetime
from marketing_agent.models import Campaign, Lead, CampaignContact, EmailSequence, Reply, EmailSendHistory
from marketing_agent.utils.reply_analyzer import ReplyAnalyzer
import logging
import re

logger = logging.getLogger(__name__)

# Patterns for "On <date> ... wrote:" quoted timestamp in reply body (Gmail, Outlook, etc.)
_QUOTED_DATE_PATTERNS = [
    # "On Thu, Feb 5, 2026 at 3:33 AM" (month first: month, day, year, hour, min, AM/PM)
    re.compile(r'\bOn\s+[\w,]+\s+([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)?', re.IGNORECASE),
    # "On Thu, 5 Feb 2026 at 04:38" (day first with optional weekday - very common)
    re.compile(r'\bOn\s+[\w,]+\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2})\b', re.IGNORECASE),
    # "On 5 Feb 2026 at 03:38" (day first, no weekday)
    re.compile(r'\bOn\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2})\b', re.IGNORECASE),
    # "Feb 5, 2026, 04:28 AM" (month first, no "On")
    re.compile(r'\b([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4}),?\s+(\d{1,2}):(\d{2})\s*(AM|PM)?', re.IGNORECASE),
]

_MONTHS = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}


def _parse_quoted_date_from_reply(reply_content):
    """
    Try to extract the first quoted email date from reply body (e.g. "On Thu, Feb 5, 2026 at 3:33 AM").
    Returns timezone-aware datetime or None. Uses server timezone for interpreted time.
    Note: the quoted text is often in the recipient's local time, so this can be wrong if server TZ != recipient TZ.
    Prefer replying on replied_at (DB timestamp) when disambiguating multiple candidates.
    """
    if not reply_content or not isinstance(reply_content, str):
        return None
    text = reply_content.strip()
    for pat in _QUOTED_DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        g = m.groups()
        try:
            if len(g) == 6 and g[5]:  # month name, day, year, hour, min, AM/PM
                month = _MONTHS.get(g[0].lower()[:3])
                day, year = int(g[1]), int(g[2])
                hour, minu = int(g[3]), int(g[4])
                if g[5].upper() == 'PM' and hour != 12:
                    hour += 12
                elif g[5].upper() == 'AM' and hour == 12:
                    hour = 0
                if month:
                    dt = datetime(year, month, day, hour, minu, 0, 0)
                    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
            elif len(g) >= 5:  # day, month name, year, hour, min
                day = int(g[0])
                month = _MONTHS.get(g[1].lower()[:3])
                year = int(g[2])
                hour, minu = int(g[3]), int(g[4])
                if month:
                    dt = datetime(year, month, day, hour, minu, 0, 0)
                    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        except (ValueError, TypeError, IndexError):
            continue
    return None


def _find_triggering_email_by_quoted_date(all_sent_emails, quoted_dt, max_diff_seconds=48 * 3600):
    """
    Return the sent email that the reply is replying to.
    Prefer the email with sent_at at or just before quoted_dt (the one they quoted), not a later email.
    """
    if not quoted_dt or not all_sent_emails:
        return None
    if timezone.is_naive(quoted_dt):
        quoted_dt = timezone.make_aware(quoted_dt)
    # Prefer: sent_at <= quoted_dt (email was sent before they replied), closest to quoted_dt
    best_before = None
    best_diff_before = float('inf')
    # Fallback: any email within window if no "before" candidate (e.g. timezone skew)
    best_any = None
    best_diff_any = float('inf')
    for email in all_sent_emails:
        sent_at = email.sent_at
        if not sent_at:
            continue
        diff = (quoted_dt - sent_at).total_seconds()  # positive if sent_at is before quoted_dt
        abs_diff = abs(diff)
        if abs_diff > max_diff_seconds:
            continue
        if diff >= -60:  # sent_at at or before quoted_dt (allow 1 min skew)
            if abs_diff < best_diff_before:
                best_diff_before = abs_diff
                best_before = email
        if abs_diff < best_diff_any:
            best_diff_any = abs_diff
            best_any = email
    return best_before if best_before is not None else best_any


def _pick_best_candidate_by_time(candidates, replied_at, quoted_dt):
    """
    When we have multiple candidate emails (e.g. same subject), pick the one they replied to.
    Prefer timezone-safe rule: of emails sent before replied_at, pick the most recent (both in DB/UTC).
    Fall back to quoted date only if replied_at is missing (quoted date can be wrong due to timezone).
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Timezone-safe: pick email sent most recently before they replied (replied_at and sent_at are both stored, same TZ)
    if replied_at:
        before_reply = [e for e in candidates if e.sent_at and e.sent_at <= replied_at]
        if before_reply:
            return max(before_reply, key=lambda e: e.sent_at)
    # Fallback: quoted date (can be wrong if server TZ != recipient TZ - quoted text is often in recipient local time)
    if quoted_dt:
        return _find_triggering_email_by_quoted_date(candidates, quoted_dt, max_diff_seconds=24 * 3600)
    return candidates[0]  # most recent (list order is -sent_at)


def find_triggering_email(campaign, lead, reply_subject, reply_content, replied_at=None):
    """
    Determine which sent email (EmailSendHistory) this reply was in response to.
    Prefers: 1) subject match (single or disambiguate by replied_at / quoted date), 2) quoted date over all, 3) most recent.
    replied_at: when the reply was received (use for disambiguation when multiple same subject - timezone-safe).
    Returns EmailSendHistory or None.
    """
    reply_subject_clean = re.sub(r'^(re:|fw:|fwd:)\s*', '', (reply_subject or ''), flags=re.IGNORECASE).strip()
    all_sent_emails = list(EmailSendHistory.objects.filter(
        campaign=campaign,
        lead=lead,
        sent_at__isnull=False
    ).order_by('-sent_at').select_related('email_template'))
    if not all_sent_emails:
        return None
    triggering_email = None
    quoted_dt = _parse_quoted_date_from_reply(reply_content) if reply_content else None

    # 1) Subject match (most reliable). Multiple emails can have the same subject; disambiguate by replied_at (safe) or quoted date.
    if reply_subject_clean:
        exact_matches = []
        best_substring_score = 0
        best_substring_matches = []
        for email in all_sent_emails:
            email_subject = (email.subject or (email.email_template.subject if email.email_template else None) or '').strip()
            if not email_subject or '{{' in email_subject:
                if email.email_template and email.email_template.subject:
                    email_subject = email.email_template.subject.strip()
            if not email_subject:
                continue
            if reply_subject_clean.strip().lower() == email_subject.strip().lower():
                exact_matches.append(email)
            elif reply_subject_clean.lower() in email_subject.lower() or email_subject.lower() in reply_subject_clean.lower():
                match_score = len(email_subject) if email_subject.lower() in reply_subject_clean.lower() else len(reply_subject_clean)
                if email.sent_at and (timezone.now() - email.sent_at) < timedelta(days=7):
                    match_score += 10
                if match_score > best_substring_score:
                    best_substring_score = match_score
                    best_substring_matches = [email]
                elif match_score == best_substring_score:
                    best_substring_matches.append(email)
        candidates = exact_matches if exact_matches else best_substring_matches
        if len(candidates) == 1:
            triggering_email = candidates[0]
        elif len(candidates) > 1:
            triggering_email = _pick_best_candidate_by_time(candidates, replied_at, quoted_dt)
            if not triggering_email:
                triggering_email = candidates[0]
    # 2) No subject match: try quoted date over all sent emails (still TZ-sensitive; prefer when replied_at not available)
    if not triggering_email and quoted_dt:
        by_date = _find_triggering_email_by_quoted_date(all_sent_emails, quoted_dt, max_diff_seconds=24 * 3600)
        if by_date:
            triggering_email = by_date
    # 3) Most recent
    if not triggering_email:
        most_recent_email = all_sent_emails[0]
        is_recent = most_recent_email.sent_at and (timezone.now() - most_recent_email.sent_at) < timedelta(hours=48)
        if is_recent:
            triggering_email = most_recent_email
        else:
            main_seq_emails = [
                e for e in all_sent_emails[:10]
                if e.email_template and e.email_template.sequence_steps.exists() and
                not e.email_template.sequence_steps.first().sequence.is_sub_sequence and
                e.sent_at and (timezone.now() - e.sent_at) < timedelta(days=14)
            ]
            triggering_email = main_seq_emails[0] if main_seq_emails else most_recent_email
    return triggering_email


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
            triggering_email = find_triggering_email(campaign, lead, reply_subject, reply_content, replied_at=reply_date)
            if triggering_email:
                logger.info(f"Matched reply to email: {lead.email} -> subject '{getattr(triggering_email, 'subject', '')}'")
            # Decide main vs sub from the EMAIL they replied to (triggering_email), not from timing.
            # So: if triggering email's template is in a sub-sequence -> sub-sequence reply; else main.
            email_sent_at = getattr(triggering_email, 'sent_at', None) if triggering_email else None
            if triggering_email and triggering_email.email_template and email_sent_at:
                sequence_steps = list(triggering_email.email_template.sequence_steps.select_related('sequence', 'sequence__parent_sequence').all())
                main_seq_ids = {s.sequence_id for s in sequence_steps if not s.sequence.is_sub_sequence}
                sub_seq_ids = {s.sequence_id for s in sequence_steps if s.sequence.is_sub_sequence}
                # Primary rule: reply is to main or sub based on which sequence the triggering email belongs to
                is_sub_sequence_reply = any(s.sequence.is_sub_sequence for s in sequence_steps)
                resolved_contact = None
                if is_sub_sequence_reply and sub_seq_ids:
                    for c in all_contacts:
                        if c.sub_sequence_id and c.sub_sequence_id in sub_seq_ids:
                            resolved_contact = c
                            reply_sub_sequence = next((s.sequence for s in sequence_steps if s.sequence_id == c.sub_sequence_id), None)
                            if reply_sub_sequence:
                                reply_sequence = getattr(reply_sub_sequence, 'parent_sequence', None) or reply_sub_sequence
                                logger.info(f"Detected sub-sequence reply: {lead.email} - reply to sub '{reply_sub_sequence.name}'")
                            break
                if resolved_contact is None:
                    for c in all_contacts:
                        if c.sequence_id and c.sequence_id in main_seq_ids:
                            resolved_contact = c
                            reply_sequence = next((s.sequence for s in sequence_steps if s.sequence_id == c.sequence_id), None)
                            if reply_sequence:
                                logger.info(f"Detected main sequence reply: {lead.email} - reply to sequence '{reply_sequence.name}'")
                            break
                if resolved_contact is not None:
                    contact = resolved_contact
                elif sequence_steps:
                    for step in sequence_steps:
                        if not step.sequence.is_sub_sequence:
                            reply_sequence = step.sequence
                            break
                    if reply_sequence is None and sequence_steps:
                        step = sequence_steps[0]
                        reply_sequence = step.sequence.parent_sequence if step.sequence.is_sub_sequence else step.sequence
                        if step.sequence.is_sub_sequence:
                            reply_sub_sequence = step.sequence
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
                # No triggering email found - try subject match against ALL sent emails before assuming "most recent"
                # (e.g. reply "Re: good to hear jeon david" + "dont send again" should match main seq email, not skip because most recent is sub)
                reply_subject_clean = re.sub(r'^(re:|fw:|fwd:)\s*', '', (reply_subject or ''), flags=re.IGNORECASE).strip()
                fallback_all = list(EmailSendHistory.objects.filter(
                    campaign=campaign, lead=lead, sent_at__isnull=False
                ).order_by('-sent_at').select_related('email_template'))
                if reply_subject_clean and fallback_all:
                    for sent in fallback_all:
                        subj = (sent.subject or (sent.email_template.subject if sent.email_template else '') or '').strip()
                        if not subj:
                            continue
                        if reply_subject_clean.strip().lower() != subj.strip().lower():
                            continue
                        steps = list(sent.email_template.sequence_steps.select_related('sequence').all()) if sent.email_template else []
                        if not steps:
                            break
                        if any(s.sequence.is_sub_sequence for s in steps):
                            is_sub_sequence_reply = True
                            reply_sub_sequence = next((s.sequence for s in steps if s.sequence.is_sub_sequence), None)
                            reply_sequence = (reply_sub_sequence.parent_sequence if reply_sub_sequence else None) or contact.sequence
                            logger.info(f"Matched reply by subject in fallback (sub-seq): {lead.email} -> '{getattr(sent, 'subject', '')}'")
                        else:
                            triggering_email = sent
                            is_sub_sequence_reply = False
                            reply_sequence = steps[0].sequence if steps else contact.sequence
                            logger.info(f"Matched reply by subject in fallback (main): {lead.email} -> '{getattr(sent, 'subject', '')}'")
                        break
                if not triggering_email:
                    # Still no match - we're only guessing from "most recent". Do NOT skip analysis:
                    # we might be wrong (they could be replying to an older main-seq email). Always analyze.
                    reply_sequence = contact.sequence
                    if fallback_all:
                        most_recent = fallback_all[0]
                        if most_recent and most_recent.email_template:
                            sequence_steps = most_recent.email_template.sequence_steps.all()
                            if sequence_steps.exists():
                                seq_step = sequence_steps.first()
                                if seq_step and seq_step.sequence and seq_step.sequence.is_sub_sequence:
                                    reply_sub_sequence = seq_step.sequence
                                    reply_sequence = seq_step.sequence.parent_sequence
                                    logger.info(f"Fallback: most recent is sub '{reply_sub_sequence.name}' for {lead.email} - still analyzing (no confident match)")
                                    # Do NOT set is_sub_sequence_reply = True here - we didn't match, so we analyze
        except Exception as e:
            logger.warning(f'Could not determine reply sequence: {str(e)}')
            reply_sequence = contact.sequence
            # Do NOT assume sub-sequence reply just because contact is in a sub_sequence - they may be
            # replying to a main sequence email. Leave is_sub_sequence_reply False so we still analyze.
        
        # ALWAYS analyze every reply that has content. No skipping - so no reply is ever left "not analyzed".
        # (Main vs sub only controls whether we start a new sub-sequence, not whether we run the analyzer.)
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
                logger.info(f"AI analyzed reply for {lead.email}: {interest_level}" + (" (sub-seq)" if is_sub_sequence_reply else ""))
            except Exception as e:
                logger.error(f"Error analyzing reply with AI: {str(e)}")
                interest_level = 'not_analyzed'
                analysis = f'AI analysis failed: {str(e)}'
        
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
        
        # Find sub-sequence for main sequence replies
        # Also switch sub-sequence when they reply to a sub-seq email with a *different* interest (e.g. first Unsubscribe, then "yes thanks" → Interested)
        sub_sequence = None
        interest_mapping = {
            'positive': 'positive',
            'negative': 'negative',
            'neutral': 'neutral',
            'requested_info': 'requested_info',
            'objection': 'objection',
            'unsubscribe': 'unsubscribe',
            'not_analyzed': 'any'
        }
        target_interest = interest_level if interest_level and interest_level != 'not_analyzed' else 'neutral'
        target_interest = interest_mapping.get(target_interest, target_interest if target_interest in ['positive', 'negative', 'neutral', 'requested_info', 'objection', 'unsubscribe'] else 'any')

        if not is_sub_sequence_reply and contact.sequence:
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
        elif is_sub_sequence_reply and contact.sub_sequence and contact.sequence and target_interest != 'any':
            # Reply was to a sub-sequence email but the new interest is different → switch to that sub-sequence
            if contact.sub_sequence.interest_level != target_interest:
                sub_sequences = EmailSequence.objects.filter(
                    parent_sequence=contact.sequence,
                    is_sub_sequence=True,
                    is_active=True,
                    interest_level=target_interest
                )
                if not sub_sequences.exists():
                    sub_sequences = EmailSequence.objects.filter(
                        parent_sequence=contact.sequence,
                        is_sub_sequence=True,
                        is_active=True,
                        interest_level='any'
                    )
                if sub_sequences.exists():
                    sub_sequence = sub_sequences.first()
                    logger.info(
                        f"Sub-sequence reply from {lead.email} with new interest '{target_interest}' "
                        f"(was '{contact.sub_sequence.interest_level}'). Switching to sub-sequence '{sub_sequence.name}'."
                    )

        # Mark as replied
        was_already_in_sub_sequence = bool(contact.sub_sequence)
        existing_sub_sequence_id = contact.sub_sequence.id if contact.sub_sequence else None

        contact.mark_replied(
            reply_subject=reply_subject,
            reply_content=reply_content,
            reply_at=reply_date,  # Pass the reply date so delay calculations use correct time
            interest_level=interest_level,
            analysis=analysis,
            sub_sequence=sub_sequence
        )

        # Build message
        if is_sub_sequence_reply:
            message = f'Reply received from {lead.email} for sub-sequence email. Reply recorded.'
            if sub_sequence:
                message += f' Switched to sub-sequence "{sub_sequence.name}" (new interest: {target_interest}).'
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

