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
from ..models import ReplyDraft

logger = logging.getLogger(__name__)


class ReplyDraftAgent(MarketingBaseAgent):
    """AI agent that drafts replies to incoming emails for user review."""

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
        "4. Keep under 150 words unless the user asks for more.\n"
        "5. End with either a clear question or a specific next step.\n\n"
        "Output strict JSON only, with exactly these keys: "
        '{"subject": "...", "body": "...", "reasoning": "..."}'
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

    def generate_draft(self, original_email_id, user_context='', tone='professional',
                       email_account_id=None, parent_draft_id=None):
        """Generate a new draft reply for an incoming email.

        Args:
            original_email_id: Reply.id of the incoming message.
            user_context: free-text instructions ("keep it short", "mention demo link").
            tone: one of ReplyDraft.TONE_CHOICES.
            email_account_id: override which account to send from.
            parent_draft_id: link to the prior draft when regenerating.
        """
        try:
            reply = Reply.objects.select_related('lead', 'campaign').get(id=original_email_id)
        except Reply.DoesNotExist:
            return {'success': False, 'error': f'Incoming email {original_email_id} not found'}

        if self.user is not None and reply.lead and reply.lead.owner_id != self.user.id:
            return {'success': False, 'error': 'Not authorized for this reply'}

        account = self._resolve_email_account(email_account_id, reply)

        user_prompt = self._build_user_prompt(reply, user_context, tone)
        raw = self._call_llm(
            prompt=user_prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.5,
            max_tokens=800,
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
            'reply_id': reply.id,
            'tone': tone,
            'regen_count': draft.regeneration_count,
        })
        return {
            'success': True,
            'draft_id': draft.id,
            'subject': draft.draft_subject,
            'body': draft.draft_body,
            'reasoning': draft.ai_notes,
        }

    def regenerate_draft(self, draft_id, new_instructions='', tone=None):
        """Produce a fresh draft based on an existing one, with new instructions."""
        try:
            existing = ReplyDraft.objects.get(id=draft_id, owner=self.user)
        except ReplyDraft.DoesNotExist:
            return {'success': False, 'error': 'Draft not found'}
        if existing.status == 'sent':
            return {'success': False, 'error': 'Cannot regenerate a draft that was already sent'}

        combined_context = (existing.generation_prompt + '\n' + new_instructions).strip()
        return self.generate_draft(
            original_email_id=existing.original_email_id,
            user_context=combined_context,
            tone=tone or existing.tone,
            email_account_id=existing.email_account_id,
            parent_draft_id=existing.id,
        )

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
        """Send an approved draft through the shared email service."""
        try:
            draft = ReplyDraft.objects.select_related(
                'lead', 'email_account', 'original_email', 'original_email__triggering_email'
            ).get(id=draft_id, owner=self.user)
        except ReplyDraft.DoesNotExist:
            return {'success': False, 'error': 'Draft not found'}
        if draft.status not in ('approved', 'pending'):
            return {'success': False, 'error': f'Draft is in state "{draft.status}", cannot send'}
        if not draft.lead or not draft.lead.email:
            return {'success': False, 'error': 'Draft has no recipient email'}

        in_reply_to = self._original_message_id(draft.original_email)

        result = email_service.send_raw_email(
            to_email=draft.lead.email,
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
            self.log_action('sent_draft', {'draft_id': draft.id, 'to': draft.lead.email})
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

    def _build_user_prompt(self, reply, user_context, tone):
        lead = reply.lead
        sender_name = ''
        if lead:
            sender_name = ' '.join(filter(None, [lead.first_name, lead.last_name])).strip() or lead.email
        return (
            f"Desired tone: {tone}\n"
            f"Detected interest level: {reply.interest_level or 'unknown'}\n"
            f"Prior AI analysis: {reply.analysis or 'none'}\n"
            f"Sender: {sender_name} <{lead.email if lead else ''}> "
            f"at {lead.company or 'n/a'}\n\n"
            f"INCOMING SUBJECT: {reply.reply_subject}\n"
            f"INCOMING BODY:\n{reply.reply_content}\n\n"
            f"User instructions: {user_context or '(none)'}\n\n"
            "Draft the reply now, returning the JSON object described in the system prompt."
        )

    def _parse_llm_output(self, raw, fallback_subject=''):
        """Extract subject/body/reasoning from the LLM JSON output, tolerant of minor drift."""
        if not raw:
            return '', '', ''
        text = raw.strip()
        # Try direct JSON first
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            # Extract the first {...} block
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                return self._re_prefix(fallback_subject), text, ''
            try:
                data = json.loads(match.group(0))
            except (ValueError, TypeError):
                return self._re_prefix(fallback_subject), text, ''

        subject = (data.get('subject') or fallback_subject or '').strip()
        body = (data.get('body') or '').strip()
        reasoning = (data.get('reasoning') or '').strip()
        return self._re_prefix(subject), body, reasoning

    @staticmethod
    def _re_prefix(subject):
        if not subject:
            return subject
        return subject if subject.lower().startswith('re:') else f'Re: {subject}'

    _ensure_re_prefix = _re_prefix

    def _resolve_email_account(self, email_account_id, reply):
        if email_account_id:
            account = EmailAccount.objects.filter(id=email_account_id, owner=self.user, is_active=True).first()
            if account:
                return account
        qs = EmailAccount.objects.filter(is_active=True)
        if self.user is not None:
            qs = qs.filter(owner=self.user)
        return qs.order_by('-is_default', '-created_at').first()

    @staticmethod
    def _original_message_id(reply):
        """Find the RFC Message-ID of the email we're replying to, for threading."""
        if not reply:
            return None
        triggering = getattr(reply, 'triggering_email', None)
        if triggering and getattr(triggering, 'message_id', None):
            return triggering.message_id
        return None
