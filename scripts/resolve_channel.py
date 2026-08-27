#!/usr/bin/env python
"""Resolve a YouTube channel URL/handle to its channel_id + a ready-to-paste watchlist entry.

Usage:
    python scripts/resolve_channel.py https://www.youtube.com/@3blue1brown
    python scripts/resolve_channel.py @veritasium
"""

from __future__ import annotations

import re
import sys

import requests

_UA = {"User-Agent": "Mozilla/5.0 (ytdigest channel resolver)"}
_CHANNEL_ID_RE = re.compile(r'"(?:externalId|channelId)":"(UC[0-9A-Za-z_-]{22})"')
_META_RE = re.compile(r'<meta itemprop="(?:identifier|channelId)" content="(UC[0-9A-Za-z_-]{22})"')
_NAME_RE = re.compile(r'<meta property="og:title" content="([^"]+)"')


def normalize(arg: str) -> str:
    if arg.startswith("http://") or arg.startswith("https://"):
        return arg
    if arg.startswith("@"):
        return f"https://www.youtube.com/{arg}"
    return f"https://www.youtube.com/@{arg}"


def resolve(url: str) -> tuple[str, str]:
    resp = requests.get(url, headers=_UA, timeout=30)
    resp.raise_for_status()
    html = resp.text
    m = _CHANNEL_ID_RE.search(html) or _META_RE.search(html)
    if not m:
        raise SystemExit(f"Could not find a channel_id on {url}")
    name_m = _NAME_RE.search(html)
    return m.group(1), (name_m.group(1) if name_m else "Channel name")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    url = normalize(sys.argv[1])
    channel_id, name = resolve(url)
    print(f"\nchannel_id: {channel_id}")
    print(f"RSS feed:   https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
    print("\nPaste into config/watchlist.yml under `channels:`\n")
    print(f"  - name: {name}")
    print(f"    channel_id: {channel_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
