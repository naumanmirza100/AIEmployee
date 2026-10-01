import json
import os
import time
from typing import Any, Dict, Optional

import requests


class GroqClientError(Exception):
    """Custom exception for Groq client failures."""
    
    def __init__(self, message: str, is_auth_error: bool = False, is_rate_limit: bool = False, is_request_too_large: bool = False):
        super().__init__(message)
        self.is_auth_error = is_auth_error  # API key expired/invalid
        self.is_rate_limit = is_rate_limit  # Rate limit exceeded
        self.is_request_too_large = is_request_too_large  # Request exceeds token limit (413)


class GroqClient:
    """
    Thin wrapper around Groq's chat completion API for structured JSON extraction.
    API key MUST be supplied explicitly — never fetched from environment.
    Use QuotaAwareGroqClient (below) with a CallContext from resolve_for_call()
    so that every call is tracked against the company's quota.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        # Keys must come from the platform (resolve_for_call), never from .env.
        # If api_key is still None here, something in the call chain bypassed
        # resolve_for_call — fail loudly so the bug is caught immediately.
        if not api_key:
            raise GroqClientError(
                "No API key provided. All keys must come from the platform key service "
                "(resolve_for_call). Do not set GROQ_API_KEY or GROQ_REC_API_KEY in the environment.",
                is_auth_error=True,
            )
        self.api_key = api_key
        self.model = model or "openai/gpt-oss-20b"
        self.base_url = base_url or "https://api.groq.com/openai/v1/chat/completions"
        self.timeout = timeout
        self.last_token_usage: Optional[Dict] = None  # Tracks token usage of last API call

    def send_prompt(self, system_prompt: str, text: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Send a prompt and text to Groq and return parsed JSON.
        Raises GroqClientError with is_auth_error=True if API key is expired/invalid.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_exc = None
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.base_url, headers=headers, json=payload, timeout=self.timeout
                )
                response.raise_for_status()
                last_exc = None
                break
            except requests.HTTPError as exc:
                detail = ""
                try:
                    error_body = exc.response.json()
                    detail = error_body.get("error", {}).get("message", exc.response.text)
                except Exception:
                    detail = exc.response.text
                if exc.response.status_code in (401, 403):
                    raise GroqClientError(
                        f"Groq API authentication failed (API key expired/invalid): {detail}",
                        is_auth_error=True,
                    ) from exc
                if exc.response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait = 30
                        try:
                            wait = int(exc.response.headers.get("Retry-After", 30))
                        except (ValueError, TypeError):
                            pass
                        time.sleep(wait)
                        last_exc = exc
                        continue
                    raise GroqClientError(
                        "Groq API rate limit exceeded.",
                        is_rate_limit=True,
                    ) from exc
                if exc.response.status_code == 413:
                    raise GroqClientError(
                        f"Groq API request too large (exceeds token limit): {detail}",
                        is_request_too_large=True,
                    ) from exc
                raise GroqClientError(
                    f"Groq API request failed (HTTP {exc.response.status_code}): {detail}"
                ) from exc
            except requests.RequestException as exc:
                raise GroqClientError(f"Groq API request failed: {exc}") from exc
        if last_exc is not None:
            raise GroqClientError(
                "Groq API rate limit exceeded after retries.",
                is_rate_limit=True,
            ) from last_exc

        try:
            content = response.json()
            self.last_token_usage = content.get("usage", {})
            message = content["choices"][0]["message"]["content"]
            return json.loads(message)
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise GroqClientError(f"Unable to parse Groq response: {exc}") from exc

    def send_prompt_text(self, system_prompt: str, text: str, max_retries: int = 3) -> str:
        """
        Send a prompt and return raw text (no JSON mode). Use for long or free-form
        output where JSON would be fragile (e.g. multi-paragraph job descriptions).
        Retries up to max_retries times on rate-limit (429) with backoff.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
            "max_tokens": 2048,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_exc = None
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.base_url, headers=headers, json=payload, timeout=self.timeout
                )
                response.raise_for_status()
                last_exc = None
                break
            except requests.HTTPError as exc:
                detail = ""
                try:
                    error_body = exc.response.json()
                    detail = error_body.get("error", {}).get("message", exc.response.text)
                except Exception:
                    detail = exc.response.text
                if exc.response.status_code in (401, 403):
                    raise GroqClientError(
                        f"Groq API authentication failed: {detail}",
                        is_auth_error=True,
                    ) from exc
                if exc.response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait = 30
                        try:
                            wait = int(exc.response.headers.get("Retry-After", 30))
                        except (ValueError, TypeError):
                            pass
                        time.sleep(wait)
                        last_exc = exc
                        continue
                    raise GroqClientError(
                        "Groq API rate limit exceeded.",
                        is_rate_limit=True,
                    ) from exc
                if exc.response.status_code == 413:
                    raise GroqClientError(
                        "Groq API request too large.",
                        is_request_too_large=True,
                    ) from exc
                raise GroqClientError(
                    f"Groq API request failed (HTTP {exc.response.status_code}): {detail}"
                ) from exc
            except requests.RequestException as exc:
                raise GroqClientError(f"Groq API request failed: {exc}") from exc
        if last_exc is not None:
            raise GroqClientError(
                "Groq API rate limit exceeded after retries.",
                is_rate_limit=True,
            ) from last_exc
        try:
            content = response.json()
            self.last_token_usage = content.get("usage", {})
            return content["choices"][0]["message"]["content"].strip() or ""
        except (KeyError, TypeError):
            raise GroqClientError("Unable to read Groq response") from None


    def send_prompt_text_stream(self, system_prompt: str, text: str, max_retries: int = 3):
        """`send_prompt_text`, as it is written: yields pieces of the answer.

        Errors before the first piece (auth, rate limit after retries, too
        large) raise GroqClientError exactly as the plain call does. Token
        usage lands in `last_token_usage` at the end — Groq reports it on the
        last chunk; if it didn't, or the reader stopped early, it's estimated.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
            "max_tokens": 2048,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = None
        for attempt in range(max_retries):
            try:
                response = requests.post(self.base_url, headers=headers, json=payload,
                                         timeout=self.timeout, stream=True)
                response.raise_for_status()
                break
            except requests.HTTPError as exc:
                code = exc.response.status_code
                try:
                    detail = exc.response.json().get("error", {}).get("message", exc.response.text)
                except Exception:
                    detail = exc.response.text
                if code in (401, 403):
                    raise GroqClientError(f"Groq API authentication failed: {detail}", is_auth_error=True) from exc
                if code == 429:
                    if attempt < max_retries - 1:
                        try:
                            wait = int(exc.response.headers.get("Retry-After", 30))
                        except (ValueError, TypeError):
                            wait = 30
                        time.sleep(wait)
                        continue
                    raise GroqClientError("Groq API rate limit exceeded.", is_rate_limit=True) from exc
                if code == 413:
                    raise GroqClientError("Groq API request too large.", is_request_too_large=True) from exc
                raise GroqClientError(f"Groq API request failed (HTTP {code}): {detail}") from exc
            except requests.RequestException as exc:
                raise GroqClientError(f"Groq API request failed: {exc}") from exc

        self.last_token_usage = None
        collected = []
        try:
            for raw in response.iter_lines():
                line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else (raw or "")
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                usage = chunk.get("usage") or (chunk.get("x_groq") or {}).get("usage")
                if usage:
                    self.last_token_usage = usage
                for choice in chunk.get("choices") or []:
                    piece = (choice.get("delta") or {}).get("content") or ""
                    if piece:
                        collected.append(piece)
                        yield piece
        except requests.RequestException as exc:
            raise GroqClientError(f"Groq API stream failed: {exc}") from exc
        finally:
            response.close()
            if not self.last_token_usage:
                prompt_tokens = (len(system_prompt) + len(text)) // 4 + 1
                completion_tokens = len("".join(collected)) // 4 + 1
                self.last_token_usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                                         "total_tokens": prompt_tokens + completion_tokens, "estimated": True}


import logging as _logging
_core_logger = _logging.getLogger(__name__)


class QuotaAwareGroqClient(GroqClient):
    """GroqClient that automatically records token usage against a company quota
    after every LLM call. Pass the CallContext returned by resolve_for_call().

    Usage:
        ctx = resolve_for_call(company, 'recruitment_agent')
        client = QuotaAwareGroqClient(api_key=ctx.api_key, key_ctx=ctx)
    """

    def __init__(self, api_key: str, key_ctx, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self._key_ctx = key_ctx

    def _record_after_call(self) -> None:
        usage = self.last_token_usage or {}
        total = int(usage.get('total_tokens', 0))
        if total > 0 and self._key_ctx:
            try:
                from core.api_key_service import record_usage
                record_usage(self._key_ctx, total)
            except Exception as exc:
                _core_logger.warning("Recruitment quota decrement failed: %s", exc)

    def send_prompt(self, system_prompt: str, text: str, max_retries: int = 3):
        result = super().send_prompt(system_prompt, text, max_retries)
        self._record_after_call()
        return result

    def send_prompt_text(self, system_prompt: str, text: str, max_retries: int = 3):
        result = super().send_prompt_text(system_prompt, text, max_retries)
        self._record_after_call()
        return result

    def send_prompt_text_stream(self, system_prompt: str, text: str, max_retries: int = 3):
        # Recorded however the stream ends — the model wrote those tokens even
        # if the reader went away part-way.
        started = False
        try:
            for piece in super().send_prompt_text_stream(system_prompt, text, max_retries):
                started = True
                yield piece
            started = True
        finally:
            if started:
                self._record_after_call()
