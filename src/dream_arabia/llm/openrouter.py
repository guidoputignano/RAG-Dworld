"""OpenRouter chat-completions client (configurable model). Network + key.

The kickoff asks for the option to use specific agents/models through OpenRouter;
the model id is configurable via ``DREAM_LLM_MODEL`` (default a Claude model).
"""
from __future__ import annotations

import os

from .base import LLMContext, Message


class OpenRouterLLM:
    name = "openrouter"

    def __init__(self, model: str = "qwen/qwen3.5-flash-02-23", env: dict | None = None):
        env = env if env is not None else os.environ
        self.model = model
        self.base_url = (env.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        self.api_key = env.get("OPENROUTER_API_KEY") or ""
        self.temperature = float(env.get("DREAM_LLM_TEMPERATURE", "0.2"))

    def complete(self, system: str, messages: list[Message], context: LLMContext | None = None) -> str:  # pragma: no cover - needs network
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set; use DREAM_LLM_PROVIDER=mock offline")
        import httpx

        payload_messages = [{"role": "system", "content": system}]
        payload_messages += [{"role": m.role, "content": m.content} for m in messages]
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": self.model, "messages": payload_messages, "temperature": self.temperature},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
