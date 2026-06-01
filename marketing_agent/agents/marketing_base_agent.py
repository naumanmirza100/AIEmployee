"""
Marketing Base Agent Class
Uses Groq API for Q&A and OpenAI API (optional) for advanced tasks
Separate from core BaseAgent to avoid disrupting existing system
"""

try:
    from groq import Groq
except ImportError:
    raise ImportError("groq library not installed. Run: pip install --upgrade groq")

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # Optional - only needed for document writing

import os
import time
import re
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class MarketingBaseAgent:
    """
    Base class for all Marketing AI agents.
    Uses Groq API for Q&A and OpenAI API (optional) for advanced tasks.
    
    Model Selection:
    - Reasoning/Q&A: Groq (llama-3.1-8b-instant or other Groq models)
    - Document Writing: OpenAI GPT-4.1 (optional, if API key provided)
    - Embeddings (RAG): OpenAI text-embedding-3-large (optional, if API key provided)
    """
    
    def __init__(self, model=None, use_embeddings=False):
        """
        Initialize the marketing base agent.

        Keys are NEVER read from environment variables or Django settings here.
        All LLM calls go through _resolve_company_client() which calls
        resolve_for_call(company, agent_key_name) — the only authorised key source.
        Set self.company_id and self.agent_key_name before any LLM call.
        """
        # No env-key pre-loading. groq_client / openai_client are created lazily
        # per-call inside _resolve_company_client when company_id is set.
        self.groq_client = None   # legacy attribute; not used in the per-company path
        self.openai_client = None  # legacy attribute; not used in the per-company path
        self.groq_api_key = ''     # intentionally empty — never read from env
        self.openai_api_key = ''   # intentionally empty — never read from env

        # Model selection based on use case
        if use_embeddings:
            self.embedding_model = getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-large')
            self.model = None
        else:
            self.model = model or 'llama-3.1-8b-instant'
            self.embedding_model = None

        self.agent_name = self.__class__.__name__
        self.last_token_usage = None
        self.last_llm_used = False

    def _resolve_company_client(self):
        """Opt-in per-company key + quota routing. Subclass instances can set
        `self.company_id` and `self.agent_key_name` (e.g. 'marketing_agent') to
        enable the BYOK / platform-key flow. Returns (client, ctx) or (None,
        None) when no routing applies. Hard-blocks (QuotaExhausted,
        NoKeyAvailable) propagate. Never falls back to env key when company_id
        is set — raises ValueError for unsupported providers."""
        company_id = getattr(self, 'company_id', None)
        agent_key_name = getattr(self, 'agent_key_name', None)
        if not company_id or not agent_key_name:
            return None, None
        from core.models import Company
        from core.api_key_service import resolve_for_call
        company = Company.objects.get(pk=company_id)
        ctx = resolve_for_call(company, agent_key_name)
        if ctx.provider == 'groq':
            from groq import Groq
            return Groq(api_key=ctx.api_key), ctx
        if ctx.provider == 'openai':
            from openai import OpenAI
            return OpenAI(api_key=ctx.api_key), ctx
        raise ValueError(f"Unsupported provider '{ctx.provider}' configured for company key")
    
    def _call_llm(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2000, model=None):
        """
        Make a call to the LLM API (Groq for Q&A, OpenAI for advanced tasks).
        
        Args:
            prompt (str): User prompt/question
            system_prompt (str): System prompt for context
            temperature (float): Sampling temperature (0-2)
            max_tokens (int): Maximum tokens in response
            model (str): Override model for this call
            
        Returns:
            str: LLM response text
        """
        # Route through _call_groq_qa which handles provider-agnostic resolution.
        # _call_openai is only used when caller explicitly requests a GPT model
        # AND no company key overrides the provider choice.
        company_id = getattr(self, 'company_id', None)
        if not company_id and self.openai_client and model and 'gpt' in model.lower():
            return self._call_openai(prompt, system_prompt, temperature, max_tokens, model)
        return self._call_groq_qa(prompt, system_prompt, temperature, max_tokens)
    
    def _call_openai(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2000, model=None):
        """
        Make a call to the OpenAI LLM API (for document writing and advanced tasks).

        Args:
            prompt (str): User prompt/question
            system_prompt (str): System prompt for context
            temperature (float): Sampling temperature (0-2)
            max_tokens (int): Maximum tokens in response
            model (str): Override model for this call

        Returns:
            str: LLM response text
        """
        resolved_client, key_ctx = self._resolve_company_client()
        if resolved_client is not None:
            call_client = resolved_client
            if key_ctx.provider == 'groq':
                model_to_use = model or self.model or getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant')
            else:
                model_to_use = model or getattr(settings, 'OPENAI_MODEL', 'gpt-4.1')
        else:
            # company_id/agent_key_name not set — fail; never fall back to env key
            call_client = None
            model_to_use = model or getattr(settings, 'OPENAI_MODEL', 'gpt-4.1')
        if not call_client:
            raise ValueError(
                "No API key available for OpenAI call. Set self.company_id and self.agent_key_name "
                "so the platform key service can resolve the correct key. "
                "Keys are never read from environment variables."
            )

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
                model=model_to_use,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            usage = getattr(response, 'usage', None)
            content = response.choices[0].message.content
            self.last_llm_used = True

            prompt_text = ''
            try:
                prompt_text = '\n'.join([m.get('content', '') for m in messages if isinstance(m, dict)])
            except Exception:
                prompt_text = ''

            prompt_tokens = getattr(usage, 'prompt_tokens', None) if usage else None
            completion_tokens = getattr(usage, 'completion_tokens', None) if usage else None
            total_tokens = getattr(usage, 'total_tokens', None) if usage else None
            estimated = False

            if total_tokens is None:
                estimated = True
                def _est_tokens(t: str) -> int:
                    t = t or ''
                    return max(1, int(len(t) / 4))
                if prompt_tokens is None:
                    prompt_tokens = _est_tokens(prompt_text)
                if completion_tokens is None:
                    completion_tokens = _est_tokens(content)
                total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

            self.last_token_usage = {
                'provider': key_ctx.provider if key_ctx else 'openai',
                'model': model_to_use,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'estimated': estimated,
            }
            if key_ctx and total_tokens:
                try:
                    from core.api_key_service import record_usage
                    record_usage(key_ctx, total_tokens)
                except Exception as e:
                    logger.warning("marketing quota decrement failed: %s", e)

            return content

        except Exception as e:
            logger.error(f"Error in {self.agent_name} OpenAI LLM call: {str(e)}")
            from core.api_key_service import raise_if_auth_error
            raise_if_auth_error(e, key_ctx)
            raise
    
    def _get_embeddings(self, text, model=None):
        """
        Get embeddings for text using OpenAI embeddings API.
        
        Args:
            text (str or list): Text(s) to embed
            model (str): Embedding model to use
            
        Returns:
            list: Embedding vectors
        """
        resolved_client, key_ctx = self._resolve_company_client()
        if resolved_client is not None:
            if key_ctx.provider != 'openai':
                raise ValueError(
                    f"Embeddings require an OpenAI key; company has '{key_ctx.provider}' key configured."
                )
            emb_client = resolved_client
        else:
            emb_client = self.openai_client
        if not emb_client:
            raise ValueError(
                "No OpenAI key available for embeddings. Set self.company_id and self.agent_key_name "
                "so the platform key service can resolve an OpenAI key. "
                "Keys are never read from environment variables."
            )

        try:
            model_to_use = model or self.embedding_model or 'text-embedding-3-large'

            # Handle both single text and list of texts
            if isinstance(text, str):
                text = [text]

            response = emb_client.embeddings.create(
                model=model_to_use,
                input=text
            )
            
            # Return embeddings as list of vectors
            if len(text) == 1:
                return response.data[0].embedding
            else:
                return [item.embedding for item in response.data]
            
        except Exception as e:
            logger.error(f"Error in {self.agent_name} OpenAI embeddings call: {str(e)}")
            raise
    
    def _call_llm_for_reasoning(self, prompt, system_prompt=None, temperature=0.3, max_tokens=2000):
        """
        Call LLM optimized for reasoning and Q&A tasks.
        Uses Groq API for Q&A.
        
        Args:
            prompt (str): User prompt/question
            system_prompt (str): System prompt for context
            temperature (float): Lower temperature for more focused reasoning
            max_tokens (int): Maximum tokens in response
            
        Returns:
            str: LLM response text
        """
        # Use Groq for Q&A
        return self._call_groq_qa(prompt, system_prompt, temperature, max_tokens)
    
    def _call_groq_qa(self, prompt, system_prompt=None, temperature=0.3, max_tokens=2000):
        """
        Call Groq API for Q&A tasks.
        Retries on 429 rate limit (wait then retry up to 2 times).
        
        Args:
            prompt (str): User prompt/question
            system_prompt (str): System prompt for context
            temperature (float): Sampling temperature
            max_tokens (int): Maximum tokens in response
            
        Returns:
            str: LLM response text
        """
        resolved_client, key_ctx = self._resolve_company_client()
        if resolved_client is not None:
            call_client = resolved_client
            if key_ctx.provider == 'openai':
                effective_model = getattr(settings, 'OPENAI_MODEL', 'gpt-4.1-mini')
            else:
                effective_model = self.model
        else:
            # company_id/agent_key_name not set — this agent was not initialised through the
            # subscription key service.  Fail loudly; never silently fall back to an env key.
            call_client = None
            effective_model = self.model
        if not call_client:
            raise ValueError(
                "No API key available. Set self.company_id and self.agent_key_name before "
                "making LLM calls so the platform key service can resolve the correct key. "
                "Keys are never read from environment variables."
            )
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error = None
        max_retries = 2  # 3 attempts total
        for attempt in range(max_retries + 1):
            try:
                response = call_client.chat.completions.create(
                    model=effective_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                usage = getattr(response, 'usage', None)
                content = response.choices[0].message.content
                self.last_llm_used = True

                prompt_text = ''
                try:
                    prompt_text = '\n'.join([m.get('content', '') for m in messages if isinstance(m, dict)])
                except Exception:
                    prompt_text = ''

                prompt_tokens = getattr(usage, 'prompt_tokens', None) if usage else None
                completion_tokens = getattr(usage, 'completion_tokens', None) if usage else None
                total_tokens = getattr(usage, 'total_tokens', None) if usage else None
                estimated = False

                if total_tokens is None:
                    estimated = True
                    def _est_tokens(t: str) -> int:
                        t = t or ''
                        return max(1, int(len(t) / 4))
                    if prompt_tokens is None:
                        prompt_tokens = _est_tokens(prompt_text)
                    if completion_tokens is None:
                        completion_tokens = _est_tokens(content)
                    total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

                self.last_token_usage = {
                    'provider': key_ctx.provider if key_ctx else 'groq',
                    'model': effective_model,
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens,
                    'total_tokens': total_tokens,
                    'estimated': estimated,
                }
                if key_ctx and total_tokens:
                    try:
                        from core.api_key_service import record_usage
                        record_usage(key_ctx, total_tokens)
                    except Exception as e:
                        logger.warning("marketing quota decrement failed: %s", e)
                return content
            except Exception as e:
                last_error = e
                err_str = str(e)
                is_rate_limit = "429" in err_str or "rate_limit" in err_str.lower() or "rate limit" in err_str.lower()
                if is_rate_limit and attempt < max_retries:
                    wait_sec = 4
                    match = re.search(r"try again in (\d+(?:\.\d+)?)\s*s", err_str, re.IGNORECASE)
                    if match:
                        wait_sec = max(3, min(15, int(float(match.group(1)) + 1)))
                    logger.warning(f"Groq rate limit (429), waiting {wait_sec}s before retry {attempt + 1}/{max_retries}")
                    time.sleep(wait_sec)
                else:
                    logger.error(f"Error in {self.agent_name} Groq Q&A call: {err_str}")
                    if is_rate_limit:
                        raise RuntimeError("The service is busy. Please try again in a moment.")
                    from core.api_key_service import raise_if_auth_error
                    raise_if_auth_error(e, key_ctx)
                    raise
        if last_error:
            err_str = str(last_error)
            if "429" in err_str or "rate_limit" in err_str.lower() or "rate limit" in err_str.lower():
                raise RuntimeError("The service is busy. Please try again in a moment.")
            from core.api_key_service import raise_if_auth_error
            raise_if_auth_error(last_error, key_ctx)
            raise last_error
    
    def _call_llm_for_writing(self, prompt, system_prompt=None, temperature=0.7, max_tokens=4000):
        """
        Call LLM optimized for document writing tasks.
        Uses GPT-4 Turbo for better writing quality.
        
        Args:
            prompt (str): Writing prompt
            system_prompt (str): System prompt for context
            temperature (float): Higher temperature for more creative writing
            max_tokens (int): Maximum tokens in response (higher for documents)
            
        Returns:
            str: LLM response text
        """
        # Use GPT-4 Turbo for writing (or gpt-4.1 if available)
        writing_model = getattr(settings, 'OPENAI_WRITING_MODEL', 'gpt-4.1')
        return self._call_llm(prompt, system_prompt, temperature, max_tokens, model=writing_model)
    
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

