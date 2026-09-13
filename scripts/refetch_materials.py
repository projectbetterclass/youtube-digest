#!/usr/bin/env python
"""Re-fetch linked documents for already-archived videos with the improved classifier.

Why: the classifier used to be https-only and had no spreadsheet support, so many
older videos (notably Aswath Damodaran's, whose NYU pages serve slide PDFs and
valuation spreadsheets over http) never had their documents downloaded. This walks
the library, re-classifies each video's description, and fetches the now-eligible
docs — extracting text into the committed archive and (optionally) saving the RAW
files to a local, gitignored folder for downstream use (e.g. a valuation project).

Runs locally on the home IP (yt-dlp for descriptions; direct http(s) for the docs),
so no proxy or cloud runner is involved. Resumable via --only-missing.

Examples:
    # Validate on a few, save raw to a scratch dir, don't touch the archive/library:
    python scripts/refetch_materials.py --channel "Aswath Damodaran" \
        --only-missing --limit 5 --raw-dir /tmp/aswath_raw --dry-run

    # Full run: extract text into the library AND save raw files for the valuation project
    python scripts/refetch_materials.py --channel "Aswath Damodaran" --only-missing \
        --raw-dir "C:/Users/Gebruiker/Downloads/Valuation Agent/damodaran_source_files"
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ytdigest import config as C  # noqa: E402
from ytdigest.backfill import _fetch_description  # noqa: E402
from ytdigest.library import load_library, save_library, write_index  # noqa: E402
from ytdigest.links import classify_links  # noqa: E402
from ytdigest.materials import (  # noqa: E402
    _download, _extract_pdf_text, _extract_pptx_text, _extract_xlsx_text,
)

log = logging.getLogger("refetch")


def _extract(category: str, url: str, data: bytes) -> str:
    low = url.lower()
    if category == "pptx" or low.endswith(".pptx"):
        return _extract_pptx_text(data)
    if category == "excel" or low.endswith((".xlsx", ".xlsm")):
        if low.endswith(".xls"):
            return f"[legacy .xls workbook: {os.path.basename(url)} — see raw file]"
        return _extract_xlsx_text(data)
    if low.endswith(".xls"):
        return f"[legacy .xls workbook: {os.path.basename(url)} — see raw file]"
    return _extract_pdf_text(data)


def _has_materials_on_disk(vid: str) -> bool:
    return bool(glob.glob(str(C.ARCHIVE_DIR / vid / "materials" / "*.txt")))


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="Re-fetch linked docs with the improved classifier.")
    ap.add_argument("--channel", default=None, help="Only videos from this channel (library 'channel' name)")
    ap.add_argument("--only-missing", action="store_true", help="Skip videos that already have materials on disk")
    ap.add_argument("--limit", type=int, default=None, help="Process at most N videos")
    ap.add_argument("--raw-dir", default=None, help="Save raw downloaded files under here (<raw-dir>/<video_id>/)")
    ap.add_argument("--delay", type=float, default=1.5, help="Seconds between videos (politeness)")
    ap.add_argument("--dry-run", action="store_true", help="Download + save raw + report, but don't write archive text or library")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    settings, _ = C.load_config()
    library = load_library(C.LIBRARY_PATH)
    session = requests.Session()

    vids = [(v, r) for v, r in library.get("videos", {}).items()
            if (not args.channel or r.get("channel") == args.channel)]
    if args.only_missing:
        vids = [(v, r) for v, r in vids if not _has_materials_on_disk(v)]
    if args.limit:
        vids = vids[: args.limit]

    print(f"Candidates: {len(vids)} video(s)"
          + (f" from {args.channel}" if args.channel else "")
          + (" (missing-materials only)" if args.only_missing else ""))

    docs_saved = docs_text = vids_touched = 0
    for i, (vid, rec) in enumerate(vids, 1):
        try:
            desc = _fetch_description(vid)
        except Exception as exc:  # noqa: BLE001
            log.warning("desc fetch failed %s: %s", vid, exc)
            continue
        dl = [ln for ln in classify_links(desc) if ln.kind == "download"]
        if not dl:
            continue
        got_any = False
        for n, ln in enumerate(dl, 1):
            try:
                data, ctype = _download(ln.url, session, settings.max_download_bytes)
            except Exception as exc:  # noqa: BLE001
                log.warning("  download failed %s: %s", ln.url, exc)
                continue
            fname = ln.url.rsplit("/", 1)[-1].split("?")[0][:120] or f"{n}.bin"
            # Save raw file (the deliverable for downstream projects).
            if args.raw_dir:
                rawd = Path(args.raw_dir) / vid
                rawd.mkdir(parents=True, exist_ok=True)
                (rawd / fname).write_bytes(data)
                docs_saved += 1
            # Extract text.
            try:
                text = _extract(ln.category, ln.url, data)
            except Exception as exc:  # noqa: BLE001
                text = ""
                log.warning("  extract failed %s: %s", ln.url, exc)
            if text and not args.dry_run:
                md = C.ARCHIVE_DIR / vid / "materials"
                md.mkdir(parents=True, exist_ok=True)
                (md / f"{n:02d}_{ln.category}.txt").write_text(
                    f"Source: {ln.url}\n\n{text[: settings.max_material_chars]}\n", encoding="utf-8")
            if text:
                docs_text += 1
            got_any = True
            print(f"  [{i}/{len(vids)}] {vid} {ln.category} {fname} "
                  f"({len(data)//1024}KB, {len(text)} chars text)")
        if got_any:
            vids_touched += 1
            if not args.dry_run:
                library["videos"].setdefault(vid, rec)["had_materials"] = True
        time.sleep(args.delay)

    print(f"\nDone. videos with docs: {vids_touched} | docs saved: {docs_saved} | docs with text: {docs_text}")
    if not args.dry_run and vids_touched:
        save_library(C.LIBRARY_PATH, library)
        write_index(C.INDEX_PATH, library)
        print("Updated library.json + INDEX.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
