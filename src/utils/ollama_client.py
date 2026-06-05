"""Ollama client wrapper with JSON mode, retry, and timeout."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class OllamaConfig(BaseModel):
    host: str = "http://localhost:11434"
    main_model: str = "qwen3:8b"
    light_model: str = "qwen3:4b"
    timeout: float = 300.0
    max_retries: int = 2
    retry_delay: float = 2.0


class OllamaClient:
    """Thin wrapper around Ollama REST API with structured output support."""

    def __init__(self, config: OllamaConfig | None = None) -> None:
        self.config = config or OllamaConfig()
        self._client = httpx.Client(
            base_url=self.config.host,
            timeout=httpx.Timeout(self.config.timeout),
        )

    def _request(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send request with retry logic."""
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                resp = self._client.post(endpoint, json=payload)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as e:
                last_error = e
                logger.warning(
                    "Ollama request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.config.max_retries,
                    e,
                )
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (attempt + 1))
        raise RuntimeError(
            f"Ollama request failed after {self.config.max_retries} retries: {last_error}"
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        json_mode: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Send a chat completion request.

        Args:
            messages: Chat messages in OpenAI format.
            model: Model name. Defaults to config.main_model.
            json_mode: If True, force JSON output via format='json'.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.

        Returns:
            Model response text.
        """
        payload: dict[str, Any] = {
            "model": model or self.config.main_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"

        logger.debug("Ollama request: model=%s, msgs=%d, json=%s",
                      payload["model"], len(messages), json_mode)

        result = self._request("/api/chat", payload)
        content = result.get("message", {}).get("content", "")
        return content

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Chat with guaranteed JSON output, parsed into a dict.

        Raises ValueError if the response cannot be parsed as JSON.
        """
        raw = self.chat(
            messages,
            model=model,
            json_mode=True,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # Try to extract JSON from potentially noisy output
        raw = raw.strip()
        # Remove markdown code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON from model response: %s", e)
            logger.debug("Raw response: %s", raw[:500])
            raise ValueError(f"Model did not return valid JSON: {e}") from e

    def health_check(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            resp = self._client.get("/api/tags")
            resp.raise_for_status()
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List available models."""
        try:
            resp = self._client.get("/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
            return [m["name"] for m in models]
        except Exception:
            return []

    def pull_model(self, model: str) -> bool:
        """Pull a model (blocking). Returns True on success."""
        try:
            resp = self._client.post(
                "/api/pull",
                json={"name": model, "stream": False},
                timeout=httpx.Timeout(600.0),
            )
            resp.raise_for_status()
            logger.info("Model %s pulled successfully", model)
            return True
        except Exception as e:
            logger.error("Failed to pull model %s: %s", model, e)
            return False


# Singleton for convenience
_default_client: OllamaClient | None = None


def get_client() -> OllamaClient:
    global _default_client
    if _default_client is None:
        config = OllamaConfig(
            host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            main_model=os.environ.get("OLLAMA_MAIN_MODEL", "qwen3:8b"),
            light_model=os.environ.get("OLLAMA_LIGHT_MODEL", "qwen3:4b"),
        )
        _default_client = OllamaClient(config)
    return _default_client
