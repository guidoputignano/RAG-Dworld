"""Frontmatter markdown — the universal format for every knowledge_base page.

Both scraped pages (Phase 3) and extracted PDFs (Phase 2) produce a markdown file
with a YAML frontmatter block carrying provenance and persona tags:

    ---
    source: misa
    title: Foreign Investor Licensing
    url: https://misa.gov.sa/en/investor-license
    personas: [P1, P2, P4]
    tier: T1
    publisher: Ministry of Investment
    year: 2025
    fixture: true
    ---
    # Foreign Investor Licensing
    ...

This module reads/writes that format. The ``source`` (namespace), ``url`` and
``personas`` fields are required on every file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

REQUIRED_FIELDS = ("source", "url", "personas")
_DELIM = "---"


@dataclass
class Document:
    frontmatter: dict
    body: str
    path: Path | None = None

    @property
    def source(self) -> str:
        return self.frontmatter["source"]

    @property
    def url(self) -> str:
        return self.frontmatter["url"]

    @property
    def personas(self) -> list[str]:
        return list(self.frontmatter.get("personas", []))

    @property
    def title(self) -> str:
        return self.frontmatter.get("title", "")


class FrontmatterError(ValueError):
    """Raised when a document is missing or has malformed frontmatter."""


def parse(text: str, path: Path | None = None) -> Document:
    """Parse frontmatter markdown text into a Document."""
    if not text.startswith(_DELIM):
        raise FrontmatterError(f"{path or '<text>'}: missing leading '---' frontmatter block")
    # Split into the frontmatter block and the body.
    rest = text[len(_DELIM):]
    end = rest.find("\n" + _DELIM)
    if end == -1:
        raise FrontmatterError(f"{path or '<text>'}: unterminated frontmatter block")
    fm_text = rest[:end]
    body = rest[end + len("\n" + _DELIM):].lstrip("\n")
    data = yaml.safe_load(fm_text) or {}
    if not isinstance(data, dict):
        raise FrontmatterError(f"{path or '<text>'}: frontmatter is not a mapping")
    missing = [f for f in REQUIRED_FIELDS if f not in data or data[f] in (None, "", [])]
    if missing:
        raise FrontmatterError(f"{path or '<text>'}: missing required frontmatter: {missing}")
    return Document(frontmatter=data, body=body, path=path)


def read(path: str | Path) -> Document:
    path = Path(path)
    return parse(path.read_text(encoding="utf-8"), path=path)


def dumps(doc: Document) -> str:
    fm = yaml.safe_dump(doc.frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"{_DELIM}\n{fm}\n{_DELIM}\n\n{doc.body.rstrip()}\n"


def write(doc: Document, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(doc), encoding="utf-8")
    return path


def iter_documents(root: str | Path) -> list[Document]:
    """Read every ``*.md`` under ``root`` (recursively) as Documents."""
    root = Path(root)
    return [read(p) for p in sorted(root.rglob("*.md"))]
