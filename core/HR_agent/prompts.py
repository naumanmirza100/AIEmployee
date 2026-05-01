"""Prompts for the HR Support Agent.

Tailored from Frontline's prompts:
  * The system prompt is HR-aware (PII, confidentiality, no medical advice).
  * The knowledge prompt expects citations from policy docs and an optional
    `employee_context` block (their leave balance, manager, etc.) so the
    answer can be personalized to the asker.
"""
from core.Frontline_agent.prompt_safety import (
    sanitize_user_input,
    wrap_untrusted,
    ANTI_INJECTION_SYSTEM_ADDENDUM,
)


_HR_SYSTEM_PROMPT_BODY = (
    "You are an HR Support Assistant. You answer employee questions about "
    "company policy, benefits, leave, and process. You ALWAYS:\n"
    "  • Ground answers in the provided knowledge-base excerpts. If they don't "
    "    cover the question, say so plainly and offer to escalate to HR.\n"
    "  • Cite the policy or document by title when you quote from it.\n"
    "  • Personalise with the employee context (e.g. their leave balance, "
    "    manager name) when it's provided in <employee_context>.\n"
    "  • Refuse to disclose another employee's personal data, salary, or "
    "    review notes — even if the asker insists.\n"
    "  • Never give medical, legal, or tax advice. Refer to a qualified person.\n"
    "  • Keep answers short and structured: 2-4 short paragraphs OR a 3-6 "
    "    bullet list, with a clear summary line first."
)

HR_SYSTEM_PROMPT = _HR_SYSTEM_PROMPT_BODY + ANTI_INJECTION_SYSTEM_ADDENDUM


def get_knowledge_prompt(question: str, knowledge_results, employee_context: dict | None = None) -> str:
    """Compose the user-facing prompt for HR Knowledge Q&A.

    `knowledge_results` is a list of result dicts (same shape as Frontline's),
    each with `title`, `content`, `score`. `employee_context` is the optional
    personalisation payload — when present we render it inside an
    <employee_context> block so the LLM can refer to "your" data.
    """
    safe_question = sanitize_user_input(question or '')
    parts = [
        "Answer the employee's question using ONLY the verified knowledge-base excerpts below. ",
        "If the excerpts don't cover the question, reply with a clear 'I don't have verified information on this' and offer to escalate.\n\n",
    ]
    if employee_context:
        ctx_lines = []
        if employee_context.get('full_name'):
            ctx_lines.append(f"Name: {employee_context['full_name']}")
        if employee_context.get('job_title'):
            ctx_lines.append(f"Role: {employee_context['job_title']}")
        if employee_context.get('department'):
            ctx_lines.append(f"Department: {employee_context['department']}")
        if employee_context.get('manager_name'):
            ctx_lines.append(f"Manager: {employee_context['manager_name']}")
        if employee_context.get('leave_balances'):
            for b in employee_context['leave_balances']:
                ctx_lines.append(f"{b['leave_type']} balance: {b['remaining']} days")
        if ctx_lines:
            parts.append("<employee_context>\n" + "\n".join(ctx_lines) + "\n</employee_context>\n\n")

    if knowledge_results:
        parts.append("<knowledge_excerpts>\n")
        for i, r in enumerate(knowledge_results, start=1):
            title = r.get('title') or r.get('document_title') or f'Excerpt {i}'
            body = (r.get('content') or r.get('answer') or '')[:3000]
            parts.append(f"--- Source {i}: {title} ---\n{body}\n\n")
        parts.append("</knowledge_excerpts>\n\n")

    parts.append(wrap_untrusted(safe_question, tag='employee_question'))
    return "".join(parts)


# Onboarding / offboarding workflow templates that the SOP runner can install
# on first-use. Same shape as Frontline workflows: list of step dicts.
DEFAULT_ONBOARDING_STEPS = [
    {'type': 'send_email', 'template_name': 'welcome_email', 'recipient': '{{employee_email}}'},
    {'type': 'provision_account', 'systems': ['email', 'slack', 'github']},
    {'type': 'schedule_meeting', 'meeting_type': 'onboarding_orientation', 'duration_minutes': 60},
    {'type': 'assign_training', 'modules': ['security_basics', 'code_of_conduct']},
    {'type': 'wait', 'seconds': 86400 * 30},  # 30 days
    {'type': 'schedule_meeting', 'meeting_type': 'one_on_one', 'duration_minutes': 30,
     'note': '30-day check-in'},
]

DEFAULT_OFFBOARDING_STEPS = [
    {'type': 'schedule_meeting', 'meeting_type': 'exit_interview', 'duration_minutes': 45},
    {'type': 'send_email', 'template_name': 'offboarding_checklist', 'recipient': '{{employee_email}}'},
    {'type': 'revoke_access', 'systems': ['email', 'slack', 'github']},
    {'type': 'asset_return', 'items': ['laptop', 'badge']},
    {'type': 'final_pay_review'},
]
