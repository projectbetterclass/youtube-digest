#!/usr/bin/env python
"""Backfill data/library.json + data/archive/INDEX.md from already-processed videos.

Videos seeded from state.json won't have a verdict/takeaway (those are only produced
when a video is summarized); future runs fill those in. Run this once so the index
exists and covers what's already been archived.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ytdigest import config as C  # noqa: E402
from ytdigest.library import load_library, save_library, write_index  # noqa: E402
from ytdigest.state import load_state  # noqa: E402


def main() -> int:
    state = load_state(C.STATE_PATH)
    library = load_library(C.LIBRARY_PATH)
    videos = library.setdefault("videos", {})

    added = 0
    for vid, rec in state.get("processed", {}).items():
        if vid in videos:
            continue
        videos[vid] = {
            "channel": rec.get("channel", ""),
            "title": rec.get("title", ""),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "published": rec.get("published"),
            "verdict": "",
            "takeaway": "",
            "had_materials": rec.get("had_materials", False),
            "transcript_available": rec.get("transcript_available", False),
            "transcript_path": f"data/archive/{vid}/transcript.md",
        }
        added += 1

    save_library(C.LIBRARY_PATH, library)
    idx = write_index(C.INDEX_PATH, library)
    print(f"Seeded {added} video(s) from state; library now has {len(videos)}.")
    print(f"Wrote {idx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
