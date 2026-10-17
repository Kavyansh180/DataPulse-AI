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


def get_llm_provider(settings: Optional[Settings] = None) -> LLMProvider:
    """Factory to retrieve configured LLM provider instance."""
    s = settings or get_settings()
    return OpenAICompatibleProvider(settings=s)
