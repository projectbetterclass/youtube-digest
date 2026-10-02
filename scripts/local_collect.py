"""Local transcript collector — a stopgap for while GitHub Actions is unavailable.

Pulls transcripts (no AI briefs) for the named channels using the same back-catalog drip
the cloud job uses — each channel's N most-recent uploads — so new videos are picked up as
well as older ones. Then commits and pushes data/ to main the way the cloud job does.

Run by hand on the PC when the user says "collect my priority channels" (nothing schedules
it). It steps aside by itself once the cloud digest is committing again, so the two never
write data/ at the same time. Log: %LOCALAPPDATA%\\ytdigest\\local_collect.log

    python scripts/local_collect.py                          # the PRIORITY channels below
    python scripts/local_collect.py --channel "Ben Yanes"    # or name channels explicitly
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ytdigest import config as C  # noqa: E402 — importing config also loads .env (proxy creds)
from ytdigest.backfill import run_backfill  # noqa: E402
from ytdigest.library import load_library, save_library, write_index  # noqa: E402
from ytdigest.state import load_state, save_state  # noqa: E402

log = logging.getLogger("local_collect")
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", ROOT)) / "ytdigest"
LOCK = ROOT / "tmp_downloads" / "local_collect.lock"
BATCH = 10  # save after every batch so an interrupted run keeps its progress
PUSH_EVERY = 100  # commit + push this often during a long run
# The user's priority channels (their choice; only these unless they name others).
PRIORITY = ["JulienHimself", "HealthyGamerGG", "Ben Yanes",
            "Tom Nash", "Ticker Symbol: YOU", "BWB - Business With Brian", "David Carbutt",
            "Felix & Friends (Goat Academy)"]


def select_channels(channels, names):
    """The watchlist entries for `names` (case-insensitive); unknown names are an error."""
    wanted = {n.lower(): n for n in names}
    found = [c for c in channels if c.name.lower() in wanted]
    missing = set(wanted) - {c.name.lower() for c in found}
    if missing:
        raise SystemExit(f"Not in config/watchlist.yml: {', '.join(sorted(wanted[m] for m in missing))}")
    return found


def git(*args: str) -> str:
    exe = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"
    out = subprocess.run([exe, *args], cwd=ROOT, capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def cloud_is_back() -> bool:
    """True when the cloud digest has committed in the last day (Actions is working again)."""
    return bool(git("log", "origin/main", "--since=24.hours", "--grep=^digest: update", "--format=%h"))


def _save(state, library) -> None:
    save_state(C.STATE_PATH, state)
    save_library(C.LIBRARY_PATH, library)
    write_index(C.INDEX_PATH, library)


def push(names: list[str], n: int) -> None:
    """Commit data/ and push, the way the cloud job does."""
    git("add", "data/")
    if not git("diff", "--cached", "--name-only"):
        return  # nothing changed — nothing to commit
    git("commit", "-q", "-m", f"local: +{n} transcripts ({', '.join(names)})")
    git("pull", "-q", "--rebase", "--autostash", "origin", "main")
    git("push", "-q", "origin", "main")


def failed_this_run(state: dict, names: set[str], since: str) -> list[str]:
    """Videos from these channels recorded without a transcript during this run.

    Through the rotating proxy these are mostly a 429 on one exit IP (YouTube's "sorry"
    page) rather than a video with no captions, so they are worth one retry.
    """
    return [vid for vid, r in state.get("processed", {}).items()
            if r.get("channel") in names and not r.get("transcript_available")
            and (r.get("processed_at") or "") >= since]


def collect(names: list[str], max_total: int) -> int:
    settings, channels = C.load_config()
    chans = select_channels(channels, names)
    batch = dataclasses.replace(settings, backfill_budget_per_run=BATCH)
    cache: dict = {}  # enumerate each channel once per run, not once per batch
    since = datetime.now(timezone.utc).isoformat()
    total = pushed = 0
    while total < max_total:
        LOCK.touch()  # keep the lock fresh through a long run
        state, library = load_state(C.STATE_PATH), load_library(C.LIBRARY_PATH)
        n = run_backfill(batch, chans, state, library, cache=cache)
        if n:
            _save(state, library)
        total += n
        log.info("batch +%d (total %d)", n, total)
        if total - pushed >= PUSH_EVERY:  # get progress off the PC during a long run
            push(names, total - pushed)
            pushed = total
        if n < BATCH:
            break

    state, library = load_state(C.STATE_PATH), load_library(C.LIBRARY_PATH)
    retry = failed_this_run(state, {c.name for c in chans}, since)
    if retry:
        for vid in retry:
            del state["processed"][vid]
        n = run_backfill(dataclasses.replace(settings, backfill_budget_per_run=len(retry)),
                         chans, state, library, cache=cache)
        _save(state, library)
        still = len(failed_this_run(state, {c.name for c in chans}, since))
        log.info("retried %d without a transcript: %d re-imported, %d still without", len(retry), n, still)
    if total > pushed or retry:  # the retry pass rewrites state even when nothing new arrived
        push(names, total - pushed)
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--channel", action="append", help="watchlist channel name (repeatable; default: PRIORITY)")
    ap.add_argument("--max", type=int, default=2000, help="safety cap on transcripts pulled in one run")
    args = ap.parse_args()
    args.channel = args.channel or PRIORITY

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_DIR / "local_collect.log", level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", encoding="utf-8",
    )
    LOCK.parent.mkdir(exist_ok=True)
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 3 * 3600:
        log.info("another run holds the lock — skipping")
        return 0
    LOCK.write_text(str(os.getpid()))
    try:
        git("fetch", "-q", "origin")
        if cloud_is_back():
            log.info("cloud digest is committing again — local collector standing down")
            return 0
        git("pull", "-q", "--rebase", "--autostash", "origin", "main")
        n = collect(args.channel, args.max)
        log.info("done: %d new transcript(s)%s", n, ", pushed" if n else "")
        return 0
    except Exception:  # noqa: BLE001 — log it; the next scheduled run retries
        log.exception("run failed")
        return 1
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
