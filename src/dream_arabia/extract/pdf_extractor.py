"""PDF extraction pipeline (Phase 2).

Two-step extraction, per the spec:

1. **pdfplumber** — fast, deterministic text for digital PDFs (~80-90% of cases).
2. **OCR fallback** — runs only for pages where pdfplumber returns (near-)empty
   text (scanned PDFs). The spec names GLM-OCR; here the OCR step is a pluggable
   backend so any engine can be wired in. The default tries Tesseract
   (``pdf2image`` + ``pytesseract``) if installed, and degrades gracefully to a
   ``NullOCR`` that flags the pages as needing OCR rather than crashing — so the
   pipeline runs offline with no OCR engine present.

Output is always frontmatter markdown with the same structure as scraped pages,
so the graph builder treats PDFs and web pages identically.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pdfplumber

from ..markdown_io import Document, write as write_doc

# Pages with fewer than this many non-space chars are treated as "empty" and
# sent to the OCR fallback.
MIN_TEXT_CHARS = 20


class OCRUnavailable(RuntimeError):
    """Raised by an OCR backend that cannot run in this environment."""


class OCRBackend(Protocol):
    name: str

    def page_text(self, pdf_path: Path, page_index: int) -> str:
        """Return OCR'd text for a single (0-based) page."""
        ...


class NullOCR:
    """Fallback when no OCR engine is available — flags pages instead of crashing."""

    name = "null"

    def page_text(self, pdf_path: Path, page_index: int) -> str:  # noqa: D102
        raise OCRUnavailable("No OCR engine available (install pytesseract + pdf2image)")


class TesseractOCR:
    """OCR via pdf2image + pytesseract, imported lazily so it's optional."""

    name = "tesseract"

    def __init__(self, dpi: int = 200, lang: str = "eng"):
        self.dpi = dpi
        self.lang = lang

    def page_text(self, pdf_path: Path, page_index: int) -> str:  # noqa: D102
        try:
            import pytesseract
            from pdf2image import convert_from_path
        except Exception as exc:  # pragma: no cover - depends on optional deps
            raise OCRUnavailable(f"OCR deps missing: {exc}") from exc
        images = convert_from_path(
            str(pdf_path), dpi=self.dpi,
            first_page=page_index + 1, last_page=page_index + 1,
        )
        if not images:  # pragma: no cover - defensive
            return ""
        return pytesseract.image_to_string(images[0], lang=self.lang)


def default_ocr() -> OCRBackend:
    """Use Tesseract if its deps import; otherwise NullOCR (offline-safe)."""
    try:
        import pytesseract  # noqa: F401
        import pdf2image  # noqa: F401
        return TesseractOCR()
    except Exception:
        return NullOCR()


@dataclass
class PageResult:
    index: int
    text: str
    method: str  # "pdfplumber" | "ocr" | "empty"


@dataclass
class ExtractionResult:
    document: Document
    pages: list[PageResult]

    @property
    def methods(self) -> set[str]:
        return {p.method for p in self.pages if p.text.strip()}

    @property
    def pages_needing_ocr(self) -> list[int]:
        return [p.index + 1 for p in self.pages if p.method == "empty"]


# --- text cleaning --------------------------------------------------------

def _clean_page(text: str) -> str:
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    return "\n".join(lines).strip()


def _strip_repeated_headers(pages: list[str]) -> list[str]:
    """Drop short lines that repeat across most pages (running headers/footers).

    Lines are compared with digit runs normalised to ``#`` so page-numbered
    footers like ``... — Technical Specification Page 2`` collapse to one key.
    """
    if len(pages) < 3:
        return pages

    def key(ln: str) -> str:
        return re.sub(r"\d+", "#", ln.strip())

    counts: Counter[str] = Counter()
    for p in pages:
        for ln in {key(l) for l in p.splitlines() if l.strip()}:
            counts[ln] += 1
    threshold = max(2, int(0.6 * len(pages)))
    boilerplate = {
        k for k, c in counts.items()
        if c >= threshold and len(k) <= 80
    }
    out = []
    for p in pages:
        kept = [ln for ln in p.splitlines() if key(ln) not in boilerplate]
        out.append("\n".join(kept).strip())
    return out


def _to_markdown(title: str, page_texts: list[str]) -> str:
    body = "\n\n".join(t for t in page_texts if t.strip())
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    heading = f"# {title}\n\n" if title else ""
    return heading + body


# --- public API -----------------------------------------------------------

def extract_pdf(
    pdf_path: str | Path,
    *,
    source: str,
    url: str,
    personas: list[str],
    title: str | None = None,
    ocr: OCRBackend | None = None,
    extra_frontmatter: dict | None = None,
    min_text_chars: int = MIN_TEXT_CHARS,
) -> ExtractionResult:
    """Extract a PDF to a frontmatter Document (pdfplumber -> OCR fallback)."""
    pdf_path = Path(pdf_path)
    ocr = ocr or default_ocr()
    title = title or pdf_path.stem.replace("_", " ").replace("-", " ").title()

    results: list[PageResult] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = _clean_page(page.extract_text() or "")
            if len(text.replace(" ", "")) >= min_text_chars:
                results.append(PageResult(i, text, "pdfplumber"))
                continue
            # OCR fallback for (near-)empty pages
            try:
                ocr_text = _clean_page(ocr.page_text(pdf_path, i))
            except OCRUnavailable:
                ocr_text = ""
            if ocr_text:
                results.append(PageResult(i, ocr_text, "ocr"))
            else:
                results.append(PageResult(i, "", "empty"))

    cleaned = _strip_repeated_headers([r.text for r in results])
    md_body = _to_markdown(title, cleaned)

    methods = {r.method for r in results if r.text.strip()}
    extractor = "mixed" if len(methods) > 1 else (next(iter(methods)) if methods else "empty")

    frontmatter = {
        "source": source,
        "title": title,
        "url": url,
        "personas": list(personas),
        "extracted": True,
        "extracted_from": pdf_path.name,
        "extractor": extractor,
        "pages": len(results),
    }
    pages_needing_ocr = [r.index + 1 for r in results if r.method == "empty"]
    if pages_needing_ocr:
        frontmatter["pages_needing_ocr"] = pages_needing_ocr
    if extra_frontmatter:
        frontmatter.update(extra_frontmatter)

    doc = Document(frontmatter=frontmatter, body=md_body, path=None)
    return ExtractionResult(document=doc, pages=results)


def extract_to_file(
    pdf_path: str | Path,
    out_path: str | Path,
    **kwargs,
) -> ExtractionResult:
    """Extract a PDF and write the frontmatter markdown to ``out_path``."""
    result = extract_pdf(pdf_path, **kwargs)
    write_doc(result.document, out_path)
    result.document.path = Path(out_path)
    return result


def _cli() -> None:  # pragma: no cover - thin argparse wrapper
    import argparse

    ap = argparse.ArgumentParser(description="Extract a PDF to frontmatter markdown.")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--personas", nargs="+", required=True)
    ap.add_argument("--title")
    args = ap.parse_args()
    res = extract_to_file(
        args.pdf, args.out,
        source=args.source, url=args.url, personas=args.personas, title=args.title,
    )
    print(f"Wrote {args.out}  (extractor={res.document.frontmatter['extractor']}, "
          f"pages={res.document.frontmatter['pages']}, "
          f"needing_ocr={res.pages_needing_ocr})")


if __name__ == "__main__":  # pragma: no cover
    _cli()
