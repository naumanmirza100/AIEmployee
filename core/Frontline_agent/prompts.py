"""
Frontline Agent Prompts
Enterprise-level prompts that enforce strict data-only responses
"""
import logging

from .prompt_safety import (
    sanitize_user_input,
    wrap_untrusted,
    wrap_untrusted_list,
    ANTI_INJECTION_SYSTEM_ADDENDUM,
)

logger = logging.getLogger(__name__)


_FRONTLINE_SYSTEM_PROMPT_BODY = """You are a Frontline Support AI Agent for PayPerProject, an enterprise project management platform.

CRITICAL RULES - YOU MUST FOLLOW THESE STRICTLY:
1. YOU MUST ONLY use information provided by the knowledge base APIs. NEVER guess, assume, or make up information.
2. If no verified information is found in the database, you MUST respond with: "I don't have verified information about this topic in our knowledge base. Let me create a ticket for a human agent to assist you."
3. NEVER provide information that wasn't explicitly returned by the API calls.
4. NEVER make assumptions about user accounts, payments, or system status.
5. If you're unsure or don't have data, ALWAYS escalate to human agents.
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

# Exported system prompt includes the anti-injection addendum.
FRONTLINE_SYSTEM_PROMPT = _FRONTLINE_SYSTEM_PROMPT_BODY + ANTI_INJECTION_SYSTEM_ADDENDUM


FRONTLINE_KNOWLEDGE_PROMPT = """Answer the user's question from the document snippets below.

DOCUMENT CONTENT (SNIPPETS):
{knowledge_results}

USER QUESTION: {user_question}

RULES:
1. Use ONLY the provided snippets. No outside knowledge.
2. Answer the specific question — do NOT copy the whole document or list unrelated topics.
3. If the snippets don't contain the answer, say exactly: "I don't have verified information about this in our knowledge base. Let me create a ticket for a human agent to assist you."
4. NO preamble. NO meta-commentary like "Based on the provided document snippets…" or "According to the document content…" — just answer directly.
5. NO verbatim block-quotes of the snippet content — paraphrase concisely. It's fine to quote a short phrase (< 15 words) when precision matters.
6. Keep it short: 1-3 sentences, or a tight 3-5 bullet list. Structure only when the answer is genuinely a list.
7. Professional, empathetic tone. No slang, no robotic phrasing.

RESPONSE:"""


FRONTLINE_TICKET_PROMPT = """A user has submitted the following support request:

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


def get_knowledge_prompt(user_question: str, knowledge_results: list) -> str:
    """
    Generate knowledge-based prompt for the agent.
    
    Args:
        user_question: User's question
        knowledge_results: List of knowledge base results (can be from get_answer or search_knowledge)
        
    Returns:
        Formatted prompt string
    """
    if not knowledge_results:
        knowledge_text = "No matching information found in knowledge base."
    else:
        knowledge_items = []
        for idx, result in enumerate(knowledge_results[:5], 1):  # Limit to top 5
            item_text = f"\n{idx}. "
            
            # Handle format from get_answer (has 'answer' key directly)
            if 'answer' in result and 'type' in result:
                # This is from get_answer - it already has the answer content
                answer_content = result.get('answer', '')
                source = result.get('source', 'Unknown')
                doc_type = result.get('type', 'unknown')
                
                # Cap at 3500 chars. Prompt size is the single biggest lever
                # on time-to-first-token for large docs — 3500 comfortably
                # covers 2-3 chunks of substantive content.
                if len(answer_content) > 3500:
                    answer_content = answer_content[:3500] + '\n\n[... content truncated ...]'

                item_text += f"Source: {source}\n   Type: {doc_type}\n   Content Length: {len(answer_content)} chars\n\nDocument Content:\n{answer_content}"
            
            # Handle format from search_knowledge (has 'question' or 'title' keys)
            elif 'question' in result:
                item_text += f"Q: {result.get('question', 'N/A')}\n   A: {result.get('answer', 'N/A')}"
            elif 'title' in result:
                content = result.get('content', 'N/A')
                # Cap per-excerpt at 800 chars — plenty for the LLM to answer
                # a specific question, and keeps TTFT low.
                if len(content) > 800:
                    content_preview = content[:800] + '...'
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

    return FRONTLINE_KNOWLEDGE_PROMPT.format(
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
