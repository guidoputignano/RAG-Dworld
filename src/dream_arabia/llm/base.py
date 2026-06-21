"""LLM provider interface + factory.

Two backends:

- ``mock`` — deterministic, context-grounded generator for offline dev/CI. It
  composes a compliant answer from the structured ``LLMContext`` the agent
  passes (citations with year, handoff URL + named action), so the
  Definition-of-Done checks run with no network.
- ``openrouter`` — chat completions via OpenRouter (configurable model). Used in
  production; ignores the structured context and works from system + messages.

Selected via ``DREAM_LLM_PROVIDER`` (see ``.env.example``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Citation:
    namespace: str
    name: str           # human-readable source name (from SOURCES)
    url: str
    year: str | int | None = None
    label: str = ""     # node label
    snippet: str = ""

    @property
    def has_year(self) -> bool:
        return self.year not in (None, "")


@dataclass
class LLMContext:
    """Structured retrieval context handed to the LLM (used by MockLLM)."""

    persona: str
    persona_name: str
    handoff_url: str
    action: str
    citations: list[Citation] = field(default_factory=list)


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str


class LLM(Protocol):
    name: str
    model: str

    def complete(self, system: str, messages: list[Message], context: LLMContext | None = None) -> str:
        ...


def get_llm(provider: str | None = None, model: str | None = None, env: dict | None = None) -> LLM:
    env = env if env is not None else os.environ
    provider = (provider or env.get("DREAM_LLM_PROVIDER") or "mock").lower()
    model = model or env.get("DREAM_LLM_MODEL") or "qwen/qwen3.5-flash-02-23"
    if provider == "mock":
        from .mock import MockLLM
        return MockLLM(model=model)
    if provider == "openrouter":
        from .openrouter import OpenRouterLLM
        return OpenRouterLLM(model=model, env=env)
    raise ValueError(f"Unknown LLM provider: {provider!r}")
