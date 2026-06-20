"""Phase 2 — PDF extraction: pdfplumber -> OCR fallback -> frontmatter markdown."""
from pathlib import Path

from dream_arabia import markdown_io
from dream_arabia.extract import extract_pdf, extract_to_file, NullOCR

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PDF = REPO_ROOT / "docs" / "Saudi_RAG_Agent_Specification_2.pdf"


def test_digital_pdf_uses_pdfplumber():
    res = extract_pdf(
        SPEC_PDF, source="misa", url="https://misa.gov.sa/en/spec",
        personas=["P1"], title="Saudi RAG Spec",
    )
    fm = res.document.frontmatter
    assert fm["extractor"] == "pdfplumber"
    assert fm["pages"] == 11
    assert res.pages_needing_ocr == []
    # known text survives extraction
    assert "knowledge graph" in res.document.body.lower()


def test_output_is_valid_frontmatter_markdown(tmp_path):
    out = tmp_path / "spec.md"
    res = extract_to_file(
        SPEC_PDF, out, source="misa", url="https://misa.gov.sa/en/spec",
        personas=["P1", "P2"], title="Saudi RAG Spec",
    )
    # re-parse from disk -> required frontmatter present and consistent
    doc = markdown_io.read(out)
    assert doc.source == "misa"
    assert doc.personas == ["P1", "P2"]
    assert doc.frontmatter["extracted"] is True
    assert doc.body.startswith("# Saudi RAG Spec")
    assert res.document.frontmatter["extracted_from"] == SPEC_PDF.name


def test_running_headers_stripped():
    res = extract_pdf(
        SPEC_PDF, source="misa", url="https://misa.gov.sa/en/spec", personas=["P1"],
    )
    # this footer line repeats on most pages and should be removed as boilerplate
    assert "Technical Specification\nPage" not in res.document.body
    occurrences = res.document.body.count(
        "Saudi Government RAG Agent — Technical Specification"
    )
    assert occurrences == 0


def test_ocr_fallback_flags_pages_when_ocr_unavailable():
    # Force every page to look "empty" so the OCR path triggers; NullOCR -> flagged.
    res = extract_pdf(
        SPEC_PDF, source="misa", url="https://misa.gov.sa/en/spec", personas=["P1"],
        ocr=NullOCR(), min_text_chars=10_000_000,
    )
    assert res.pages_needing_ocr == list(range(1, 12))
    assert res.document.frontmatter["extractor"] == "empty"


def test_ocr_fallback_used_when_backend_returns_text():
    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo".split()

    class FakeOCR:
        name = "fake"

        def page_text(self, pdf_path, page_index):
            # distinct text per page (realistic OCR output, not running boilerplate)
            return f"Scanned {words[page_index]} section with unique content."

    res = extract_pdf(
        SPEC_PDF, source="misa", url="https://misa.gov.sa/en/spec", personas=["P1"],
        ocr=FakeOCR(), min_text_chars=10_000_000,
    )
    assert res.document.frontmatter["extractor"] == "ocr"
    assert "alpha" in res.document.body
    assert res.pages_needing_ocr == []
