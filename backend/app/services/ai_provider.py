"""Replaceable interface for model calls. Sensitive folders currently warn users;
they still send selected text to the configured provider when they ask a question.
"""
from __future__ import annotations

from typing import Protocol

import httpx

from app.core.config import get_settings


class AIProvider(Protocol):
    async def complete(self, messages: list[dict[str, str]], *, model: str,
                       temperature: float, max_tokens: int,
                       timeout: httpx.Timeout) -> str: ...


class DeepSeekProvider:
    """Current hosted provider implementation; keep provider credentials server-side."""
    endpoint = "https://api.deepseek.com/chat/completions"

    async def complete(self, messages: list[dict[str, str]], *, model: str,
                       temperature: float = 0.1, max_tokens: int = 900,
                       timeout: httpx.Timeout | None = None) -> str:
        settings = get_settings()
        if not settings.DEEPSEEK_API_KEY:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=timeout or httpx.Timeout(60)) as client:
            response = await client.post(self.endpoint,
                headers={"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}"},
                json={"model": model, "messages": messages, "temperature": temperature,
                      "max_tokens": max_tokens, "thinking": {"type": "disabled"}, "stream": False})
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("AI provider returned an empty answer")
            return answer.strip()


def get_ai_provider() -> AIProvider:
    """Central provider factory. Swap this factory to support a self-hosted model."""
    return DeepSeekProvider()


def active_model_name() -> str:
    model = get_settings().DEEPSEEK_MODEL.strip()
    # Keep production compatibility with deployments that still name retired IDs.
    return "deepseek-flash" if model in {"deepseek-chat", "deepseek-reasoner"} else model
