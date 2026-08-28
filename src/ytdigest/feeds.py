"""Fetch and parse a channel's YouTube RSS feed (no API key required)."""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import requests

from .config import Channel
from .models import Video

log = logging.getLogger(__name__)

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
# A browser-like UA + EU consent cookie avoids YouTube's consent wall, which can
# otherwise return transient 404s for the RSS feed from EU/cloud IPs.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cookie": "CONSENT=YES+1",
}
# Statuses that are transient for YouTube's RSS endpoint (consent/throttle), worth retrying.
_RETRY_STATUS = {404, 429, 500, 502, 503}

# XML namespaces used in the YouTube Atom feed.
_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"
_MEDIA = "{http://search.yahoo.com/mrss/}"


def _parse_dt(text: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp like '2026-08-26T14:00:00+00:00'."""
    if not text:
        return None
    text = text.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    # Normalize to timezone-aware UTC so comparisons are safe.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_feed(xml_bytes: bytes, channel: Channel) -> list[Video]:
    """Parse feed XML bytes into a list of Video (newest-first, as YouTube orders it)."""
    root = ET.fromstring(xml_bytes)
    videos: list[Video] = []
    for entry in root.findall(f"{_ATOM}entry"):
        vid = (entry.findtext(f"{_YT}videoId") or "").strip()
        if not vid:
            continue
        title = (entry.findtext(f"{_ATOM}title") or "").strip()
        link_el = entry.find(f"{_ATOM}link")
        url = (
            link_el.get("href")
            if link_el is not None and link_el.get("href")
            else f"https://www.youtube.com/watch?v={vid}"
        )
        author = (entry.findtext(f"{_ATOM}author/{_ATOM}name") or channel.name).strip()
        published = _parse_dt(entry.findtext(f"{_ATOM}published") or "")

        description = ""
        group = entry.find(f"{_MEDIA}group")
        if group is not None:
            description = (group.findtext(f"{_MEDIA}description") or "").strip()

        videos.append(
            Video(
                video_id=vid,
                title=title,
                channel_name=author,
                channel_id=channel.channel_id,
                url=url,
                published=published,
                description=description,
            )
        )
    return videos


def fetch_channel_videos(
    channel: Channel,
    session: Optional[requests.Session] = None,
    timeout: int = 20,
    retries: int = 3,
) -> list[Video]:
    """Download and parse one channel's feed, retrying transient failures.

    Raises the last error if every attempt fails (the caller skips that channel).
    """
    url = FEED_URL.format(channel_id=channel.channel_id)
    sess = session or requests.Session()
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = sess.get(url, timeout=timeout, headers=_HEADERS)
            if resp.status_code == 200:
                return parse_feed(resp.content, channel)
            if resp.status_code in _RETRY_STATUS and attempt < retries - 1:
                log.info("Feed %s returned %s, retrying (%d/%d)",
                         channel.name, resp.status_code, attempt + 1, retries - 1)
                time.sleep(1.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            return parse_feed(resp.content, channel)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    if last_exc:
        raise last_exc
    return []
