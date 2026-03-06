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
    Uses GROQ_REC_API_KEY from environment for recruitment agent.
    Handles API key expiration and rate limits gracefully.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        # Use GROQ_REC_API_KEY for recruitment agent, fallback to GROQ_API_KEY
        self.api_key = api_key or os.environ.get("GROQ_REC_API_KEY") or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise GroqClientError(
                "GROQ_REC_API_KEY or GROQ_API_KEY is required. Set it in environment variables.",
                is_auth_error=True
            )
        self.model = model or os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
        self.base_url = base_url or os.environ.get(
            "GROQ_BASE_URL", "https://api.groq.com/openai/v1/chat/completions"
        )
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


