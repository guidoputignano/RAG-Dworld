"""Dream Arabia configuration package.

Single source of truth for sources, persona->namespace mapping, and the
guardrail ruleset parsed from the Excel training matrix.
"""
# Load a local, gitignored .env (if present) so settings like OPENROUTER_API_KEY,
# DREAM_LLM_MODEL, and DREAM_LLM_PROVIDER are picked up without manual `export`.
# Real environment variables still win; a missing .env or python-dotenv is a
# harmless no-op. Keep secrets in .env only — never commit them.
try:  # pragma: no cover - integration glue
    from pathlib import Path as _Path
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(_Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

from .sources import SOURCES, PDF_LIBRARY, source, namespaces_for_personas
from .personas import (
    PERSONAS,
    PERSONA_NAMESPACE_MAP,
    LAUNCH_PERSONAS,
    entry_namespaces,
    handoff_url,
)

__all__ = [
    "SOURCES",
    "PDF_LIBRARY",
    "source",
    "namespaces_for_personas",
    "PERSONAS",
    "PERSONA_NAMESPACE_MAP",
    "LAUNCH_PERSONAS",
    "entry_namespaces",
    "handoff_url",
]
