#!/usr/bin/env python
"""Build data/backfill_queue/<channel_id>.json for channels that skip playlists.

For each channel with `skip_playlist_titles`, this enumerates its uploads (up to
`backfill_scan`), removes every video that belongs to a playlist whose title contains
one of those strings, and writes the remaining [video_id, title] list as the backfill
queue. Run it whenever you change a channel's skip rules. Enumeration is yt-dlp
metadata only (not affected by the transcript IP cooldown).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ytdigest import config as C  # noqa: E402
from ytdigest.backfill import enumerate_channel, enumerate_playlist, enumerate_playlists  # noqa: E402


def main() -> int:
    _, channels = C.load_config()
    qdir = C.DATA_DIR / "backfill_queue"
    qdir.mkdir(parents=True, exist_ok=True)

    for ch in channels:
        if not ch.skip_playlist_titles:
            continue
        pls = enumerate_playlists(ch.channel_id)
        pats = [p.lower() for p in ch.skip_playlist_titles]
        matched = [(pid, title) for pid, title in pls if any(p in title.lower() for p in pats)]

        exclude: set[str] = set()
        for pid, title in matched:
            exclude |= set(enumerate_playlist(pid))

        scan = ch.backfill_scan or ch.backfill
        uploads = enumerate_channel(ch.channel_id, scan)
        candidates = [[vid, title] for vid, title in uploads if vid not in exclude]

        qpath = qdir / f"{ch.channel_id}.json"
        qpath.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")
        print(
            f"{ch.name}: scanned {len(uploads)} uploads, skipped {len(matched)} playlists "
            f"({len(exclude)} excluded videos) -> {len(candidates)} candidates"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
