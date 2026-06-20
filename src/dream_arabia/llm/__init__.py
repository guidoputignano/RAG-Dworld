"""LLM layer (Phase 6): provider interface, MockLLM, OpenRouter."""
from .base import LLM, LLMContext, Citation, Message, get_llm
from .mock import MockLLM

__all__ = ["LLM", "LLMContext", "Citation", "Message", "get_llm", "MockLLM"]
