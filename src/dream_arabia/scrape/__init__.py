"""Web scraping (Phase 3): fetch -> markdown -> frontmatter. Off by default."""
from .scraper import (
    ScrapeConfig,
    ScrapeDisabled,
    ScrapeProxyRequired,
    ensure_allowed,
    html_to_markdown,
    page_to_document,
    find_pdf_links,
    find_internal_links,
    slug_from_url,
    slugify,
    scrape_url,
    fetch_static,
    fetch_js,
)

__all__ = [
    "ScrapeConfig",
    "ScrapeDisabled",
    "ScrapeProxyRequired",
    "ensure_allowed",
    "html_to_markdown",
    "page_to_document",
    "find_pdf_links",
    "find_internal_links",
    "slug_from_url",
    "slugify",
    "scrape_url",
    "fetch_static",
    "fetch_js",
]
