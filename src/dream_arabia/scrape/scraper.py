"""Web scraper (Phase 3).

Pipeline: fetch HTML (httpx for static pages, Playwright for JS-rendered pages)
→ markdownify → frontmatter markdown, saved to
``knowledge_base/{source}/{slug}.md`` — the same shape as PDF extraction.

**Live scraping is OFF by default.** During development we do not hit the
network; the graph and agent are built from fixtures. Live fetching is refused
unless ``DREAM_SCRAPE_LIVE=true``, and refused for Saudi-IP-gated sources unless
a proxy / egress region is configured (many .gov.sa URLs require a Saudi IP).
The HTML→markdown→frontmatter and link/PDF discovery functions are pure and run
offline, so the conversion path is fully testable without a network.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

from markdownify import markdownify as _md

from config import SOURCES
from ..markdown_io import Document, write as write_doc


class ScrapeDisabled(RuntimeError):
    """Live scraping attempted while DREAM_SCRAPE_LIVE is not true."""


class ScrapeProxyRequired(RuntimeError):
    """A Saudi-IP-gated source was requested without a proxy/egress configured."""


def _as_bool(val: str | None) -> bool:
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ScrapeConfig:
    live: bool = False
    proxy: str | None = None
    egress_region: str | None = None
    user_agent: str = "DreamArabiaBot/0.1 (+https://example.org/dream-arabia)"
    timeout: float = 30.0

    @classmethod
    def from_env(cls, env: dict | None = None) -> "ScrapeConfig":
        env = env if env is not None else os.environ
        return cls(
            live=_as_bool(env.get("DREAM_SCRAPE_LIVE")),
            proxy=(env.get("DREAM_SCRAPE_PROXY") or None),
            egress_region=(env.get("DREAM_SCRAPE_EGRESS_REGION") or None),
        )

    @property
    def has_saudi_egress(self) -> bool:
        """A proxy or a configured egress region counts as Saudi egress."""
        return bool(self.proxy or self.egress_region)


def ensure_allowed(source: str, config: ScrapeConfig) -> None:
    """Gate a live fetch. Raises unless live mode (and egress, if required) is set."""
    if not config.live:
        raise ScrapeDisabled(
            "Live scraping is disabled. Set DREAM_SCRAPE_LIVE=true to enable "
            "(development should use fixtures, not live scraping)."
        )
    src = SOURCES.get(source)
    if src is not None and src.requires_saudi_ip and not config.has_saudi_egress:
        raise ScrapeProxyRequired(
            f"Source {source!r} requires a Saudi IP. Set DREAM_SCRAPE_PROXY or "
            f"DREAM_SCRAPE_EGRESS_REGION before scraping it."
        )


# --- pure conversion / discovery (offline-safe) ---------------------------

def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.strip().lower())
    text = re.sub(r"[\s_-]+", "_", text)
    return text.strip("_") or "page"


def slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    last = path.rsplit("/", 1)[-1] if path else ""
    last = re.sub(r"\.(html?|php|aspx)$", "", last, flags=re.I)
    return slugify(last) if last else "index"


def html_to_markdown(html: str) -> str:
    """Convert HTML to clean markdown (strip script/style, ATX headings)."""
    # markdownify's `strip` drops the tag but keeps inner text, so remove
    # script/style blocks (content included) before conversion.
    html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html, flags=re.I | re.S)
    md = _md(html, heading_style="ATX")
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def _extract_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip() or None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.I | re.S)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip() or None
    return None


def _hrefs(html: str, base_url: str) -> list[str]:
    raw = re.findall(r"""<a\b[^>]*?href\s*=\s*["']([^"'#]+)["']""", html, flags=re.I)
    return [urljoin(base_url, h) for h in raw]


def find_pdf_links(html: str, base_url: str) -> list[str]:
    """Absolute URLs of linked PDFs (handed to the PDF extractor, Phase 2)."""
    out = []
    for u in _hrefs(html, base_url):
        if urlparse(u).path.lower().endswith(".pdf") and u not in out:
            out.append(u)
    return out


def find_internal_links(html: str, base_url: str) -> list[str]:
    """Same-domain page links (for crawling), excluding PDFs."""
    base_host = urlparse(base_url).netloc
    out = []
    for u in _hrefs(html, base_url):
        p = urlparse(u)
        if p.scheme not in {"http", "https"}:
            continue
        if p.netloc != base_host:
            continue
        if p.path.lower().endswith(".pdf"):
            continue
        clean = u.split("?", 1)[0]
        if clean not in out:
            out.append(clean)
    return out


def page_to_document(
    html: str,
    *,
    source: str,
    url: str,
    personas: list[str] | None = None,
    title: str | None = None,
) -> Document:
    """Convert fetched HTML into a frontmatter Document (offline-safe)."""
    src = SOURCES.get(source)
    if personas is None:
        personas = list(src.personas) if src else []
    title = title or _extract_title(html) or slug_from_url(url).replace("_", " ").title()
    body = html_to_markdown(html)
    if not body.startswith("#"):
        body = f"# {title}\n\n{body}"
    frontmatter = {
        "source": source,
        "title": title,
        "url": url,
        "personas": list(personas),
        "scraped": True,
    }
    if src is not None:
        frontmatter["tier"] = src.tier
        frontmatter["access"] = src.access
    return Document(frontmatter=frontmatter, body=body, path=None)


# --- network fetch (guarded; not exercised offline) -----------------------

def fetch_static(url: str, config: ScrapeConfig) -> str:
    """Fetch a static page with httpx. Caller must pass ``ensure_allowed`` first."""
    import httpx  # local import keeps module import light

    proxies = config.proxy or None
    headers = {"User-Agent": config.user_agent}
    with httpx.Client(timeout=config.timeout, proxy=proxies, headers=headers, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def fetch_js(url: str, config: ScrapeConfig) -> str:
    """Fetch a JS-rendered page with Playwright (optional dependency, lazy import)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "Playwright is not installed. `pip install playwright && playwright install chromium`"
        ) from exc
    launch_kwargs = {}
    if config.proxy:
        launch_kwargs["proxy"] = {"server": config.proxy}
    with sync_playwright() as p:  # pragma: no cover - needs browser binaries
        browser = p.chromium.launch(headless=True, **launch_kwargs)
        try:
            page = browser.new_page(user_agent=config.user_agent)
            page.goto(url, timeout=int(config.timeout * 1000), wait_until="networkidle")
            return page.content()
        finally:
            browser.close()


def scrape_url(
    url: str,
    *,
    source: str,
    personas: list[str] | None = None,
    config: ScrapeConfig | None = None,
    use_js: bool = False,
    out_dir: str | Path | None = None,
) -> Document:
    """Live-fetch a URL → frontmatter Document, optionally saved to disk.

    Refuses unless live mode (and Saudi egress, where required) is configured.
    """
    config = config or ScrapeConfig.from_env()
    ensure_allowed(source, config)
    html = fetch_js(url, config) if use_js else fetch_static(url, config)
    doc = page_to_document(html, source=source, url=url, personas=personas)
    if out_dir is not None:
        path = Path(out_dir) / source / f"{slug_from_url(url)}.md"
        write_doc(doc, path)
        doc.path = path
    return doc
