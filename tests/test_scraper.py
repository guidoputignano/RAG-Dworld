"""Phase 3 — scraper: offline HTML->markdown->frontmatter; live mode gated."""
from pathlib import Path

import pytest

from dream_arabia import markdown_io
from dream_arabia.scrape import (
    ScrapeConfig,
    ScrapeDisabled,
    ScrapeProxyRequired,
    ensure_allowed,
    html_to_markdown,
    page_to_document,
    find_pdf_links,
    find_internal_links,
    slug_from_url,
)
from config import SOURCES

# Pick whichever source is currently saudi_ip (flags are measured, not fixed).
SAUDI_IP_NS = next(ns for ns, s in SOURCES.items() if s.requires_saudi_ip)

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_HTML = (REPO_ROOT / "tests" / "fixtures" / "misa_sample.html").read_text(encoding="utf-8")
BASE_URL = "https://misa.gov.sa/en/investor-license"


def test_html_to_markdown_strips_script_style_and_keeps_content():
    md = html_to_markdown(SAMPLE_HTML)
    assert "tracking" not in md          # script dropped
    assert ".nav" not in md              # style dropped
    assert "100% ownership" in md
    assert "Foreign Investor Licensing" in md


def test_page_to_document_is_valid_frontmatter():
    doc = page_to_document(SAMPLE_HTML, source="misa", url=BASE_URL)
    # personas default to the source's personas from config
    assert doc.source == "misa"
    assert doc.personas == ["P1", "P2", "P4"]
    assert doc.frontmatter["scraped"] is True
    assert doc.frontmatter["tier"] == "T1"
    assert doc.title == "Foreign Investor Licensing | MISA"
    # round-trips through the parser (required frontmatter present)
    reparsed = markdown_io.parse(markdown_io.dumps(doc))
    assert reparsed.source == "misa"


def test_find_pdf_and_internal_links():
    pdfs = find_pdf_links(SAMPLE_HTML, BASE_URL)
    assert pdfs == ["https://misa.gov.sa/app/uploads/2025/03/Investor-Guide.pdf"]
    internal = find_internal_links(SAMPLE_HTML, BASE_URL)
    assert "https://misa.gov.sa/en/rhq" in internal
    assert "https://misa.gov.sa/en" in internal
    # external link and the PDF are excluded from internal crawl set
    assert "https://investsaudi.sa/en" not in internal
    assert all(not u.endswith(".pdf") for u in internal)


def test_slug_from_url():
    assert slug_from_url("https://misa.gov.sa/en/rhq") == "rhq"
    assert slug_from_url("https://misa.gov.sa/en/") == "en"
    assert slug_from_url("https://misa.gov.sa/") == "index"


def test_live_disabled_by_default():
    cfg = ScrapeConfig.from_env(env={})  # nothing set
    assert cfg.live is False
    with pytest.raises(ScrapeDisabled):
        ensure_allowed("misa", cfg)


def test_saudi_ip_source_requires_proxy_when_live():
    cfg = ScrapeConfig(live=True, proxy=None, egress_region=None)
    # a saudi_ip source is refused without egress
    with pytest.raises(ScrapeProxyRequired):
        ensure_allowed(SAUDI_IP_NS, cfg)
    # with a proxy it is allowed
    ensure_allowed(SAUDI_IP_NS, ScrapeConfig(live=True, proxy="http://sa-proxy:8080"))


def test_open_source_allowed_when_live_without_proxy():
    # datasaudi is OPEN access -> no proxy needed
    ensure_allowed("datasaudi", ScrapeConfig(live=True))


def test_config_from_env_parses_flags():
    cfg = ScrapeConfig.from_env(env={
        "DREAM_SCRAPE_LIVE": "true",
        "DREAM_SCRAPE_PROXY": "http://sa-proxy:8080",
    })
    assert cfg.live is True
    assert cfg.has_saudi_egress is True
