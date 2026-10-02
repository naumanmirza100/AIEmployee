"""How the Recruitment agents call the AI.

They used to have their own Groq-only HTTP client, separate from the shared
BaseAgent that PM, HR and Frontline use: OpenAI keys couldn't be used, its
calls were missing from the LLMUsage log, and every fix to the shared path
(fallback model, auth errors, streaming usage) had to be made twice. The
client below keeps the interface the Recruitment agents call —
send_prompt (a JSON object), send_prompt_text, send_prompt_text_stream,
last_token_usage, GroqClientError — and does the work through BaseAgent.
"""
import json
from typing import Any, Dict, Optional

from project_manager_agent.ai_agents.base_agent import BaseAgent


class GroqClientError(Exception):
    """An AI call failed. (The name predates OpenAI support.)"""

    def __init__(self, message: str, is_auth_error: bool = False, is_rate_limit: bool = False, is_request_too_large: bool = False):
        super().__init__(message)
        self.is_auth_error = is_auth_error  # API key expired/invalid
        self.is_rate_limit = is_rate_limit  # Rate limit exceeded
        self.is_request_too_large = is_request_too_large  # Request exceeds token limit (413)


def _client_error(exc: Exception) -> GroqClientError:
    """A provider SDK error as the GroqClientError the Recruitment agents handle."""
    status = getattr(exc, 'status_code', None) or getattr(getattr(exc, 'response', None), 'status_code', None)
    return GroqClientError(f"AI request failed: {exc}", is_auth_error=status in (401, 403),
                           is_rate_limit=status == 429, is_request_too_large=status == 413)


class RecruitmentAIClient(BaseAgent):
    """The company's AI key for the Recruitment agent, through BaseAgent.

    Keys come from the key service on every call (resolve_for_call), never the
    environment; the quota is counted and each call logged against the
    company, as for the other agents.
    """

    MODEL = 'openai/gpt-oss-20b'      # on Groq; an OpenAI key uses settings.OPENAI_MODEL
    MAX_TOKENS = 2048

    def __init__(self, company_id: Optional[int] = None, model: Optional[str] = None):
        if not company_id:
            raise GroqClientError(
                "No company to call the AI for. Keys come from the platform key service "
                "(resolve_for_call), never from the environment.", is_auth_error=True)
        super().__init__(model=model or self.MODEL)
        self.agent_name = 'Recruitment'
        self.company_id = company_id
        self.agent_key_name = 'recruitment_agent'

    @property
    def last_token_usage(self) -> Optional[Dict]:
        return self.last_llm_usage

    @last_token_usage.setter
    def last_token_usage(self, value):
        self.last_llm_usage = value

    def _text(self, system_prompt: str, text: str, json_mode: bool) -> str:
        from core.api_key_service import KeyServiceError
        try:
            return self._call_llm(text, system_prompt=system_prompt, temperature=0,
                                  max_tokens=self.MAX_TOKENS, json_mode=json_mode) or ''
        except (KeyServiceError, GroqClientError):
            raise
        except Exception as exc:
            raise _client_error(exc) from exc

    def send_prompt(self, system_prompt: str, text: str, max_retries: int = 3) -> Dict[str, Any]:
        """The answer as a JSON object. (Retries are the SDK's.)"""
        message = self._text(system_prompt, text, json_mode=True)
        try:
            return json.loads(message)
        except (TypeError, ValueError) as exc:
            raise GroqClientError(f"Unable to parse the AI's JSON answer: {exc}") from exc

    def send_prompt_text(self, system_prompt: str, text: str, max_retries: int = 3) -> str:
        """The answer as plain text, for long or free-form output."""
        return self._text(system_prompt, text, json_mode=False).strip()

    def send_prompt_text_stream(self, system_prompt: str, text: str, max_retries: int = 3):
        """`send_prompt_text`, as it is written: yields pieces of the answer.
        An error before any text raises GroqClientError (or a key-service
        error) like the plain call; usage is charged however the stream ends."""
        for event in self._call_llm_stream(text, system_prompt=system_prompt, temperature=0,
                                           max_tokens=self.MAX_TOKENS):
            kind = event.get('type')
            if kind == 'token':
                yield event['value']
            elif kind == 'error':
                raise GroqClientError(f"AI request failed: {event.get('message')}")


# The name the Recruitment agents' type hints use.
GroqClient = RecruitmentAIClient
