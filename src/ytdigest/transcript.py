"""Fetch captions for a video, degrading gracefully when none are available.

Out of scope (per project spec): transcribing videos that have no captions.
If no transcript exists or the fetch is blocked, we return ("", False, reason)
and the pipeline still produces a brief from the description + any materials.

YouTube blocks most cloud-provider IPs (GitHub Actions included), so on a runner
the fetch fails with RequestBlocked unless it goes through a residential proxy.
Configure one via environment variables (set as GitHub secrets):

  * Webshare (recommended — the library rotates its residential pool for you):
      WEBSHARE_PROXY_USERNAME, WEBSHARE_PROXY_PASSWORD
  * Any generic HTTP/HTTPS proxy:
      YTDIGEST_PROXY_HTTP_URL, YTDIGEST_PROXY_HTTPS_URL

With none set, it runs proxy-free (fine locally; blocked on cloud IPs).
"""

from __future__ import annotations

import logging
import os
import time

from youtube_transcript_api import YouTubeTranscriptApi

log = logging.getLogger(__name__)


class TranscriptBlocked(Exception):
    """Raised when transcript fetching is IP rate-limited — transient, retry later."""


def _is_ip_block(exc: Exception) -> bool:
    """True for YouTube per-IP rate-limit errors (IpBlocked / RequestBlocked)."""
    return "Blocked" in type(exc).__name__ or "blocking requests from your IP" in str(exc)


def _build_proxy_config():
    """Return a youtube-transcript-api proxy config from env, or None."""
    user = os.environ.get("WEBSHARE_PROXY_USERNAME")
    pw = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    if user and pw:
        try:
            from youtube_transcript_api.proxies import WebshareProxyConfig

            log.info("Using Webshare residential proxy for transcript fetches.")
            return WebshareProxyConfig(proxy_username=user, proxy_password=pw)
        except Exception as exc:  # noqa: BLE001
            log.warning("Webshare proxy configured but could not be initialized: %s", exc)

    http_url = os.environ.get("YTDIGEST_PROXY_HTTP_URL")
    https_url = os.environ.get("YTDIGEST_PROXY_HTTPS_URL") or http_url
    if http_url or https_url:
        try:
            from youtube_transcript_api.proxies import GenericProxyConfig

            log.info("Using generic proxy for transcript fetches.")
            return GenericProxyConfig(http_url=http_url, https_url=https_url)
        except Exception as exc:  # noqa: BLE001
            log.warning("Generic proxy configured but could not be initialized: %s", exc)

    return None


def fetch_transcript(video_id: str, languages: list[str]) -> tuple[str, bool, bool, str]:
    """Return (text, ok, blocked, reason).

    text    : space-joined caption text (empty when ok is False)
    ok      : whether a transcript was retrieved
    blocked : True if the failure was an IP rate-limit (transient) — caller should
              DEFER the video and retry it on a later run, not finalize it.
    reason  : short reason when ok is False (for logging / the brief)
    """
    proxy_config = _build_proxy_config()
    reason = ""
    for attempt in range(2):  # one retry, only for a transient IP block
        try:
            api = YouTubeTranscriptApi(proxy_config=proxy_config) if proxy_config else YouTubeTranscriptApi()
            fetched = api.fetch(video_id, languages=list(languages))
        except Exception as exc:  # noqa: BLE001 — any failure means "no usable transcript"
            reason = f"{type(exc).__name__}: {exc}".strip()
            blocked = _is_ip_block(exc)
            if blocked and attempt == 0:
                log.info("Transcript for %s IP-blocked; backing off 20s then retrying", video_id)
                time.sleep(20)
                continue
            log.info("No transcript for %s (%s)", video_id, reason)
            return "", False, blocked, reason

        parts = []
        for snippet in fetched:
            piece = (getattr(snippet, "text", "") or "").replace("\n", " ").strip()
            if piece:
                parts.append(piece)
        text = " ".join(parts).strip()
        if not text:
            return "", False, False, "empty transcript"
        return text, True, False, ""

    return "", False, True, reason  # both attempts were IP-blocked
