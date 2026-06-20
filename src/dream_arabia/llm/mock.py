"""Deterministic, context-grounded LLM for offline dev/CI.

It does not invent facts: it composes an answer from the retrieved citations the
agent passes in ``LLMContext``, and always produces an answer that satisfies the
Definition of Done — statistics cited with source name + year, and a closing
handoff with the persona's URL + a named action. This lets the regression run
without a network or API key while still exercising the full agent path.
"""
from __future__ import annotations

from .base import LLMContext, Message


class MockLLM:
    name = "mock"

    def __init__(self, model: str = "mock"):
        self.model = model

    def complete(self, system: str, messages: list[Message], context: LLMContext | None = None) -> str:
        question = next((m.content for m in reversed(messages) if m.role == "user"), "")
        if context is None or not context.citations:
            # No grounded context: refuse rather than hallucinate, still hand off.
            return (
                "I can only answer from official Saudi sources, and I didn't find a "
                "relevant one for that. Next step: start at the official portal "
                f"({context.handoff_url})." if context else
                "I can only answer from official sources."
            )

        cited = context.citations
        primary = cited[0]
        parts: list[str] = []

        # Opening line grounded in the top source; statistics carry source + year.
        if primary.has_year:
            parts.append(
                f"According to the {primary.name} ({primary.year}), {primary.snippet}"
            )
        else:
            parts.append(f"From {primary.name}: {primary.snippet}")

        # Bring in additional distinct sources as supporting context.
        for c in cited[1:3]:
            if c.has_year:
                parts.append(f"The {c.name} ({c.year}) adds: {c.snippet}")
            else:
                parts.append(f"{c.name} notes: {c.snippet}")

        # Source list (every fact attributable).
        src_lines = []
        for c in cited:
            yr = f", {c.year}" if c.has_year else ""
            src_lines.append(f"- {c.name}{yr}: {c.url}")
        sources_block = "Sources:\n" + "\n".join(dict.fromkeys(src_lines))

        # Closing handoff: specific URL + named action (never a bare "visit the site").
        handoff = f"Next step: {context.action} at {context.handoff_url}."

        body = " ".join(parts)
        return f"{body}\n\n{sources_block}\n\n{handoff}"
