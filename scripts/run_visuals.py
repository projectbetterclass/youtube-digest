#!/usr/bin/env python
"""CLI entrypoint for Phase 2 — on-screen visual capture (self-hosted runner).

Downloads recent videos on opted-in channels (`visual: true` in the watchlist),
extracts slide/chart frames, has Claude vision describe them, and writes
data/archive/<id>/visuals.md next to the transcript. Runs on the home runner so
video downloads stay off the metered residential proxy (see src/ytdigest/visuals.py).

Examples:
    python scripts/run_visuals.py                 # process up to the per-run budget
    python scripts/run_visuals.py --budget 2      # just a couple (handy for a first test)
    python scripts/run_visuals.py --dry-run       # process + write visuals.md, but don't save state/library
    python scripts/run_visuals.py --video VIDEOID # force one specific archived video
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ytdigest import config as C  # noqa: E402
from ytdigest.library import load_library  # noqa: E402
from ytdigest.state import load_state, save_state  # noqa: E402
from ytdigest.visuals import run_visuals  # noqa: E402


def main() -> int:
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    parser = argparse.ArgumentParser(description="Capture on-screen visuals for opted-in channels.")
    parser.add_argument("--config", default=None, help="Path to watchlist.yml")
    parser.add_argument("--budget", type=int, default=None, help="Max videos to process this run")
    parser.add_argument("--video", default=None, help="Force one archived video id (ignores opt-in/dedup)")
    parser.add_argument("--dry-run", action="store_true", help="Write visuals.md but don't save state/library")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings, channels = C.load_config(args.config)
    state = load_state(C.VISUALS_STATE_PATH)  # Phase 2's own ledger (never state.json)
    library = load_library(C.LIBRARY_PATH)     # read-only: which videos exist + metadata

    if args.video:
        # Single-video override: reconstruct a channel opt-in on the fly so select_pending
        # picks it, and clear any prior visual record so it re-runs.
        from ytdigest.models import Video

        rec = library.get("videos", {}).get(args.video)
        if not rec:
            print(f"Video {args.video} is not in the library.")
            return 1
        state.get("visuals", {}).pop(args.video, None)
        from ytdigest.visuals import process_video_visuals
        from anthropic import Anthropic

        video = Video(
            video_id=args.video,
            title=rec.get("title") or args.video,
            channel_name=rec.get("channel") or "",
            channel_id=rec.get("channel_id") or "",
            url=rec.get("url") or f"https://www.youtube.com/watch?v={args.video}",
        )
        n = process_video_visuals(video, settings, Anthropic())
        print(f"{args.video}: {n} slide(s) → data/archive/{args.video}/visuals.md")
        return 0

    processed = run_visuals(settings, channels, state, library, budget=args.budget)
    print(f"\n{'=' * 60}\nVisual capture: {processed} video(s) processed\n{'=' * 60}")

    # Only the ledger is saved. library.json / INDEX.md stay owned by the cloud digest,
    # which surfaces the new visuals.md links on its next run (detected on disk).
    if processed and not args.dry_run:
        save_state(C.VISUALS_STATE_PATH, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
