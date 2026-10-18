from abc import ABC, abstractmethod
import json
import logging
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger("datapulse.llm")


class LLMError(Exception):
    """Base exception for LLM operations."""
    pass


class LLMConfigurationError(LLMError):
    """Raised when LLM API key or essential configuration is missing or invalid."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when an LLM provider request times out."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when the LLM provider responds with rate limit / 429."""
    pass


class LLMProviderError(LLMError):
    """Raised when the LLM provider fails due to network, auth, or server errors."""
    pass


class LLMResponseFormatError(LLMError):
    """Raised when the LLM response cannot be parsed or validated against the schema."""
    pass


class LLMProvider(ABC):
    """Abstract interface for LLM completion providers."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text completion from LLM."""
        pass


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible chat completions provider (OpenAI, Groq, OpenRouter, Ollama, etc.)."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.api_key = self.settings.LLM_API_KEY
        self.model = self.settings.LLM_MODEL
        self.base_url = (self.settings.LLM_API_BASE or "https://api.openai.com/v1").rstrip("/")
        self.timeout = self.settings.LLM_TIMEOUT_SECONDS

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.api_key or not self.api_key.strip():
            raise LLMConfigurationError(
                "LLM API key is not configured. Please set LLM_API_KEY in your environment."
            )

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(endpoint, json=payload, headers=headers)

                if response.status_code in (401, 403):
                    raise LLMProviderError("Authentication failed with LLM provider. Check your API key configuration.")
                elif response.status_code == 429:
                    raise LLMRateLimitError("LLM provider rate limit exceeded. Please retry after some time.")
                elif response.status_code >= 500:
                    raise LLMProviderError(f"LLM provider service error (HTTP {response.status_code}).")
                elif response.status_code >= 400:
                    raise LLMProviderError(f"LLM provider rejected request (HTTP {response.status_code}).")

                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    raise LLMResponseFormatError("LLM provider returned empty choices in response.")

                content = choices[0].get("message", {}).get("content", "")
                if not content or not content.strip():
                    raise LLMResponseFormatError("LLM provider returned empty message content.")

                return content.strip()

        except httpx.TimeoutException as exc:
            logger.error(f"LLM request timed out after {self.timeout}s: {exc.__class__.__name__}")
            raise LLMTimeoutError(f"LLM provider request timed out after {self.timeout} seconds.")
        except httpx.RequestError as exc:
            logger.error(f"LLM network error: {exc.__class__.__name__}")
            raise LLMProviderError("LLM provider network connection failed.")
        except LLMError:
            raise
        except Exception as exc:
            logger.error(f"Unexpected error during LLM generation: {exc.__class__.__name__}")
            raise LLMProviderError("LLM provider communication failed.")


class GeminiProvider(LLMProvider):
    """Google Gemini completion provider using the official Google Gen AI Python SDK (google-genai)."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.api_key = self.settings.effective_gemini_api_key
        # Use LLM_MODEL if specified and not an OpenAI default or deprecated gemini-2.5-flash
        model_name = (self.settings.LLM_MODEL or "").strip()
        if not model_name or "gpt" in model_name.lower() or model_name == "gemini-2.5-flash":
            self.model = "gemini-3.8-flash"
        else:
            self.model = model_name
        self.timeout = self.settings.LLM_TIMEOUT_SECONDS

    @staticmethod
    def _sanitize_error(text: str) -> str:
        """Strip API keys, authorization tokens, or sensitive query params from error messages."""
        if not text:
            return ""
        import re
        sanitized = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "[REDACTED_API_KEY]", text)
        sanitized = re.sub(r"(key=)[^&\s]+", r"\1[REDACTED_KEY]", sanitized)
        sanitized = re.sub(r"(Bearer\s+)[A-Za-z0-9\-_.]+", r"\1[REDACTED_TOKEN]", sanitized, flags=re.IGNORECASE)
        return sanitized

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self.api_key or not self.api_key.strip():
            raise LLMConfigurationError(
                "Gemini API key is not configured. Please set GEMINI_API_KEY in your environment."
            )

        try:
            from google import genai
            from google.genai import types, errors
        except ImportError as imp_err:
            logger.error("google-genai SDK is not installed: %s", imp_err)
            raise LLMConfigurationError(
                "The 'google-genai' SDK is not installed. Please run: pip install google-genai"
            )

        try:
            client = genai.Client(api_key=self.api_key)

            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.2,
            )

            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )

            text = response.text
            if not text or not text.strip():
                raise LLMResponseFormatError("Gemini returned an empty response.")

            return text.strip()

        except errors.ClientError as exc:
            code = getattr(exc, "code", None)
            raw_msg = str(exc)
            err_msg = self._sanitize_error(raw_msg)
            if code in (401, 403) or "API_KEY_INVALID" in err_msg or "PERMISSION_DENIED" in err_msg:
                logger.error("Gemini authentication failure (HTTP %s): %s", code, err_msg)
                raise LLMProviderError(f"Authentication failed with Gemini API (HTTP {code}). Check your API key configuration.")
            elif code == 429 or "RESOURCE_EXHAUSTED" in err_msg or "rate limit" in err_msg.lower() or "quota" in err_msg.lower():
                logger.warning("Gemini rate limit / quota exceeded (HTTP %s): %s", code, err_msg)
                raise LLMRateLimitError(f"Gemini API rate limit or quota exceeded (HTTP {code}). Please retry after some time.")
            else:
                logger.error("Gemini client error (HTTP %s): %s", code, err_msg)
                raise LLMProviderError(f"Gemini API rejected request (HTTP {code}): {err_msg}")
        except errors.ServerError as exc:
            code = getattr(exc, "code", None)
            err_msg = self._sanitize_error(str(exc))
            logger.error("Gemini server error (HTTP %s): %s", code, err_msg)
            raise LLMProviderError(f"Gemini service error (HTTP {code}): {err_msg}")
        except errors.APIError as exc:
            code = getattr(exc, "code", None)
            err_msg = self._sanitize_error(str(exc))
            logger.error("Gemini API error (HTTP %s): %s", code, err_msg)
            raise LLMProviderError(f"Gemini API error (HTTP {code}): {err_msg}")
        except (LLMConfigurationError, LLMRateLimitError, LLMTimeoutError, LLMResponseFormatError, LLMProviderError):
            raise
        except Exception as exc:
            err_str = self._sanitize_error(str(exc))
            if "timeout" in err_str.lower() or "timed out" in err_str.lower():
                raise LLMTimeoutError(f"Gemini request timed out after {self.timeout} seconds.")
            logger.error("Unexpected error during Gemini generation [%s]: %s", exc.__class__.__name__, err_str)
            raise LLMProviderError(f"Gemini provider communication failed [{exc.__class__.__name__}]: {err_str}")


def get_llm_provider(settings: Optional[Settings] = None) -> LLMProvider:
    """Factory to retrieve configured LLM provider instance."""
    s = settings or get_settings()
    provider_name = (s.LLM_PROVIDER or "openai").lower().strip()
    if provider_name in ("gemini", "google", "google-genai", "google_genai"):
        return GeminiProvider(settings=s)
    return OpenAICompatibleProvider(settings=s)
