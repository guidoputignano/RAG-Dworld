"""Guardrail enforcement engine (Phase 6) — the first-class guardrail layer.

Consumes the structured ruleset parsed in Phase 1 and does two jobs:

1. **Prompt** — render the persona's HARD/SOFT rules into the system prompt so
   the model is told the constraints up front.
2. **Validate / enforce** — deterministically check the produced answer:
   - statistics carry source name + year,
   - the answer ends with a handoff URL + a named action,
   - no HARD "NEVER…" pattern is violated (eligibility confirmation, guaranteed
     approvals, tax-rate quoting without a source, visa determinations).

   ``enforce`` auto-fixes the always-required structural rules (appends a handoff
   if missing) and returns the remaining violations so callers can surface or
   block on HARD breaches.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from config.guardrails_loader import GuardrailRule, Ruleset, load_generated
from ..llm.base import Citation


# Cross-persona HARD patterns that must never appear in an answer. These encode
# the Guardrails Matrix / persona "NEVER…" rules as detectors.
_FORBIDDEN: list[tuple[str, re.Pattern]] = [
    ("confirm_eligibility", re.compile(r"\byou(?:'re| are)?\s+(?:do\s+)?(?:qualify|qualified|eligible)\b", re.I)),
    ("confirm_eligibility", re.compile(r"\byou (?:will|'ll) (?:be )?(?:approved|get approved|qualify)\b", re.I)),
    # Promising an outcome to the user — NOT the product noun "loan guarantee"
    # and NOT negations like "no route guarantees funding". Requires a
    # first/second-person promissory subject, or the adjective form.
    ("guarantee", re.compile(r"\b(?:we|i|this|it|that)\s+guarantee(?:s)?\b", re.I)),
    ("guarantee", re.compile(r"\bguaranteed\s+(?:approval|funding|acceptance|admission|you|your)\b", re.I)),
    ("guarantee", re.compile(r"\b(?:approval|funding|acceptance|admission)\s+is\s+guaranteed\b", re.I)),
    ("visa_determination", re.compile(r"\byour (?:visa|iqama|residency)(?: application)? will be (?:approved|rejected|denied)\b", re.I)),
]
# A percentage adjacent to tax/zakat/vat language, treated as "quoting a tax rate".
_TAX_RATE = re.compile(r"(?:\btax\b|\bvat\b|\bzakat\b)[^.]{0,40}?\b\d+(?:\.\d+)?\s*%|\b\d+(?:\.\d+)?\s*%[^.]{0,40}?(?:\btax\b|\bvat\b|\bzakat\b)", re.I)
_URL = re.compile(r"https?://[^\s)\]\"'<>]+")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_NEGATION = re.compile(r"\b(?:not|no|never|without|cannot|can't|don't|doesn't|isn't|aren't|won't)\b", re.I)


def _negated_before(text: str, start: int, window: int = 30) -> bool:
    """True if a negation word appears just before ``start`` (e.g. 'not guaranteed')."""
    return bool(_NEGATION.search(text[max(0, start - window):start]))


def _hit(pat: re.Pattern, text: str) -> bool:
    """Pattern matches and is not negated immediately before the match."""
    for m in pat.finditer(text):
        if not _negated_before(text, m.start()):
            return True
    return False
_NAMED_ACTION = re.compile(
    r"\b(register|apply|download|book|contact|start|begin|review|submit|visit|check|read|browse|open|consult)\b",
    re.I,
)


def _norm_url(u: str) -> str:
    """Normalise a URL for comparison (drop trailing punctuation / slash, lowercase)."""
    return u.strip().rstrip(".,;:!?)]}'\"").rstrip("/").lower()


def _allowed_urls(citations: list[Citation], handoff_urls: list[str]) -> set[str]:
    allowed = {_norm_url(u) for u in handoff_urls if u}
    allowed |= {_norm_url(c.url) for c in citations if c.url}
    return allowed


def _strip_ungrounded_urls(text: str, allowed: set[str]) -> str:
    """Replace any URL not in ``allowed`` with a marker, so invented links never show."""
    return _URL.sub(
        lambda m: m.group(0) if _norm_url(m.group(0)) in allowed else "[link not in official sources]",
        text,
    )


@dataclass
class Violation:
    kind: str            # "missing_handoff" | "missing_citation_year" | "forbidden:<x>"
    severity: str        # "HARD" | "SOFT"
    detail: str = ""


@dataclass
class ValidationReport:
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def hard(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == "HARD"]

    @property
    def ok_hard(self) -> bool:
        return not self.hard


class GuardrailEngine:
    def __init__(self, ruleset: Ruleset | None = None):
        self.ruleset = ruleset or load_generated()

    # --- prompt side ------------------------------------------------------

    def rules_for(self, persona: str) -> list[GuardrailRule]:
        return self.ruleset.for_persona(persona)

    def render_rules(self, persona: str) -> str:
        rules = self.rules_for(persona)
        hard = [r for r in rules if r.severity == "HARD"]
        soft = [r for r in rules if r.severity == "SOFT"]

        def fmt(r: GuardrailRule) -> str:
            who = r.domain or r.rule_type
            pattern = f" Required response: {r.response_pattern}" if r.response_pattern else ""
            return f"- ({who}) {r.rule}.{pattern}"

        lines = ["HARD rules (never violate):"]
        lines += [fmt(r) for r in hard]
        if soft:
            lines += ["", "SOFT rules (prefer to follow):"]
            lines += [fmt(r) for r in soft]
        return "\n".join(lines)

    def system_prompt(self, persona_name: str, persona: str, handoff_url: str) -> str:
        return (
            f"You are Dream Arabia, a persona-switchable assistant for Saudi government "
            f"programmes. The active persona is {persona} ({persona_name}).\n\n"
            "Core rules:\n"
            "- Answer ONLY from the official sources in the context. Do not invent facts.\n"
            "- Use ONLY figures, amounts, and percentages that literally appear in the context. "
            "If the sources do not give a specific number or amount, say the official sources "
            "provided do not specify it — never estimate it or supply it from general knowledge.\n"
            "- The only URLs you may write are those that appear in the context or the handoff "
            "URL below. Never invent, guess, or construct a link.\n"
            "- Every statistic must include the source name and year (e.g. 'MISA FDI Report, 2024').\n"
            "- Maintain strict neutrality on Saudi politics, the royal family, and competitor "
            "jurisdictions (UAE, Qatar, etc.).\n"
            "- Never confirm an individual's eligibility, never guarantee approvals or timelines, "
            "never quote tax rates/quotas without an official source URL, never make visa/immigration "
            "determinations.\n"
            f"- End every answer with a specific handoff: a named action plus the URL "
            f"(primary handoff: {handoff_url}). Never say only 'visit the site'.\n\n"
            f"Persona guardrails:\n{self.render_rules(persona)}"
        )

    # --- validation side --------------------------------------------------

    def validate(
        self,
        answer: str,
        persona: str,
        citations: list[Citation],
        handoff_urls: list[str],
    ) -> ValidationReport:
        report = ValidationReport()

        # 1. handoff: a known handoff URL + a named action verb.
        has_handoff = any(u and u in answer for u in handoff_urls)
        if not has_handoff:
            report.violations.append(Violation("missing_handoff", "HARD", "no handoff URL in answer"))
        elif not _NAMED_ACTION.search(answer):
            report.violations.append(Violation("missing_handoff", "HARD", "handoff URL without a named action"))

        # 2. statistics carry source name + year. If any cited node has a year,
        #    require a 4-digit year to appear in the answer text.
        if any(c.has_year for c in citations) and not _YEAR.search(answer):
            report.violations.append(
                Violation("missing_citation_year", "HARD", "a dated source was used but no year is cited")
            )

        # 3. forbidden HARD patterns (negation-aware: "not guaranteed" is fine).
        for label, pat in _FORBIDDEN:
            if _hit(pat, answer):
                report.violations.append(Violation(f"forbidden:{label}", "HARD", pat.pattern))
        if _TAX_RATE.search(answer) and not _URL.search(answer):
            report.violations.append(
                Violation("forbidden:tax_rate_without_source", "HARD", "tax-rate % without a source URL")
            )

        # 4. groundedness: every URL in the answer must be one we actually provided
        #    (a cited source or a known handoff) — invented links are hallucinations.
        allowed = _allowed_urls(citations, handoff_urls)
        for m in _URL.finditer(answer):
            if _norm_url(m.group(0)) not in allowed:
                report.violations.append(
                    Violation("ungrounded_url", "HARD", f"URL not in official sources: {m.group(0)}")
                )

        return report

    def enforce(
        self,
        answer: str,
        persona: str,
        citations: list[Citation],
        handoff_url: str,
        action: str = "continue",
        extra_handoffs: list[str] | None = None,
    ) -> tuple[str, ValidationReport]:
        """Neutralise invented URLs, auto-fix the handoff, then return violations."""
        handoff_urls = [handoff_url] + (extra_handoffs or [])
        allowed = _allowed_urls(citations, handoff_urls)

        # record then strip any invented link, so a fabricated URL is never shown
        invented = [m.group(0) for m in _URL.finditer(answer) if _norm_url(m.group(0)) not in allowed]
        fixed = _strip_ungrounded_urls(answer, allowed)

        report = self.validate(fixed, persona, citations, handoff_urls)
        if any(v.kind == "missing_handoff" for v in report.hard):
            fixed = f"{fixed.rstrip()}\n\nNext step: {action} at {handoff_url}."
            report = self.validate(fixed, persona, citations, handoff_urls)

        # surface the hallucination even though it was removed from the text
        for u in invented:
            report.violations.append(Violation("ungrounded_url", "HARD", f"removed invented URL: {u}"))
        return fixed, report
