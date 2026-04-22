"""
Base Agent Class for AI Project Manager
All AI agents inherit from this base class
"""

try:
    from groq import Groq
except ImportError:
    raise ImportError("groq library not installed. Run: pip install --upgrade groq")

from django.conf import settings
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# Rough prices in USD per 1M tokens (input, output). Update as providers change pricing.
# Used only for approximate cost tracking. Unknown models fall back to _DEFAULT_PRICE_PER_MTOK.
_PRICE_PER_MTOK = {
    'llama-3.1-8b-instant': (0.05, 0.08),
    'llama-3.3-70b-versatile': (0.59, 0.79),
    'llama-3.1-70b-versatile': (0.59, 0.79),
    'mixtral-8x7b-32768': (0.24, 0.24),
    'gemma2-9b-it': (0.20, 0.20),
}
_DEFAULT_PRICE_PER_MTOK = (0.50, 0.50)


def _estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Cheap best-effort $ estimate. Returns Decimal with 6 dp for the DB field."""
    in_price, out_price = _PRICE_PER_MTOK.get(model or '', _DEFAULT_PRICE_PER_MTOK)
    cost = ((prompt_tokens or 0) * in_price + (completion_tokens or 0) * out_price) / 1_000_000.0
    return Decimal(str(round(cost, 6)))


def _record_llm_usage(*, company_id, agent_name, model, usage_dict, duration_ms, success):
    """Persist a single LLM call row. Silent no-op if company_id is missing or the
    write fails — cost tracking must never break the request."""
    if not company_id:
        return
    try:
        prompt_tokens = int((usage_dict or {}).get('prompt_tokens') or 0)
        completion_tokens = int((usage_dict or {}).get('completion_tokens') or 0)
        total_tokens = int((usage_dict or {}).get('total_tokens') or (prompt_tokens + completion_tokens))
        cost = _estimate_cost_usd(model, prompt_tokens, completion_tokens)
        # Local import — avoids loading Django models at module import time
        from Frontline_agent.models import LLMUsage
        LLMUsage.objects.create(
            company_id=company_id,
            agent_name=agent_name or 'unknown',
            model=model or 'unknown',
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=int(duration_ms or 0),
            success=bool(success),
            estimated_cost_usd=cost,
        )
    except Exception as exc:
        logger.warning("LLM usage tracking failed: %s", exc)


class BaseAgent:
    """
    Base class for all AI agents in the Project Manager system.
    Provides common functionality like Groq API integration and logging.
    """
    
    def __init__(self, model=None):
        """
        Initialize the base agent with Groq API client.
        
        Args:
            model (str): Groq model to use. Defaults to settings.GROQ_MODEL
        """
        self.api_key = getattr(settings, 'GROQ_API_KEY', None)
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables. Please set it in .env file.")
        
        try:
            # Simple initialization - just pass api_key
            # Some versions of groq may have issues with extra arguments
            self.client = Groq(api_key=self.api_key)
        except TypeError as e:
            error_msg = str(e)
            if 'proxies' in error_msg or 'unexpected keyword' in error_msg:
                # This usually means the groq library version is incompatible
                logger.error(f"Groq client initialization error: {e}")
                logger.error("This is usually caused by an outdated groq library version.")
                logger.error("Please run: pip install --upgrade groq")
                raise ValueError(
                    f"Groq client initialization failed. "
                    f"This is likely due to an incompatible groq library version. "
                    f"Please update it: pip install --upgrade groq. "
                    f"Original error: {e}"
                )
            else:
                raise
        except Exception as e:
            logger.error(f"Unexpected error initializing Groq client: {e}")
            raise ValueError(f"Failed to initialize Groq client: {e}")
        
        self.agent_name = self.__class__.__name__
        self.fallback_model = getattr(settings, 'GROQ_FALLBACK_MODEL', 'llama-3.3-70b-versatile')

        # Load per-agent config from settings
        agent_config = getattr(settings, 'PM_AGENT_LLM_CONFIG', {})
        defaults = agent_config.get('defaults', {})
        agent_overrides = agent_config.get(self.agent_name.lower(), {})

        self.model = model or agent_overrides.get('model') or defaults.get('model') or getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant')
        self.default_temperature = agent_overrides.get('temperature') or defaults.get('temperature', 0.7)
        self.default_max_tokens = agent_overrides.get('max_tokens') or defaults.get('max_tokens', 1024)

        # Store last token usage from Groq API calls (if available)
        self.last_llm_usage = None
        # Cumulative token tracking for this agent instance
        self.total_tokens_used = 0
    
    def _resolve_company_client(self):
        """If the agent has a company_id + agent_key_name set, route through
        the key/quota resolver. Returns (client, ctx) or (None, None) to fall
        back to the default Groq env-key client. Raises on hard-block so the
        view layer can surface a 402/403."""
        company_id = getattr(self, 'company_id', None)
        agent_key_name = getattr(self, 'agent_key_name', None)
        if not company_id or not agent_key_name:
            return None, None
        try:
            from core.models import Company
            from core.api_key_service import resolve_for_call
            company = Company.objects.get(pk=company_id)
            ctx = resolve_for_call(company, agent_key_name)
        except Exception:
            raise  # QuotaExhausted / NoKeyAvailable / Company.DoesNotExist — let the view handle
        try:
            if ctx.provider == 'groq':
                from groq import Groq
                return Groq(api_key=ctx.api_key), ctx
            # Provider mismatch (e.g. admin set an openai key but agent speaks groq):
            # fall back to env so we don't silently use a wrong-protocol client.
            logger.warning("PM agent got non-groq key (%s); falling back to env", ctx.provider)
            return None, None
        except Exception as e:
            logger.warning("Failed to build client from resolved key: %s — using env fallback", e)
            return None, None

    def _call_llm(self, prompt, system_prompt=None, temperature=0.7, max_tokens=1024):
        """
        Make a call to the Groq LLM API.

        Args:
            prompt (str): User prompt/question
            system_prompt (str): System prompt for context
            temperature (float): Sampling temperature (0-1)
            max_tokens (int): Maximum tokens in response

        Returns:
            str: LLM response text
        """
        import time as _time
        _start = _time.time()
        client, key_ctx = self._resolve_company_client()
        call_client = client or self.client
        try:
            messages = []

            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })

            messages.append({
                "role": "user",
                "content": prompt
            })

            response = call_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Capture token usage information if the client provides it
            usage_info = getattr(response, "usage", None)
            usage_dict = None
            if usage_info is not None:
                try:
                    # usage might be a dict-like or an object with attributes
                    prompt_tokens = getattr(usage_info, "prompt_tokens", None)
                    completion_tokens = getattr(usage_info, "completion_tokens", None)
                    total_tokens = getattr(usage_info, "total_tokens", None)
                    # If it's a plain dict, getattr will return None; fall back to dict access
                    if isinstance(usage_info, dict):
                        prompt_tokens = usage_info.get("prompt_tokens", prompt_tokens)
                        completion_tokens = usage_info.get("completion_tokens", completion_tokens)
                        total_tokens = usage_info.get("total_tokens", total_tokens)
                    usage_dict = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    }
                except Exception:
                    usage_dict = None
            
            self.last_llm_usage = usage_dict
            if usage_dict and usage_dict.get('total_tokens'):
                self.total_tokens_used += usage_dict['total_tokens']

            elapsed = round(_time.time() - _start, 2)
            tokens = usage_dict.get('total_tokens', '?') if usage_dict else '?'
            logger.info(f"[LLM] {self.agent_name} | {elapsed}s | {tokens} tokens | model={self.model}")
            if elapsed > 5:
                logger.warning(f"[LLM SLOW] {self.agent_name} took {elapsed}s (>5s threshold)")

            # Per-tenant usage tracking (opt-in: agent sets self.company_id)
            _record_llm_usage(
                company_id=getattr(self, 'company_id', None),
                agent_name=self.agent_name,
                model=self.model,
                usage_dict=usage_dict,
                duration_ms=int((_time.time() - _start) * 1000),
                success=True,
            )

            # Decrement per-agent token quota if we used a resolved key
            if key_ctx and usage_dict and usage_dict.get('total_tokens'):
                try:
                    from core.api_key_service import record_usage
                    record_usage(key_ctx, usage_dict['total_tokens'])
                except Exception as e:
                    logger.warning("quota decrement failed: %s", e)

            return response.choices[0].message.content

        except Exception as e:
            # Record the failed attempt before attempting fallback
            _record_llm_usage(
                company_id=getattr(self, 'company_id', None),
                agent_name=self.agent_name,
                model=self.model,
                usage_dict=None,
                duration_ms=int((_time.time() - _start) * 1000),
                success=False,
            )
            # Try fallback model if primary fails
            if self.fallback_model and self.fallback_model != self.model:
                logger.warning(f"{self.agent_name}: Primary model '{self.model}' failed ({e}), trying fallback '{self.fallback_model}'")
                _fallback_start = _time.time()
                try:
                    response = call_client.chat.completions.create(
                        model=self.fallback_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    # Best-effort usage capture for the fallback call too
                    fb_usage_info = getattr(response, "usage", None)
                    fb_usage_dict = None
                    if fb_usage_info is not None:
                        try:
                            fb_usage_dict = {
                                "prompt_tokens": getattr(fb_usage_info, "prompt_tokens", None),
                                "completion_tokens": getattr(fb_usage_info, "completion_tokens", None),
                                "total_tokens": getattr(fb_usage_info, "total_tokens", None),
                            }
                        except Exception:
                            fb_usage_dict = None
                    _record_llm_usage(
                        company_id=getattr(self, 'company_id', None),
                        agent_name=self.agent_name,
                        model=self.fallback_model,
                        usage_dict=fb_usage_dict,
                        duration_ms=int((_time.time() - _fallback_start) * 1000),
                        success=True,
                    )
                    if key_ctx and fb_usage_dict and fb_usage_dict.get('total_tokens'):
                        try:
                            from core.api_key_service import record_usage
                            record_usage(key_ctx, fb_usage_dict['total_tokens'])
                        except Exception as e:
                            logger.warning("quota decrement failed on fallback: %s", e)
                    return response.choices[0].message.content
                except Exception as fallback_err:
                    logger.error(f"{self.agent_name}: Fallback model also failed: {fallback_err}")
                    _record_llm_usage(
                        company_id=getattr(self, 'company_id', None),
                        agent_name=self.agent_name,
                        model=self.fallback_model,
                        usage_dict=None,
                        duration_ms=int((_time.time() - _fallback_start) * 1000),
                        success=False,
                    )
                    raise
            logger.error(f"Error in {self.agent_name} LLM call: {str(e)}")
            raise
    
    def log_action(self, action, details=None):
        """
        Log agent actions for debugging and monitoring.
        
        Args:
            action (str): Action description
            details (dict): Additional details
        """
        logger.info(f"{self.agent_name}: {action}")
        if details:
            logger.debug(f"{self.agent_name} details: {details}")
    
    def validate_input(self, **kwargs):
        """
        Validate input parameters. Override in subclasses.
        
        Args:
            **kwargs: Input parameters to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        return True
    
    def process(self, **kwargs):
        """
        Main processing method. Must be implemented by subclasses.
        
        Args:
            **kwargs: Agent-specific parameters
            
        Returns:
            dict: Processing results
        """
        raise NotImplementedError("Subclasses must implement process() method")

