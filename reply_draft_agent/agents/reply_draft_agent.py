"""
Reply Draft Agent — AI-assisted composition of replies to incoming emails.

Designed as a tool, not a pipeline: each invocation handles one draft at
a time. Every send requires explicit user approval — the agent never
auto-sends.
"""
import json
import logging
import re

from django.utils import timezone

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

        result = email_service.send_raw_email(
            to_email=recipient_email,
            subject=self._ensure_re_prefix(draft.get_final_subject()),
            body=draft.get_final_body(),
            email_account=draft.email_account,
            owner=self.user,
            in_reply_to=in_reply_to,
            campaign=draft.original_email.campaign if draft.original_email_id else None,
            lead=draft.lead,
        )

        if result.get('success'):
            sent_history = None
            sh_id = result.get('send_history_id')
            if sh_id:
                sent_history = EmailSendHistory.objects.filter(id=sh_id).first()
            draft.mark_sent(sent_history)
            self.log_action('sent_draft', {'draft_id': draft.id, 'to': recipient_email})
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
