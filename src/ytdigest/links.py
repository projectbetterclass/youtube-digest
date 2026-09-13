"""Parse a video description for URLs and classify them.

Classification decides what happens downstream:
  * kind == "download": a safe document we will fetch and extract text from
    (direct PDF/PPTX, or a known slide host). Enforced elsewhere with https-only,
    content-type, size, and timeout checks.
  * kind == "list": everything else — shown in the brief as a mention, never fetched.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import Link

# Grab http(s) URLs; stop at whitespace or common wrapping/trailing punctuation.
_URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.IGNORECASE)
# Trailing punctuation that is almost never part of the actual URL.
_TRAILING = ".,;:!?'\")]}>"

_DOWNLOAD_EXTS = (".pdf", ".pptx", ".xls", ".xlsx", ".xlsm")
_EXCEL_EXTS = (".xls", ".xlsx", ".xlsm")
_SLIDE_HOSTS = {"slideshare.net", "speakerdeck.com"}
_PAPER_HOSTS = {"arxiv.org", "openreview.net", "papers.nips.cc", "aclanthology.org"}
# Registered domains we trust enough to fetch documents from over plain http, not just
# https. Kept deliberately tiny: these are academic pages (e.g. Aswath Damodaran's NYU
# site) that host slide PDFs and valuation spreadsheets under http:// on older pages.
# The https-only rule still applies to every other host.
_TRUSTED_HTTP_HOSTS = {"nyu.edu"}


def _ext_category(path: str) -> str | None:
    """Map a URL path to a document category, or None if it isn't a known doc type."""
    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith(".pptx"):
        return "pptx"
    if path.endswith(_EXCEL_EXTS):
        return "excel"
    return None


def extract_urls(text: str) -> list[str]:
    """Return de-duplicated URLs in first-seen order, with trailing punctuation trimmed."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(_TRAILING)
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower().split(":")[0]


def _registered(host: str) -> str:
    """Strip a leading 'www.' and any deeper subdomain to the last two labels."""
    host = host[4:] if host.startswith("www.") else host
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def classify_url(url: str) -> Link:
    host = _host(url)
    reg = _registered(host)
    path = (urlparse(url).path or "").lower()
    is_https = url.lower().startswith("https://")
    # http is allowed only for a tiny set of trusted academic hosts; https everywhere else.
    scheme_ok = is_https or reg in _TRUSTED_HTTP_HOSTS

    # Safe downloadable documents: a known doc extension over an allowed scheme.
    ext_cat = _ext_category(path)
    if scheme_ok and ext_cat:
        return Link(url=url, kind="download", category=ext_cat)
    if is_https and reg in _SLIDE_HOSTS:
        category = "speakerdeck" if reg == "speakerdeck.com" else "slideshare"
        return Link(url=url, kind="download", category=category)

    # Mention-only categories.
    if reg == "github.com":
        category = "github"
    elif reg in _PAPER_HOSTS:
        category = "paper"
    elif ext_cat:
        # A doc-type link we won't fetch (e.g. a .pdf/.xlsx over untrusted http) — list it.
        category = ext_cat
    else:
        category = "other"
    return Link(url=url, kind="list", category=category)


def classify_links(description: str) -> list[Link]:
    return [classify_url(u) for u in extract_urls(description)]
