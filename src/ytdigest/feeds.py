"""Fetch and parse a channel's YouTube RSS feed (no API key required)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import requests

from .config import Channel
from .models import Video

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
USER_AGENT = "ytdigest/0.1 (+https://github.com/) RSS reader"

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
) -> list[Video]:
    """Download and parse one channel's feed. Raises on network/HTTP errors."""
    url = FEED_URL.format(channel_id=channel.channel_id)
    sess = session or requests.Session()
    resp = sess.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return parse_feed(resp.content, channel)
