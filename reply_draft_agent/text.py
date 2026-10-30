"""Email text as the AI is given it: the sender's own words, cut to a size.

The whole stored body went to the model, quoted history and all, and mail with only an HTML part kept the contents
of its style blocks; long threads and newsletters made requests past the model's limit and the draft simply failed
(CO-249). Every prompt of the agent takes its email text from here.
"""
import json
import re

# Big enough for a long business email; a newsletter or a thread with its history is cut.
BODY_LIMIT = 8000
SHORTENED = '\n[… the rest of this email was cut]'


def own_words(text: str) -> str:
    """The message without the earlier thread it quotes; the message as it is when nothing is left."""
    from ai_sdr_agent.agents.email_assistant_agent import strip_quoted_reply
    text = text or ''
    stripped = strip_quoted_reply(text)
    return stripped if stripped.strip() else text.strip()


def for_ai(text: str, limit: int = BODY_LIMIT) -> str:
    """The sender's words, with blank runs folded, cut to `limit` characters and marked when cut."""
    body = re.sub(r'\n\s*\n\s*\n+', '\n\n', re.sub(r'[ \t\r\f\v]+', ' ', own_words(text))).strip()
    if len(body) > limit:
        return body[:limit].rstrip() + SHORTENED
    return body


def parse_json(raw: str) -> dict:
    """The JSON object in the AI's answer, also when it is wrapped in a code fence or a sentence. ValueError when
    there is none. The agent's AI call has no JSON mode, so the prompts ask for JSON and this reads it."""
    text = (raw or '').strip()
    fence = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end < start:
        raise ValueError(f'no JSON in the answer: {text[:120]}')
    return json.loads(text[start:end + 1], strict=False)


def ai_json(agent, *, prompt, system_prompt, temperature=0, max_tokens=500) -> dict:
    """Ask the agent's AI and read its JSON answer."""
    return parse_json(agent._call_llm(prompt=prompt, system_prompt=system_prompt, temperature=temperature,
                                      max_tokens=max_tokens))
