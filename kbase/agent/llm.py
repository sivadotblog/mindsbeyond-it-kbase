"""A small, provider neutral LLM port.

``OfflineLLM`` is the default and does nothing, so every caller must have a deterministic path.
``AnthropicLLM`` and ``OpenAICompatibleLLM`` call HTTPS APIs with ``requests``; no SDK is needed.
Callers ask for JSON with :meth:`LLM.complete_json` and fall back when it returns ``None``.
"""
from __future__ import annotations

import json
import re
from typing import Any

import requests

from kbase.redact import redact

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


def parse_json(text: str | None) -> dict[str, Any] | None:
    """Parse the first JSON object in ``text``. Returns ``None`` when there is none."""
    if not text:
        return None
    cleaned = _FENCE.sub("", text.strip())
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except ValueError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(cleaned[start:end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


class LLM:
    name = "offline"
    enabled = False

    def __init__(self) -> None:
        self.last_error: str | None = None

    def complete(self, system: str, prompt: str, *, max_tokens: int = 800) -> str | None:
        return None

    def complete_json(self, system: str, prompt: str, *, max_tokens: int = 800) -> dict[str, Any] | None:
        text = self.complete(system + "\nReply with a single JSON object and nothing else.", prompt,
                             max_tokens=max_tokens)
        data = parse_json(text)
        if text is not None and data is None:
            self.last_error = "reply was not valid JSON"
        return data

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "enabled": self.enabled}


class OfflineLLM(LLM):
    """No model. The agent uses its deterministic logic."""


class _HttpLLM(LLM):
    enabled = True

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout: float = 30.0,
                 session: Any = None):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def _post(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any] | None:
        try:
            resp = self.session.post(url, headers=headers, json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            self.last_error = f"{self.name} request failed: {type(exc).__name__}"
            return None
        if resp.status_code != 200:
            self.last_error = f"{self.name} returned HTTP {resp.status_code}: {redact(resp.text[:200])}"
            return None
        try:
            return resp.json()
        except ValueError:
            self.last_error = f"{self.name} returned a body that is not JSON"
            return None

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "enabled": True, "model": self.model}


class AnthropicLLM(_HttpLLM):
    name = "anthropic"

    def complete(self, system: str, prompt: str, *, max_tokens: int = 800) -> str | None:
        self.last_error = None
        data = self._post(
            f"{self.base_url}/v1/messages",
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            {"model": self.model, "max_tokens": max_tokens, "system": system,
             "messages": [{"role": "user", "content": prompt}]},
        )
        if data is None:
            return None
        texts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        return "".join(texts) or None


class OpenAICompatibleLLM(_HttpLLM):
    name = "openai"

    def __init__(self, *, auth_header: str = "Authorization", **kwargs: Any):
        super().__init__(**kwargs)
        self.auth_header = auth_header

    def complete(self, system: str, prompt: str, *, max_tokens: int = 800) -> str | None:
        self.last_error = None
        if self.auth_header.lower() == "authorization":
            headers = {"Authorization": f"Bearer {self.api_key}"}
        else:
            headers = {self.auth_header: self.api_key}
        data = self._post(
            f"{self.base_url}/chat/completions", headers,
            {"model": self.model, "max_tokens": max_tokens, "temperature": 0,
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
        )
        if data is None:
            return None
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            self.last_error = "openai reply had no choices"
            return None


def make_llm(settings: Any, session: Any = None) -> LLM:
    """Build the LLM from settings. Missing keys mean offline."""
    if not settings.llm_enabled:
        return OfflineLLM()
    common = {"api_key": settings.llm_api_key, "model": settings.llm_model,
              "timeout": settings.llm_timeout, "session": session}
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(base_url=settings.llm_base_url or "https://api.anthropic.com", **common)
    return OpenAICompatibleLLM(base_url=settings.llm_base_url or "https://api.openai.com/v1",
                               auth_header=settings.llm_auth_header, **common)
