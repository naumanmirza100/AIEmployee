"""
Frontline Agent Prompts
Enterprise-level prompts that enforce strict data-only responses
"""
import logging

from django.conf import settings

from .prompt_safety import (
    sanitize_user_input,
    wrap_untrusted,
    wrap_untrusted_list,
    ANTI_INJECTION_SYSTEM_ADDENDUM,
)

logger = logging.getLogger(__name__)


# Whose assistant it is. It said "a Frontline Support AI Agent for PayPerProject, an enterprise project management
# platform" for every company, so a company's own customers were told they were talking to PayPerProject.
_FRONTLINE_SYSTEM_PROMPT_BODY = """You are the customer support assistant of {company}. You answer {company}'s customers from {company}'s own help documents.

CRITICAL RULES - YOU MUST FOLLOW THESE STRICTLY:
1. YOU MUST ONLY use information provided by the knowledge base APIs. NEVER guess, assume, or make up information.
2. If no verified information is found in the database, you MUST respond with: "I couldn't find this in our help documents, so I can't answer it reliably. You can ask to talk to a person, and someone from our team will help you."
3. NEVER provide information that wasn't explicitly returned by the API calls.
4. NEVER make assumptions about user accounts, payments, or system status.
5. If you're unsure or don't have data, say so plainly; the customer can ask to talk to a person.
5a. Reply in the language the customer wrote in: English, or Roman Urdu when they wrote in Roman Urdu.
6. RESPONSE TONE: You MUST maintain a consistent, highly professional, empathetic, and reassuring tone at all times. Use clear, simple language without jargon, and structure your responses clearly without being overly robotic.
7. When providing information, cite the source (e.g., "According to our knowledge base...").
8. For step-by-step instructions, only provide steps that are in the verified knowledge base.

YOUR CAPABILITIES:
- Answer FAQs from the knowledge base
- Provide step-by-step guidance from verified documentation
- Explain policies and procedures from the database
- Classify and route tickets appropriately
- Auto-resolve only predefined, low-complexity issues
- Escalate complex or urgent issues to human agents

YOUR LIMITATIONS:
- You cannot access user accounts directly
- You cannot process payments or refunds
- You cannot modify system settings
- You cannot provide information not in the knowledge base
- You cannot guess answers

Remember: Your primary goal is to help users with verified information and route complex issues to human experts."""

# Exported system prompt includes the anti-injection addendum. With no company known, "our company".
FRONTLINE_SYSTEM_PROMPT = _FRONTLINE_SYSTEM_PROMPT_BODY.format(company='our company') + ANTI_INJECTION_SYSTEM_ADDENDUM


def frontline_system_prompt(company_name=None):
    """The system prompt in the voice of `company_name` (the company whose customers are asking)."""
    name = (company_name or '').strip() or 'our company'
    return _FRONTLINE_SYSTEM_PROMPT_BODY.format(company=name) + ANTI_INJECTION_SYSTEM_ADDENDUM


FRONTLINE_KNOWLEDGE_PROMPT = """Answer the user's question from the document snippets below.

DOCUMENT CONTENT (SNIPPETS):
{knowledge_results}

USER QUESTION: {user_question}

RULES:
1. Use ONLY the provided snippets. No outside knowledge.
2. Answer the specific question thoroughly — cover every detail present in the snippets that's relevant, including numbers, dates, categories, conditions, and exceptions. Do NOT invent unrelated topics.
3. Structure the answer for readability:
   • Open with a one-sentence direct answer.
   • Then a **Details** section with short paragraphs OR a bulleted list of the key points.
   • If the snippets describe a process, categories, or eligibility rules, use a bulleted or numbered list — one bullet per item, with a short explanation.
   • End with a **Notes / Caveats** line only if the snippets mention conditions, exceptions, or "subject to" phrasing worth surfacing.
4. If the snippets don't contain the answer, say exactly: "I couldn't find this in our help documents, so I can't answer it reliably. You can ask to talk to a person, and someone from our team will help you."
4a. Reply in the language of the question: English, or Roman Urdu when it is written in Roman Urdu.
5. NO preamble. NO meta-commentary like "Based on the provided document snippets…" or "According to the document content…" — just answer directly.
6. NO verbatim block-quotes of the snippet content — paraphrase in your own words. Short quotes (< 15 words) are fine when precision matters.
7. Professional, empathetic tone. No slang, no robotic phrasing.

RESPONSE:"""


# The website chat's answer. FRONTLINE_KNOWLEDGE_PROMPT's report layout ("Details", "Notes / Caveats", every detail)
# suits the team's Knowledge Q&A; on the chat (live, 27 Oct) it gave customers 250-word reports, and a customer whose
# site was down was told to "contact us on the chat" while on it.
FRONTLINE_CUSTOMER_CHAT_PROMPT = """A customer wrote this on the company's website chat. Answer from the help-document passages below.

PASSAGES:
{knowledge_results}

CUSTOMER'S MESSAGE: {user_question}

RULES:
1. Use ONLY the passages. No outside knowledge.
2. Write as the company's chat ("we", "our plans"). Never mention documents, passages, guides, a knowledge base, pages or sources, and add no line about where the answer comes from.
3. Keep it short: answer in one or two sentences first. Add a short bulleted list only when there are several items (plans, steps, options), about 120 words in all. No headings, no "Details" or "Notes" sections.
4. Give what was asked. Add a condition or exception only when it changes the answer.
5. The customer is already on our chat: never tell them to contact us by chat. When they report a problem, answer in two or three sentences, with no list: how quickly we reply to and fix a problem like theirs, and what details help us (which page, a screenshot). Our team is told separately.
6. If the passages don't contain the answer, say exactly: "I couldn't find this in our help documents, so I can't answer it reliably. You can ask to talk to a person, and someone from our team will help you."
7. Reply in the customer's language: English, or Roman Urdu when they wrote in Roman Urdu.
8. Friendly and professional. No preamble.

RESPONSE:"""


FRONTLINE_TICKET_PROMPT ="""A user has submitted the following support request:

TITLE: {ticket_title}
DESCRIPTION: {ticket_description}

CLASSIFICATION RESULTS:
- Category: {category}
- Priority: {priority}
- Auto-resolvable: {auto_resolvable}
- Should escalate: {should_escalate}
- Confidence: {confidence}

KNOWLEDGE BASE MATCHES (if any):
{knowledge_matches}

INSTRUCTIONS:
1. If auto-resolvable is True and knowledge base has a solution:
   - Provide the solution from the knowledge base
   - Mark ticket as auto-resolved
   - Include the resolution in your response

2. If auto-resolvable is False or should_escalate is True:
   - Acknowledge the issue
   - Inform the user that a human agent will review their ticket
   - Provide ticket ID for reference
   - Do NOT attempt to resolve complex issues

3. NEVER guess solutions. Only use information from the knowledge base.
4. TONE: Respond with a consistent, professional, empathetic, and reassuring tone. Do not sound robotic, but avoid overly casual slang.

RESPONSE:"""


FRONTLINE_AUTO_RESOLVE_PROMPT = """You are processing a ticket that has been classified as auto-resolvable.

TICKET INFORMATION:
- Title: {ticket_title}
- Description: {ticket_description}
- Category: {category}
- Priority: {priority}

VERIFIED SOLUTION FROM KNOWLEDGE BASE:
{solution}

INSTRUCTIONS:
1. Provide a clear, helpful response using ONLY the verified solution above.
2. If no solution is provided, you MUST escalate to human agent (do not guess).
3. TONE: Respond with a consistent, highly professional, polite, and reassuring tone. Ensure the customer feels supported while reading the solution.
4. Include next steps if applicable.

RESPONSE:"""


def get_knowledge_prompt(user_question: str, knowledge_results: list, for_customer: bool = False) -> str:
    """
    Generate knowledge-based prompt for the agent.

    Args:
        user_question: User's question
        knowledge_results: List of knowledge base results (can be from get_answer or search_knowledge)
        for_customer: the website chat's short reply in the company's voice, not the team's full answer

    Returns:
        Formatted prompt string
    """
    if not knowledge_results:
        knowledge_text = "No matching information found in knowledge base."
    else:
        knowledge_items = []
        # Top 8 by default, not 5: retrieval is now allowed to return 10, and
        # silently dropping half of them here made "list every X" questions
        # answer from a fraction of the document. Tunable via
        # FRONTLINE_QA_PROMPT_SOURCES.
        _max_sources = int(getattr(settings, 'FRONTLINE_QA_PROMPT_SOURCES', 8))
        for idx, result in enumerate(knowledge_results[:_max_sources], 1):
            item_text = f"\n{idx}. "
            
            # Handle format from get_answer (has 'answer' key directly)
            if 'answer' in result and 'type' in result:
                # This is from get_answer - it already has the answer content
                answer_content = result.get('answer', '')
                source = result.get('source', 'Unknown')
                doc_type = result.get('type', 'unknown')
                
                # This string is every retrieved chunk joined together, so the
                # cap decides how much of the document the model actually sees.
                # 6000 was sized for 1200-char chunks; FRONTLINE_CHUNK_SIZE is
                # now 4000, so 6000 chars discarded most of a 10-chunk
                # retrieval and broke "list all X" answers. 24000 chars is
                # ~6k tokens — comfortable for gpt-4.1-mini's window.
                # Tunable via FRONTLINE_QA_CONTEXT_CHARS.
                _ctx_cap = int(getattr(settings, 'FRONTLINE_QA_CONTEXT_CHARS', 24000))
                if len(answer_content) > _ctx_cap:
                    answer_content = (
                        answer_content[:_ctx_cap]
                        + f'\n\n[... truncated at {_ctx_cap} chars — {len(answer_content) - _ctx_cap} '
                          'more characters were retrieved but not shown. Say so if the '
                          'answer looks incomplete rather than implying it is exhaustive.]'
                    )

                item_text += f"Source: {source}\n   Type: {doc_type}\n   Content Length: {len(answer_content)} chars\n\nDocument Content:\n{answer_content}"
            
            # Handle format from search_knowledge (has 'question' or 'title' keys)
            elif 'question' in result:
                item_text += f"Q: {result.get('question', 'N/A')}\n   A: {result.get('answer', 'N/A')}"
            elif 'title' in result:
                content = result.get('content', 'N/A')
                # Cap per-excerpt at 2000 chars so the LLM sees a full 1200-char
                # chunk with margin — enough to synthesize detailed answers.
                if len(content) > 2000:
                    content_preview = content[:2000] + '...'
                else:
                    content_preview = content
                similarity = result.get('similarity_score', 'N/A')
                item_text += f"Title: {result.get('title', 'N/A')}\n   Similarity Score: {similarity}\n   Content: {content_preview}"
            else:
                # Fallback: try to extract any available information
                item_text += f"Result: {str(result)[:500]}"
            
            knowledge_items.append(item_text)
        knowledge_text = "\n".join(knowledge_items)
    
    # Wrap the user's question in a tagged block so the model can tell data from
    # instructions; sanitize first to scrub obvious injection phrases + invisible chars.
    safe_question = sanitize_user_input(user_question, max_len=4000)
    wrapped_question = wrap_untrusted(safe_question, tag='user_question')

    template = FRONTLINE_CUSTOMER_CHAT_PROMPT if for_customer else FRONTLINE_KNOWLEDGE_PROMPT
    return template.format(
        knowledge_results=knowledge_text,
        user_question=wrapped_question,
    )


def get_ticket_prompt(ticket_data: dict, classification: dict, knowledge_matches: list = None) -> str:
    """
    Generate ticket processing prompt for the agent.
    
    Args:
        ticket_data: Ticket information (title, description)
        classification: Classification results
        knowledge_matches: Optional knowledge base matches
        
    Returns:
        Formatted prompt string
    """
    if not knowledge_matches:
        knowledge_text = "No matching solutions found in knowledge base."
    else:
        knowledge_items = []
        for idx, match in enumerate(knowledge_matches[:3], 1):
            item_text = f"\n{idx}. "
            if 'answer' in match:
                item_text += f"{match.get('answer', 'N/A')}"
            elif 'content' in match:
                item_text += f"{match.get('content', 'N/A')[:300]}"
            knowledge_items.append(item_text)
        knowledge_text = "\n".join(knowledge_items)
    
    return FRONTLINE_TICKET_PROMPT.format(
        ticket_title=ticket_data.get('title', 'N/A'),
        ticket_description=ticket_data.get('description', 'N/A'),
        category=classification.get('category', 'other'),
        priority=classification.get('priority', 'medium'),
        auto_resolvable=classification.get('auto_resolvable', False),
        should_escalate=classification.get('should_escalate', False),
        confidence=classification.get('confidence', 0.0),
        knowledge_matches=knowledge_text
    )
