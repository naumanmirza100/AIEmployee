"""
Reply Draft Agent — AI-assisted composition of replies to incoming emails.

Designed as a tool, not a pipeline: each invocation handles one draft at
a time. Every send requires explicit user approval — the agent never
auto-sends.
"""
import html as _html
import json
import logging
import re

from django.utils import timezone


# Bare http(s) URL detector. Negative lookbehind avoids picking up URLs
# that already sit inside an attribute we just emitted (href="..."), since
# autolinking runs once over the whole already-HTML-escaped string.
_AUTOLINK_URL_RE = re.compile(r'(?<![\"\'>=])(https?://[^\s<>"\']+)', re.IGNORECASE)


_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _html_body_to_plain(html):
    """Cheap text/plain fallback derived from a user-composed HTML body.

    Used when the user writes the email in HTML mode — we still send a
    text/plain alternative for accessibility / text-only clients, and the
    Sent-tab mirror needs both shapes (`body` + `body_html`) to stay
    consistent with how reply drafts are stored.

    Strategy: drop tags + decode entities + collapse whitespace. Not a
    full HTML→text converter (no list bullets, no link footers); good
    enough for the fallback that 99% of clients ignore.
    """
    if not html:
        return ''
    no_tags = _HTML_TAG_RE.sub('', html)
    decoded = _html.unescape(no_tags)
    # Collapse runs of blank lines and trailing/leading whitespace so the
    # plain text doesn't look like the raw HTML with tags excised.
    cleaned = re.sub(r'\n\s*\n+', '\n\n', decoded).strip()
    return cleaned


def _plain_body_to_html(text):
    """Convert a plain-text email body into minimal, safe HTML.

    Used at send time to give recipients (and our own Sent-tab view) a
    rendered version of the AI/user-edited plain body. Steps:

      1. HTML-escape — anything `< > &` the user typed must not render as
         markup. This is the only XSS-relevant step here; everything below
         only operates on the already-escaped string.
      2. Autolink bare http(s):// URLs so they're clickable in the
         recipient's client (Gmail/Outlook fold raw URLs but our Sent-tab
         iframe needs explicit `<a>` tags to apply its link styling).
      3. Paragraph breaks on blank lines + `<br>` on single newlines so
         the formatting the user typed survives — without this most clients
         collapse all whitespace into a single line.

    Returns '' for empty input — callers treat that as "no html alternative,
    send text/plain only".
    """
    if not text or not text.strip():
        return ''

    escaped = _html.escape(text, quote=False)

    def _link(m):
        url = m.group(1)
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'

    linked = _AUTOLINK_URL_RE.sub(_link, escaped)

    # Split on one-or-more blank lines → paragraphs. Single newlines stay
    # as <br> inside the paragraph so multi-line lists / sign-offs aren't
    # collapsed.
    blocks = []
    for chunk in re.split(r'\n\s*\n', linked):
        if not chunk.strip():
            continue
        blocks.append('<p style="margin:0 0 1em 0;">' + chunk.replace('\n', '<br>') + '</p>')
    if not blocks:
        return ''

    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'font-size:14px;line-height:1.5;color:#222;">'
        + ''.join(blocks)
        + '</div>'
    )

from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent
from marketing_agent.models import Reply, EmailAccount, EmailSendHistory
from marketing_agent.services.email_service import email_service
from ..models import ReplyDraft, InboxEmail

logger = logging.getLogger(__name__)


class ReplyDraftAgent(MarketingBaseAgent):
    """AI agent that drafts replies to incoming emails for user review."""

    # Length presets. The user picks one in the UI; the prompt asks the
    # model to respect the corresponding word band. Replaces the previous
    # hard "<150 words" rule, which truncated substantive replies.
    LENGTH_GUIDANCE = {
        'short':  'Aim for 60-100 words. Be brief and direct.',
        'medium': 'Aim for 120-200 words. Cover the points without padding.',
        'long':   'Aim for 250-400 words. You may go deeper when the context warrants it.',
    }
    DEFAULT_LENGTH = 'medium'

    SYSTEM_PROMPT = (
        "You are an email assistant helping a human draft a reply to an incoming "
        "message. You never send emails yourself — your output is a proposal the "
        "human will review, edit, and approve.\n\n"
        "Rules:\n"
        "1. Match the formality of the sender. A casual inbound gets a warm reply; "
        "a formal inbound gets a professional one.\n"
        "2. Stay grounded in the original email and the user's instructions. Do not "
        "invent product details, pricing, or commitments that are not provided.\n"
        "3. Respect the detected interest level:\n"
        "   - positive: momentum-building, propose a clear next step.\n"
        "   - requested_info: directly address what they asked for.\n"
        "   - objection: acknowledge the concern first, then respond.\n"
        "   - negative / unsubscribe: brief, respectful, offer an easy opt-out.\n"
        "   - neutral: warm, re-engage with a soft question.\n"
        "4. Honor the length guidance the user provided in the prompt.\n"
        "5. End with either a clear question or a specific next step.\n\n"
        "Output strict JSON only, with exactly these keys: "
        '{"subject": "...", "body": "...", "reasoning": "..."}'
    )

    INBOX_SYSTEM_PROMPT = (
        "You are an email assistant helping a human draft a reply to an incoming "
        "email that arrived in their inbox. No prior CRM analysis is available, so "
        "you must analyze the message yourself before drafting the reply.\n\n"
        "Step 1 — analyze: read the sender name/email and the message content. "
        "Decide the sender's intent and classify their interest level as one of: "
        "positive, negative, neutral, requested_info, objection, unsubscribe.\n"
        "Step 2 — draft the reply with these rules:\n"
        "1. Match the formality of the sender.\n"
        "2. Stay grounded in what the sender actually wrote and the user's instructions. "
        "Do not invent product details, pricing, or commitments.\n"
        "3. Respect the interest level you just classified:\n"
        "   - positive: momentum-building, propose a clear next step.\n"
        "   - requested_info: directly address what they asked for.\n"
        "   - objection: acknowledge the concern first, then respond.\n"
        "   - negative / unsubscribe: brief, respectful, offer an easy opt-out.\n"
        "   - neutral: warm, re-engage with a soft question.\n"
        "4. Honor the length guidance the user provided in the prompt.\n"
        "5. End with a clear question or a specific next step.\n\n"
        "Output strict JSON only, with exactly these keys: "
        '{"interest_level": "...", "analysis": "...", "subject": "...", "body": "...", "reasoning": "..."}'
    )

    def __init__(self, user=None, company_id=None, **kwargs):
        super().__init__(**kwargs)
        self.user = user
        self.company_id = company_id
        self.agent_key_name = 'reply_draft_agent'

    def process(self, action, **kwargs):
        if action == 'generate_draft':
            return self.generate_draft(**kwargs)
        if action == 'regenerate_draft':
            return self.regenerate_draft(**kwargs)
        if action == 'approve_draft':
            return self.approve_draft(**kwargs)
        if action == 'send_approved':
            return self.send_approved(**kwargs)
        return {'success': False, 'error': f'Unknown action: {action}'}

    def generate_draft(self, original_email_id=None, inbox_email_id=None,
                       user_context='', tone='professional', length=None,
                       email_account_id=None, parent_draft_id=None):
        """Generate a new draft reply for an incoming email.

        Exactly one of `original_email_id` (campaign Reply) or
        `inbox_email_id` (generic InboxEmail) must be provided.

        Args:
            original_email_id: Reply.id of a campaign reply.
            inbox_email_id: InboxEmail.id of a generic inbox message.
            user_context: free-text instructions ("keep it short", "mention demo link").
            tone: one of ReplyDraft.TONE_CHOICES.
            length: 'short' / 'medium' / 'long'. Maps to the LENGTH_GUIDANCE
                band the model is told to target. Defaults to 'medium'.
            email_account_id: override which account to send from.
            parent_draft_id: link to the prior draft when regenerating.
        """
        if not original_email_id and not inbox_email_id:
            return {'success': False, 'error': 'original_email_id or inbox_email_id is required'}
        if original_email_id and inbox_email_id:
            return {'success': False, 'error': 'Provide only one of original_email_id / inbox_email_id'}

        length = (length or self.DEFAULT_LENGTH).strip().lower()
        if length not in self.LENGTH_GUIDANCE:
            length = self.DEFAULT_LENGTH

        if original_email_id:
            return self._generate_from_reply(
                original_email_id=original_email_id,
                user_context=user_context,
                tone=tone,
                length=length,
                email_account_id=email_account_id,
                parent_draft_id=parent_draft_id,
            )
        return self._generate_from_inbox(
            inbox_email_id=inbox_email_id,
            user_context=user_context,
            tone=tone,
            length=length,
            email_account_id=email_account_id,
            parent_draft_id=parent_draft_id,
        )

    def _generate_from_reply(self, original_email_id, user_context, tone, length,
                             email_account_id, parent_draft_id):
        try:
            reply = Reply.objects.select_related('lead', 'campaign').get(id=original_email_id)
        except Reply.DoesNotExist:
            return {'success': False, 'error': f'Incoming email {original_email_id} not found'}

        if self.user is not None and reply.lead and reply.lead.owner_id != self.user.id:
            return {'success': False, 'error': 'Not authorized for this reply'}

        account = self._resolve_email_account(email_account_id, reply)

        user_prompt = self._build_user_prompt(reply, user_context, tone, length)
        # Long replies need more output budget — bump max_tokens for 'long'
        # so the model isn't truncated mid-sentence.
        max_tokens = 1400 if length == 'long' else 800
        raw = self._call_llm(
            prompt=user_prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.5,
            max_tokens=max_tokens,
        )

        subject, body, reasoning = self._parse_llm_output(raw, fallback_subject=reply.reply_subject)
        if not body:
            return {'success': False, 'error': 'AI failed to produce a draft. Try regenerating.'}

        parent = None
        if parent_draft_id:
            parent = ReplyDraft.objects.filter(id=parent_draft_id, owner=self.user).first()

        draft = ReplyDraft.objects.create(
            owner=self.user,
            original_email=reply,
            lead=reply.lead,
            email_account=account,
            draft_subject=subject,
            draft_body=body,
            tone=tone,
            ai_notes=reasoning,
            generation_prompt=user_context,
            parent_draft=parent,
            regeneration_count=(parent.regeneration_count + 1) if parent else 0,
        )

        self.log_action('generated_draft', {
            'draft_id': draft.id,
            'source': 'reply',
            'reply_id': reply.id,
            'tone': tone,
            'regen_count': draft.regeneration_count,
        })
        return {
            'success': True,
            'draft_id': draft.id,
            'source': 'reply',
            'subject': draft.draft_subject,
            'body': draft.draft_body,
            'reasoning': draft.ai_notes,
        }

    def _generate_from_inbox(self, inbox_email_id, user_context, tone, length,
                             email_account_id, parent_draft_id):
        try:
            msg = InboxEmail.objects.select_related('email_account').get(id=inbox_email_id)
        except InboxEmail.DoesNotExist:
            return {'success': False, 'error': f'Inbox email {inbox_email_id} not found'}

        if self.user is not None and msg.owner_id != self.user.id:
            return {'success': False, 'error': 'Not authorized for this email'}

        account = self._resolve_email_account(email_account_id, None) or msg.email_account

        user_prompt = self._build_inbox_prompt(msg, user_context, tone, length)
        max_tokens = 1500 if length == 'long' else 900
        raw = self._call_llm(
            prompt=user_prompt,
            system_prompt=self.INBOX_SYSTEM_PROMPT,
            temperature=0.5,
            max_tokens=max_tokens,
        )

        subject, body, reasoning, interest_level, analysis = self._parse_inbox_llm_output(
            raw, fallback_subject=msg.subject
        )
        if not body:
            return {'success': False, 'error': 'AI failed to produce a draft. Try regenerating.'}

        # Persist analysis back onto the InboxEmail so the UI can display it.
        update_fields = []
        if interest_level and interest_level != msg.interest_level:
            msg.interest_level = interest_level
            update_fields.append('interest_level')
        if analysis and analysis != msg.analysis:
            msg.analysis = analysis
            update_fields.append('analysis')
        if update_fields:
            update_fields.append('updated_at')
            msg.save(update_fields=update_fields)

        parent = None
        if parent_draft_id:
            parent = ReplyDraft.objects.filter(id=parent_draft_id, owner=self.user).first()

        draft = ReplyDraft.objects.create(
            owner=self.user,
            inbox_email=msg,
            lead=None,
            email_account=account,
            draft_subject=subject,
            draft_body=body,
            tone=tone,
            ai_notes=reasoning,
            generation_prompt=user_context,
            parent_draft=parent,
            regeneration_count=(parent.regeneration_count + 1) if parent else 0,
        )

        self.log_action('generated_draft', {
            'draft_id': draft.id,
            'source': 'inbox',
            'inbox_email_id': msg.id,
            'tone': tone,
            'regen_count': draft.regeneration_count,
        })
        return {
            'success': True,
            'draft_id': draft.id,
            'source': 'inbox',
            'subject': draft.draft_subject,
            'body': draft.draft_body,
            'reasoning': draft.ai_notes,
            'interest_level': msg.interest_level,
            'analysis': msg.analysis,
        }

    # Cap on context carried forward across regenerations. Without this the
    # generation_prompt grows by `new_instructions` every iteration and a
    # user who hits "Regenerate" 10 times ends up with a multi-KB prompt
    # full of stale, contradictory instructions.
    _REGEN_CONTEXT_MAX_CHARS = 800

    def regenerate_draft(self, draft_id, new_instructions='', tone=None, length=None):
        """Produce a fresh draft based on an existing one, with new instructions.

        The parent draft is marked 'rejected' once a new child is created, so
        the drafts list and pending counts only reflect the latest iteration.

        The new instruction set is the *fresh* `new_instructions` plus the
        original prompt that started this regeneration chain — bounded by
        `_REGEN_CONTEXT_MAX_CHARS` so repeated regenerations don't bloat
        the prompt with stacked, contradictory guidance.
        """
        try:
            existing = ReplyDraft.objects.get(id=draft_id, owner=self.user)
        except ReplyDraft.DoesNotExist:
            return {'success': False, 'error': 'Draft not found'}
        if existing.status == 'sent':
            return {'success': False, 'error': 'Cannot regenerate a draft that was already sent'}

        # Walk back to the root draft of this regen chain so we keep the
        # original user intent, but only that — every intermediate draft's
        # accumulated instructions are dropped.
        root_prompt = (existing.generation_prompt or '').strip()
        seen = {existing.id}
        cursor = existing.parent_draft
        while cursor and cursor.id not in seen:
            seen.add(cursor.id)
            if cursor.generation_prompt:
                root_prompt = cursor.generation_prompt.strip()
            cursor = cursor.parent_draft

        new_part = (new_instructions or '').strip()
        if root_prompt and new_part:
            combined_context = f"{new_part}\n\n[earlier guidance: {root_prompt}]"
        else:
            combined_context = new_part or root_prompt
        if len(combined_context) > self._REGEN_CONTEXT_MAX_CHARS:
            combined_context = combined_context[:self._REGEN_CONTEXT_MAX_CHARS] + '… [truncated]'

        result = self.generate_draft(
            original_email_id=existing.original_email_id,
            inbox_email_id=existing.inbox_email_id,
            user_context=combined_context,
            tone=tone or existing.tone,
            length=length,
            email_account_id=existing.email_account_id,
            parent_draft_id=existing.id,
        )

        # If the new draft was created successfully, supersede the parent.
        if result.get('success') and result.get('draft_id') and existing.status != 'rejected':
            # Reassign attachments from the parent to the child so the user
            # doesn't lose uploads on Regenerate. Cheaper than copying file
            # bytes — we just point the row's FK at the new draft. The
            # parent is being marked 'rejected' anyway, so no path keeps a
            # reference to its (now empty) attachments.
            try:
                from ..models import ReplyDraftAttachment
                ReplyDraftAttachment.objects.filter(draft_id=existing.id).update(
                    draft_id=result['draft_id'],
                )
            except Exception:
                logger.exception('regenerate_draft: failed to reassign attachments to new draft')

            existing.status = 'rejected'
            existing.save(update_fields=['status', 'updated_at'])

        return result

    def approve_draft(self, draft_id, edited_subject=None, edited_body=None):
        """User approves a draft, optionally with inline edits. Send happens separately."""
        try:
            draft = ReplyDraft.objects.get(id=draft_id, owner=self.user)
        except ReplyDraft.DoesNotExist:
            return {'success': False, 'error': 'Draft not found'}
        if draft.status == 'sent':
            return {'success': False, 'error': 'Already sent'}

        update_fields = ['status', 'updated_at']
        if edited_subject is not None:
            draft.edited_subject = edited_subject
            update_fields.append('edited_subject')
        if edited_body is not None:
            draft.edited_body = edited_body
            update_fields.append('edited_body')
        draft.status = 'approved'
        draft.save(update_fields=update_fields)
        return {'success': True, 'draft_id': draft.id, 'status': draft.status}

    def send_approved(self, draft_id):
        """Send an approved draft through the shared email service.

        Requires status='approved'. Pending drafts must go through approve
        first (even if approval is just a no-op click in the UI) — the
        review step exists deliberately and bypassing it here defeated it.
        Failed drafts are allowed to retry.
        """
        try:
            draft = ReplyDraft.objects.select_related(
                'lead', 'email_account', 'original_email', 'original_email__triggering_email',
                'inbox_email',
            ).get(id=draft_id, owner=self.user)
        except ReplyDraft.DoesNotExist:
            return {'success': False, 'error': 'Draft not found'}
        if draft.status not in ('approved', 'failed'):
            return {'success': False, 'error': f'Draft must be approved before sending (currently "{draft.status}")'}

        recipient_email = draft.get_recipient_email()
        if not recipient_email:
            return {'success': False, 'error': 'Draft has no recipient email'}

        in_reply_to = self._resolve_in_reply_to(draft)
        references = self._resolve_references(draft, in_reply_to)

        # Collect user-uploaded attachments. Read bytes once here so
        # email_service stays storage-backend agnostic (file lives on local
        # disk today, S3 tomorrow — same call site).
        attachments_payload = []
        for att in draft.attachments.all():
            if not att.file:
                continue
            try:
                with att.file.open('rb') as fh:
                    raw = fh.read()
            except Exception:
                logger.warning('send_approved: could not read attachment id=%s for draft %s', att.id, draft.id)
                continue
            if not raw:
                continue
            attachments_payload.append((
                att.filename or 'attachment',
                raw,
                att.content_type or 'application/octet-stream',
            ))

        # Build the (text, html) pair we send + mirror. Two paths:
        #
        #   format='text' (AI replies, plain compose)
        #     stored body IS the plain text. We derive HTML from it via
        #     the autolink/<br> converter so recipients in HTML clients
        #     get clickable links + preserved formatting.
        #
        #   format='html' (Gmail-style compose with HTML toggle on)
        #     stored body IS the HTML markup the user typed. We derive a
        #     plain-text fallback by stripping tags so the multipart's
        #     text/plain alternative isn't empty (text-only clients +
        #     accessibility readers depend on it).
        #
        # Re: subject prefixing — only reply drafts get the "Re:" prefix
        # auto-added. A fresh compose has no parent subject and the user's
        # typed subject should go out verbatim, so _ensure_re_prefix is
        # gated on the presence of a source email.
        final_body = draft.get_final_body()
        if draft.body_format == 'html':
            body_html = final_body or ''
            plain_body = _html_body_to_plain(body_html)
        else:
            body_html = _plain_body_to_html(final_body)
            plain_body = final_body

        is_reply = bool(draft.original_email_id or draft.inbox_email_id)
        outgoing_subject = (
            self._ensure_re_prefix(draft.get_final_subject())
            if is_reply else (draft.get_final_subject() or '')
        )

        result = email_service.send_raw_email(
            to_email=recipient_email,
            subject=outgoing_subject,
            body=plain_body,
            email_account=draft.email_account,
            owner=self.user,
            in_reply_to=in_reply_to,
            references=references,
            campaign=draft.original_email.campaign if draft.original_email_id else None,
            lead=draft.lead,
            html_body=body_html or None,
            attachments=attachments_payload or None,
        )

        if result.get('success'):
            sent_history = None
            sh_id = result.get('send_history_id')
            if sh_id:
                sent_history = EmailSendHistory.objects.filter(id=sh_id).first()
            draft.mark_sent(sent_history)
            self.log_action('sent_draft', {'draft_id': draft.id, 'to': recipient_email})

            # Mirror the outgoing message into our InboxEmail/InboxAttachment
            # tables so:
            #   1) the Sent tab shows it immediately (no 5-min wait for the
            #      next IMAP sync);
            #   2) thread linkage is correct regardless of what
            #      compute_thread_key would derive from the headers (a fresh
            #      inbound message has no References, so its key is `subj:..`,
            #      while the sent reply's would be `root:..` — the only way
            #      to put them in the same thread is to copy the parent's
            #      key explicitly, which we can do here);
            #   3) attachments are visible in the Sent UI even when the
            #      upstream SMTP provider doesn't auto-save to the IMAP Sent
            #      folder (Hostinger/cPanel/etc.).
            # Idempotent — the (account, message_id) unique constraint stops
            # the later IMAP sync from inserting a duplicate.
            try:
                self._mirror_sent_to_inbox(
                    draft=draft,
                    recipient_email=recipient_email,
                    in_reply_to=in_reply_to,
                    references=references,
                    message_id=result.get('message_id') or '',
                    attachments=attachments_payload,
                    body_html=body_html,
                    plain_body=plain_body,
                    outgoing_subject=outgoing_subject,
                )
            except Exception:
                logger.exception(
                    'send_approved: failed to mirror sent message into InboxEmail '
                    '— Sent tab will still pick it up via the next IMAP sync'
                )
        else:
            draft.mark_failed(result.get('error', 'unknown error'))
            self.log_action('send_failed', {'draft_id': draft.id, 'error': result.get('error')})

        return {
            'success': bool(result.get('success')),
            'draft_id': draft.id,
            'status': draft.status,
            'error': result.get('error'),
        }

    # --- internals ---

    def _build_user_prompt(self, reply, user_context, tone, length):
        lead = reply.lead
        sender_name = ''
        if lead:
            sender_name = ' '.join(filter(None, [lead.first_name, lead.last_name])).strip() or lead.email
        length_guide = self.LENGTH_GUIDANCE.get(length, self.LENGTH_GUIDANCE[self.DEFAULT_LENGTH])
        return (
            f"Desired tone: {tone}\n"
            f"Length guidance: {length_guide}\n"
            f"Detected interest level: {reply.interest_level or 'unknown'}\n"
            f"Prior AI analysis: {reply.analysis or 'none'}\n"
            f"Sender: {sender_name} <{lead.email if lead else ''}> "
            f"at {lead.company or 'n/a'}\n\n"
            f"INCOMING SUBJECT: {reply.reply_subject}\n"
            f"INCOMING BODY:\n{reply.reply_content}\n\n"
            f"User instructions: {user_context or '(none)'}\n\n"
            "Draft the reply now, returning the JSON object described in the system prompt."
        )

    def _build_inbox_prompt(self, msg, user_context, tone, length):
        sender_name = (msg.from_name or '').strip() or msg.from_email
        length_guide = self.LENGTH_GUIDANCE.get(length, self.LENGTH_GUIDANCE[self.DEFAULT_LENGTH])
        # Surface attachment metadata so the model knows the sender included
        # files. We don't pass file contents here (no extraction pipeline
        # yet) but listing names + types lets the model acknowledge them
        # rather than ignore them entirely.
        attachments_block = ''
        try:
            atts = list(msg.attachments.all().only('filename', 'content_type', 'size_bytes', 'is_inline'))
            visible = [a for a in atts if not a.is_inline]
            if visible:
                lines = []
                for a in visible[:10]:  # cap at 10 — past that is noise
                    size_kb = max(1, (a.size_bytes or 0) // 1024)
                    lines.append(f"  - {a.filename} ({a.content_type or 'unknown'}, {size_kb} KB)")
                attachments_block = (
                    "ATTACHMENTS (filenames only — you do not have the contents, "
                    "do not invent details from them):\n" + "\n".join(lines) + "\n\n"
                )
        except Exception:
            attachments_block = ''

        # Recent thread context: previous messages in the same conversation.
        # Lets the model write a reply that's aware of the back-and-forth
        # rather than treating each message in isolation.
        thread_block = self._build_thread_context(msg)

        return (
            f"Desired tone: {tone}\n"
            f"Length guidance: {length_guide}\n"
            f"Sender: {sender_name} <{msg.from_email}>\n"
            f"Received: {msg.received_at.isoformat() if msg.received_at else 'unknown'}\n\n"
            f"{thread_block}"
            f"INCOMING SUBJECT: {msg.subject or '(no subject)'}\n"
            f"INCOMING BODY:\n{msg.body or '(empty body)'}\n\n"
            f"{attachments_block}"
            f"User instructions: {user_context or '(none)'}\n\n"
            "First classify the sender's interest_level, write a short analysis, "
            "then draft the reply. Return the JSON object described in the system prompt."
        )

    def _build_thread_context(self, msg, max_messages=3, max_chars_per_msg=600):
        """Render the most recent prior messages in this thread as a context block.

        Pulls up to `max_messages` prior InboxEmail rows (both directions)
        for the same `thread_key`, oldest-first so the conversation reads
        naturally. Returns '' when no prior thread context exists.
        """
        thread_key = getattr(msg, 'thread_key', '') or ''
        if not thread_key:
            return ''
        try:
            prior = list(
                InboxEmail.objects
                .filter(
                    email_account_id=msg.email_account_id,
                    thread_key=thread_key,
                )
                .exclude(id=msg.id)
                .order_by('-received_at')
                .only('from_email', 'from_name', 'to_email', 'direction',
                      'subject', 'body', 'received_at')[:max_messages]
            )
        except Exception:
            return ''
        if not prior:
            return ''
        prior.reverse()  # oldest first reads more naturally
        lines = ["PRIOR MESSAGES IN THIS THREAD (oldest first):"]
        for p in prior:
            who = (p.from_name or p.from_email or '').strip()
            arrow = '→ you' if p.direction == 'in' else 'you →'
            when = p.received_at.strftime('%Y-%m-%d %H:%M') if p.received_at else ''
            body = (p.body or '').strip().replace('\r\n', '\n')
            if len(body) > max_chars_per_msg:
                body = body[:max_chars_per_msg] + '… [truncated]'
            lines.append(f"--- {arrow} {who} @ {when} ---")
            lines.append(body)
        lines.append('--- end of prior messages ---\n')
        return '\n'.join(lines) + '\n'

    _VALID_INTEREST_LEVELS = {
        'positive', 'negative', 'neutral', 'requested_info',
        'objection', 'unsubscribe', 'not_analyzed',
    }

    def _parse_llm_output(self, raw, fallback_subject=''):
        """Extract subject/body/reasoning from the LLM JSON output, tolerant of minor drift."""
        data = self._loose_json(raw)
        if data is None:
            return self._re_prefix(fallback_subject), (raw or '').strip(), ''

        subject = (data.get('subject') or fallback_subject or '').strip()
        body = (data.get('body') or '').strip()
        reasoning = (data.get('reasoning') or '').strip()
        return self._re_prefix(subject), body, reasoning

    def _parse_inbox_llm_output(self, raw, fallback_subject=''):
        """Parse the extended inbox JSON shape: interest_level + analysis + subject + body + reasoning."""
        data = self._loose_json(raw)
        if data is None:
            return self._re_prefix(fallback_subject), (raw or '').strip(), '', '', ''

        subject = (data.get('subject') or fallback_subject or '').strip()
        body = (data.get('body') or '').strip()
        reasoning = (data.get('reasoning') or '').strip()
        interest_level = (data.get('interest_level') or '').strip().lower()
        if interest_level not in self._VALID_INTEREST_LEVELS:
            interest_level = 'not_analyzed'
        analysis = (data.get('analysis') or '').strip()
        return self._re_prefix(subject), body, reasoning, interest_level, analysis

    @staticmethod
    def _loose_json(raw):
        """Parse JSON tolerantly when the model wraps its output in prose / fences.

        Strategy:
          1. Try plain json.loads on the trimmed text.
          2. Strip ```json … ``` / ``` … ``` fences — Groq frequently emits
             these even when the system prompt says "JSON only".
          3. Walk the string brace-by-brace and try every candidate object
             starting at each '{', returning the first one that parses.
             This survives a leading "Sure, here's your JSON:" preamble or
             a trailing "Hope that helps!" — both observed in the wild.
        """
        if not raw:
            return None
        text = raw.strip()
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            pass

        # ```json ... ``` or ``` ... ``` fences
        fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL | re.IGNORECASE)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except (ValueError, TypeError):
                pass

        # Brace-walk: try the largest candidate from each '{' going outward.
        # raw_decode is the right tool — it stops at the end of the first
        # complete value, ignoring any trailing junk.
        decoder = json.JSONDecoder()
        for i, ch in enumerate(text):
            if ch != '{':
                continue
            try:
                obj, _end = decoder.raw_decode(text[i:])
                if isinstance(obj, dict):
                    return obj
            except ValueError:
                continue
        return None

    @staticmethod
    def _re_prefix(subject):
        if not subject:
            return subject
        return subject if subject.lower().startswith('re:') else f'Re: {subject}'

    _ensure_re_prefix = _re_prefix

    def _resolve_email_account(self, email_account_id, reply):
        """Choose which EmailAccount to send the draft from.

        Priority:
            1. Caller-supplied id (only if it belongs to the user and is active).
            2. The user's reply-agent-flagged account.
            3. Any active account belonging to the user (default-first).

        Step 2 prevents accidental cross-bleed: without it, a user with a
        marketing campaign account but no flagged reply-agent account would
        end up sending replies from the marketing mailbox, which violates
        the agent's isolation guarantee.
        """
        if email_account_id:
            account = EmailAccount.objects.filter(id=email_account_id, owner=self.user, is_active=True).first()
            if account:
                return account
        if self.user is not None:
            flagged = EmailAccount.objects.filter(
                owner=self.user, is_active=True, is_reply_agent_account=True,
            ).order_by('-is_default', '-created_at').first()
            if flagged:
                return flagged
        qs = EmailAccount.objects.filter(is_active=True)
        if self.user is not None:
            qs = qs.filter(owner=self.user)
        return qs.order_by('-is_default', '-created_at').first()

    @staticmethod
    def _resolve_in_reply_to(draft):
        """RFC Message-ID to use in the outbound In-Reply-To header for threading."""
        if draft.original_email_id and draft.original_email:
            triggering = getattr(draft.original_email, 'triggering_email', None)
            if triggering and getattr(triggering, 'message_id', None):
                return triggering.message_id
        if draft.inbox_email_id and draft.inbox_email:
            return draft.inbox_email.message_id or None
        return None

    @staticmethod
    def _resolve_references(draft, in_reply_to):
        """Build the RFC 5322 References chain for the outbound reply.

        Per the spec, References should be the parent's existing References
        chain followed by its Message-ID. This is what mail clients use to
        reconstruct the thread tree, so getting it right matters for the
        recipient's inbox just as much as for our own Sent-tab linkage.
        Without this we'd send References = just the immediate parent, and
        any deep thread would lose its earlier context in clients that walk
        the full chain (Apple Mail / mutt / Outlook desktop).
        """
        irt = (in_reply_to or '').strip().strip('<>')
        if not irt:
            return None

        # Pull the parent's existing References chain when we have it.
        existing_refs = ''
        if draft.inbox_email_id and draft.inbox_email:
            existing_refs = (draft.inbox_email.references or '').strip()
        elif draft.original_email_id and draft.original_email:
            triggering = getattr(draft.original_email, 'triggering_email', None)
            if triggering:
                existing_refs = (getattr(triggering, 'references', '') or '').strip()

        wrapped_irt = f'<{irt}>'
        if not existing_refs:
            return wrapped_irt
        # Existing chain may or may not already include irt; append only if
        # it's not already the last entry to avoid `… <X> <X>` duplication.
        last_token = existing_refs.split()[-1].strip().lstrip('<').rstrip('>') if existing_refs else ''
        if last_token == irt:
            return existing_refs
        return f'{existing_refs} {wrapped_irt}'

    def _mirror_sent_to_inbox(self, *, draft, recipient_email, in_reply_to, references,
                              message_id, attachments, body_html='', plain_body=None,
                              outgoing_subject=None):
        """Insert a direction='out' InboxEmail row mirroring the message we just sent.

        Why a mirror (instead of just relying on the IMAP Sent-folder sync):
          - Many SMTP providers (Hostinger / cPanel / generic IMAP+SMTP)
            don't auto-copy SMTP submissions into the Sent IMAP folder, so
            the user would never see their reply in the Sent tab without
            this mirror.
          - Even on providers that do (Gmail), the IMAP sync runs every
            5 minutes — the mirror gives instant feedback.
          - The thread_key derived by compute_thread_key from message
            headers alone doesn't always match the parent inbox row (a new
            external email arrives with no References → its key is
            `subj:..`, but its reply's key would be `root:..`). Copying the
            parent's key explicitly is the only way to keep both messages
            in the same thread group.

        Idempotent on (account, message_id) — the unique constraint on
        InboxEmail makes this safe to call alongside the later IMAP sync.
        """
        from .models import InboxEmail, InboxAttachment

        if not draft.email_account or not message_id:
            return

        msg_id = message_id.strip().strip('<>')[:500]
        if not msg_id:
            return

        # Idempotent: if a previous attempt (or a fast IMAP sync) already
        # landed this row, don't insert again. Cheaper than letting the
        # unique constraint raise.
        if InboxEmail.objects.filter(
            email_account_id=draft.email_account_id, message_id=msg_id,
        ).exists():
            return

        # Inherit the parent's thread_key when the source is an inbox email
        # so this reply lands in the same conversation. Falls back to the
        # standard derivation when sending to a campaign-Reply source or
        # when the parent has no key yet.
        from_email = draft.email_account.email or ''
        # Prefer the subject we actually put on the wire (may have a "Re:"
        # prefix added for replies) so the Sent-tab row matches what the
        # recipient sees. Falls back to draft fields if the caller
        # didn't pass it through.
        subject = (outgoing_subject if outgoing_subject is not None else draft.get_final_subject()) or ''
        # Same idea for the body — `plain_body` is the text/plain side of
        # the multipart we sent, which is the right thing to store as the
        # row's `body` regardless of whether the user composed in plain
        # text or HTML mode.
        body = plain_body if plain_body is not None else (draft.get_final_body() or '')

        thread_key = ''
        if draft.inbox_email_id and draft.inbox_email:
            thread_key = (draft.inbox_email.thread_key or '').strip()
        if not thread_key:
            thread_key = InboxEmail.compute_thread_key(
                references=references or '',
                in_reply_to=in_reply_to or '',
                subject=subject,
                from_email=from_email,
                to_email=recipient_email,
            )

        irt_clean = (in_reply_to or '').strip().strip('<>')[:500]

        from_name = (draft.email_account.name or '').strip()[:255]

        row = InboxEmail.objects.create(
            owner=self.user,
            email_account=draft.email_account,
            message_id=msg_id,
            in_reply_to=irt_clean,
            references=(references or '')[:4000],
            from_email=from_email,
            from_name=from_name,
            subject=subject[:500],
            body=body,
            # Storing the HTML version that went out via SMTP keeps the
            # Sent tab visually consistent with the Inbox tab — both render
            # through HtmlBody's iframe with dark-theme overrides. When
            # body_html is empty (e.g. the plain body was empty), the
            # frontend falls back to plain-text rendering automatically.
            body_html=body_html or '',
            received_at=timezone.now(),
            to_email=(recipient_email or '')[:254],
            direction='out',
            thread_key=thread_key,
        )

        # Mirror the user's uploaded files as InboxAttachment rows on the
        # sent message. We REUSE the source file path instead of re-writing
        # the bytes through a new ContentFile/save() cycle:
        #
        #   - Re-writing was the wrong design: we already have a copy of
        #     these bytes on disk under reply_draft_attachments/, and a
        #     second write at send time hit a file-corruption issue
        #     (downloaded JPEGs failed to open, OGGs wouldn't play). The
        #     extra write also doubled storage usage and dropped the sha8
        #     prefix from the new filename.
        #   - File sharing means both ReplyDraftAttachment and InboxAttachment
        #     rows reference the same path. The post_delete signals in
        #     reply_draft_agent.apps now check for sibling references before
        #     unlinking, so deleting one row doesn't orphan the other.
        for src_att in draft.attachments.all():
            if not src_att.file or not src_att.file.name:
                continue
            try:
                att = InboxAttachment(
                    inbox_email_id=row.id,
                    filename=(src_att.filename or 'attachment')[:255],
                    content_type=(src_att.content_type or '')[:120],
                    size_bytes=src_att.size_bytes or 0,
                    sha256=(src_att.sha256 or '')[:64],
                    is_inline=False,
                )
                # Set the path directly so the row points at the source
                # file. Skipping FieldFile.save() bypasses upload_to + the
                # storage round-trip — exactly what we want here.
                att.file.name = src_att.file.name
                att.save()
            except Exception:
                logger.warning(
                    'mirror_sent: failed to attach source file %r onto sent inbox row %s',
                    src_att.filename, row.id,
                )
