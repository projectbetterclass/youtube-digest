#!/usr/bin/env python
"""CLI entrypoint for one digest run.

Examples:
    python scripts/run.py                      # full run (used by the GitHub Action)
    python scripts/run.py --dry-run --limit 1  # summarize 1 newest video, no commit/issue/state
    python scripts/run.py --channel "3Blue1Brown"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make the src/ package importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ytdigest.digest import render_brief  # noqa: E402
from ytdigest.pipeline import run  # noqa: E402


def main() -> int:
    # The Windows CI console is cp1252 and can't encode emoji; force UTF-8 so printing
    # briefs (or logging unicode titles) can never crash the run after work is done.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — best-effort; older/redirected streams
            pass

    parser = argparse.ArgumentParser(description="Build the YouTube digest for new videos.")
    parser.add_argument("--config", default=None, help="Path to watchlist.yml (default: config/watchlist.yml)")
    parser.add_argument("--dry-run", action="store_true", help="Process + print, but don't save state or open an Issue")
    parser.add_argument("--limit", type=int, default=None, help="Only process the N newest new videos")
    parser.add_argument("--channel", default=None, help="Only this channel (matched by name)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    briefs = run(
        config_path=args.config,
        dry_run=args.dry_run,
        limit=args.limit,
        channel_filter=args.channel,
    )

    print(f"\n{'=' * 60}\n{len(briefs)} brief(s) produced\n{'=' * 60}\n")
    for b in briefs:
        print(render_brief(b))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
