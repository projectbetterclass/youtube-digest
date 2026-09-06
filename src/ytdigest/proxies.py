"""Shared residential-proxy URL for the plain HTTP clients (RSS + yt-dlp).

youtube-transcript-api has its own WebshareProxyConfig (see transcript.py); this gives
the same rotating-residential endpoint as a URL string for `requests` and `yt-dlp`, so
RSS feeds and channel enumeration also go through the proxy — essential on cloud IPs,
which YouTube blocks directly. Returns None when no proxy is configured (local runs).
"""

from __future__ import annotations

import os
from typing import Optional


def youtube_proxy_url() -> Optional[str]:
    user = os.environ.get("WEBSHARE_PROXY_USERNAME")
    pw = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    if user and pw:
        # Webshare rotating-residential endpoint (the "-rotate" suffix picks a new IP per request).
        return f"http://{user}-rotate:{pw}@p.webshare.io:80"
    generic = os.environ.get("YTDIGEST_PROXY_HTTP_URL")
    return generic or None
