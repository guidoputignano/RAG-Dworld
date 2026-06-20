"""PDF extraction (Phase 2): pdfplumber -> OCR fallback -> frontmatter markdown."""
from .pdf_extractor import (
    extract_pdf,
    extract_to_file,
    ExtractionResult,
    PageResult,
    OCRBackend,
    NullOCR,
    TesseractOCR,
    OCRUnavailable,
    default_ocr,
)

__all__ = [
    "extract_pdf",
    "extract_to_file",
    "ExtractionResult",
    "PageResult",
    "OCRBackend",
    "NullOCR",
    "TesseractOCR",
    "OCRUnavailable",
    "default_ocr",
]
