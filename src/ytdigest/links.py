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

_DOWNLOAD_EXTS = (".pdf", ".pptx")
_SLIDE_HOSTS = {"slideshare.net", "speakerdeck.com"}
_PAPER_HOSTS = {"arxiv.org", "openreview.net", "papers.nips.cc", "aclanthology.org"}


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

    # Safe downloadable documents (https only).
    if is_https and path.endswith(".pdf"):
        return Link(url=url, kind="download", category="pdf")
    if is_https and path.endswith(".pptx"):
        return Link(url=url, kind="download", category="pptx")
    if is_https and reg in _SLIDE_HOSTS:
        category = "speakerdeck" if reg == "speakerdeck.com" else "slideshare"
        return Link(url=url, kind="download", category=category)

    # Mention-only categories.
    if reg == "github.com":
        category = "github"
    elif reg in _PAPER_HOSTS:
        category = "paper"
    elif path.endswith(_DOWNLOAD_EXTS):
        # A .pdf/.pptx that wasn't https — list it, don't fetch it.
        category = "pdf" if path.endswith(".pdf") else "pptx"
    else:
        category = "other"
    return Link(url=url, kind="list", category=category)


def classify_links(description: str) -> list[Link]:
    return [classify_url(u) for u in extract_urls(description)]
