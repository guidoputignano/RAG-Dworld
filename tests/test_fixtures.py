"""Phase 1 — fixtures: every knowledge_base page has valid frontmatter."""
from pathlib import Path

import pytest

from config import SOURCES
from dream_arabia import markdown_io

REPO_ROOT = Path(__file__).resolve().parent.parent
# Synthetic fixtures live here (separated from the real scraped knowledge_base/).
KB = REPO_ROOT / "tests" / "fixtures" / "kb"
FIXTURE_SOURCES = {"misa", "monshaat"}


def _docs():
    return markdown_io.iter_documents(KB)


def test_two_sources_have_fixtures():
    present = {p.parent.name for p in KB.rglob("*.md")}
    assert FIXTURE_SOURCES <= present


def test_each_source_has_three_to_five_pages():
    for ns in FIXTURE_SOURCES:
        n = len(list((KB / ns).glob("*.md")))
        assert 3 <= n <= 5, f"{ns} has {n} fixture pages (want 3-5)"


def test_frontmatter_valid_and_consistent():
    docs = _docs()
    assert docs, "no fixture documents found"
    for doc in docs:
        # required fields enforced by parser; check coherence with config
        assert doc.source in SOURCES, f"{doc.path}: unknown source {doc.source}"
        assert doc.url.startswith("http")
        assert doc.personas, f"{doc.path}: no persona tags"
        for p in doc.personas:
            assert p in SOURCES[doc.source].personas, (
                f"{doc.path}: persona {p} not valid for source {doc.source}"
            )
        assert doc.frontmatter.get("fixture") is True


def test_missing_frontmatter_raises():
    with pytest.raises(markdown_io.FrontmatterError):
        markdown_io.parse("# no frontmatter here\n")
