"""Daily local job: pick up new uploads on every watched channel, and screen-capture the new
videos on chart channels. Stands in for the cloud digest while GitHub Actions is off.

Run by Windows Task Scheduler (see scripts/install_daily_task.ps1) whenever the PC is on,
independent of any chat session:

    python scripts/daily_local.py            # skips if it ran in the last 12 hours
    python scripts/daily_local.py --force    # run now anyway

What it does, cheapest first:
  1. Reads each channel's RSS feed (its 15 newest uploads; a few KB through the proxy) and
     keeps uploads from the last 30 days that aren't in the library yet (new-uploads-only
     channels: the cloud digest's `max_age_days`). Shorts only for channels with `shorts: N`
     in the watchlist (the user's opt-in).
  2. Fetches their transcripts (no AI briefs), at most MAX_NEW per run.
  3. Screen-captures recent uploads (published in the last 30 days) on channels with
     `visual: true` that have no screen capture yet, newest first, at most VISUAL_BUDGET per run
     (home connection + Claude vision). Leftovers carry over to the next run; old back
     catalogs are never touched (they have no upload date in the library).
  4. Commits data/ and pushes. If someone else pushed meanwhile, the library records are
     merged (theirs + this run's) instead of leaving a half-done rebase.
It stops early, marking nothing, when the proxy data runs out or YouTube blocks the PC, and
stands down by itself once the cloud digest is committing again. A run only counts as done
once its push succeeded; otherwise the next trigger tries again.
Log: %LOCALAPPDATA%\\ytdigest\\daily.log  — last result: daily_status.txt next to it.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ytdigest import config as C  # noqa: E402 — importing config also loads .env (proxy + API key)
from ytdigest import visuals as V  # noqa: E402
from ytdigest.backfill import import_video  # noqa: E402
from ytdigest.feeds import fetch_channel_videos  # noqa: E402
from ytdigest.library import add_brief, load_library, save_library, write_index  # noqa: E402
from ytdigest.state import (load_state, mark_processed, mark_visual_done, save_state,  # noqa: E402
                            select_new_videos, visual_done)
from ytdigest.transcript import TranscriptBlocked  # noqa: E402

log = logging.getLogger("daily_local")
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", ROOT)) / "ytdigest"
STAMP = LOG_DIR / "daily_last_run.txt"
STATUS = LOG_DIR / "daily_status.txt"
LOCK = ROOT / "tmp_downloads" / "local_collect.lock"  # shared with local_collect.py: never both at once
MAX_AGE_DAYS = 30    # a feed shows 15 uploads; anything older is left to a manual run
MAX_NEW = 150        # transcripts per run (~0.4 MB of proxy each)
VISUAL_BUDGET = 10   # screen captures per run (~1.8 cents each)
MIN_HOURS_BETWEEN = 12
SAVE_EVERY = 10
# Library files merged record-by-record when someone else pushed during a run (path -> writer).
MERGE_FILES = {"data/state.json": save_state, "data/library.json": save_library,
               "data/visuals_state.json": save_state}
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # no console flashes under pythonw


def git(*args: str) -> subprocess.CompletedProcess:
    exe = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"
    return subprocess.run([exe, *args], cwd=ROOT, capture_output=True, text=True,
                          creationflags=_NO_WINDOW)


def cloud_is_back() -> bool:
    """True when the cloud digest has committed in the last day (Actions is working again)."""
    r = git("log", "origin/main", "--since=24.hours", "--grep=^digest: update", "--format=%h")
    return bool(r.stdout.strip())


def ran_recently(now: datetime, stamp: Path = STAMP) -> bool:
    try:
        last = datetime.fromisoformat(stamp.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return now - last < timedelta(hours=MIN_HOURS_BETWEEN)


def set_status(now: datetime, ok: bool, text: str) -> None:
    try:
        STATUS.write_text(f"{now.isoformat()} {'OK' if ok else 'FAILED'}: {text}\n", encoding="utf-8")
    except OSError:
        pass


def preflight() -> str:
    """'' when the working copy is safe to use (on main, no rebase/merge half-done, up to date)."""
    gitdir = ROOT / ".git"
    if any((gitdir / p).exists() for p in ("rebase-merge", "rebase-apply", "MERGE_HEAD")):
        return "a rebase or merge is half-done in the working copy; finish or abort it first"
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        return f"the working copy is on branch {branch!r}, not main"
    if git("fetch", "-q", "origin").returncode != 0:
        return "git fetch failed (offline?)"
    # A commit kept from an earlier run whose push failed is merged here, not left to block.
    return pull_or_merge("daily: library records kept from an earlier run (local)")


def discover(settings, channels, state, now, fetch=fetch_channel_videos, sleep=time.sleep,
             dates=None) -> tuple[list, int]:
    """(new uploads from every channel's RSS feed oldest first, number of feeds that failed).

    Shorts only where switched on. New-uploads-only channels (no `backfill`) keep the cloud
    digest's short window (`max_age_days`), so their older uploads aren't caught up behind the
    user's back. `dates`, if given, is filled with every feed video's upload date.
    """
    found, failed = [], 0
    for ch in channels:
        try:
            videos = fetch(ch)
        except Exception as exc:  # noqa: BLE001 — one bad feed shouldn't stop the rest
            log.warning("feed failed for %s: %s", ch.name, exc)
            failed += 1
            continue
        if dates is not None:
            dates.update({v.video_id: v.published for v in videos if v.published})
        max_age = MAX_AGE_DAYS if ch.backfill > 0 else settings.max_age_days
        for v in select_new_videos(videos, state, max_age, now=now):
            if v.short and ch.shorts <= 0:
                continue
            found.append((ch, v))
        sleep(settings.request_delay_seconds)
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    seen, out = set(), []
    for ch, v in sorted(found, key=lambda cv: cv[1].published or epoch):
        if v.video_id not in seen:
            seen.add(v.video_id)
            out.append((ch, v))
    return out, failed


def fill_missing_dates(library, dates) -> int:
    """Give library records stored without an upload date (collected back-catalog style, e.g.
    by local_collect.py) the date their channel's feed shows. Only a channel's newest uploads
    are in its feed, so this marks recent uploads as recent and leaves back catalogs dateless."""
    n = 0
    for vid, published in dates.items():
        rec = library.get("videos", {}).get(vid)
        if rec is not None and not rec.get("published"):
            rec["published"] = published.isoformat()
            n += 1
    return n


def _save(state, library) -> None:
    save_state(C.STATE_PATH, state)
    save_library(C.LIBRARY_PATH, library)


def collect(settings, new, state, library, importer=import_video, sleep=time.sleep) -> list:
    """Transcripts for the new uploads. Stops (marking nothing more) on a proxy run-out or block."""
    done = []
    for i, (ch, v) in enumerate(new[:MAX_NEW], start=1):
        sleep(settings.transcript_delay_seconds)
        try:
            brief = importer(v, settings, fetch_materials=ch.materials)
        except TranscriptBlocked:
            log.warning("stopping transcripts: the proxy data ran out or YouTube blocked the PC "
                        "(%d left for the next run)", len(new) - len(done))
            break
        except Exception as exc:  # noqa: BLE001
            log.warning("transcript failed for %s (%s): %s", v.title, v.video_id, exc)
            continue
        add_brief(library, brief)
        mark_processed(state, v, had_materials=brief.had_materials,
                       transcript_available=brief.transcript_available,
                       transcript_miss=brief.transcript_miss)
        done.append((ch, v))
        if i % SAVE_EVERY == 0:
            _save(state, library)
    if len(new) > MAX_NEW:
        log.info("%d more new uploads than the per-run cap; the next run takes them", len(new) - MAX_NEW)
    _save(state, library)
    return done


def capture_candidates(channels, vstate, library, now) -> list:
    """Recent uploads (published within MAX_AGE_DAYS) on visual channels with no capture yet,
    newest first. Back-catalog records have no upload date, so old backlogs are never picked."""
    cutoff = now - timedelta(days=MAX_AGE_DAYS)
    videos = library.get("videos", {})

    def recent(vid: str) -> bool:
        try:
            published = datetime.fromisoformat(videos.get(vid, {}).get("published") or "")
        except ValueError:
            return False
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return published >= cutoff

    pool = V.select_pending(channels, vstate, library, budget=10**9)  # newest first
    return [v for v in pool if recent(v.video_id)][:VISUAL_BUDGET]


def capture(settings, candidates, vstate, client, process=None) -> int:
    """Screen-capture the candidates. Stops, marking nothing more, on a YouTube block or no credit."""
    process = process or V.process_video_visuals
    read = 0
    for v in candidates:
        if visual_done(vstate, v.video_id):
            continue
        try:
            n = process(v, settings, client)
        except Exception as exc:  # noqa: BLE001
            if V._is_out_of_credit(exc) or V._is_bot_check(exc):
                log.warning("stopping screen capture (%s); the rest wait for the next run", str(exc)[:120])
                break
            log.warning("screen capture failed for %s (%s): %s", v.title, v.video_id, exc)
            mark_visual_done(vstate, v.video_id, slides=0, error=str(exc)[:200])
            continue
        mark_visual_done(vstate, v.video_id, slides=n)
        read += 1
    return read


def _union(theirs: dict, ours: dict) -> dict:
    """Theirs, plus every record of ours they don't have (one level of nesting: processed/videos/visuals)."""
    out = dict(theirs)
    for key, val in ours.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            merged = dict(out[key])
            for rid, rec in val.items():
                merged.setdefault(rid, rec)
            out[key] = merged
        else:
            out.setdefault(key, val)
    return out


def merge_with_origin(message: str) -> str:
    """Someone else pushed data meanwhile: put our records on top of theirs, record by record.

    After `rebase --abort` our unpushed commit(s) are HEAD. Move to origin/main keeping our files,
    bring back origin's versions of the tracked data, then add our records to them and rebuild
    INDEX.md. Our new archive folders aren't tracked on origin, so the checkout leaves them in
    place. Returns '' on success, else the reason (nothing is changed then).
    """
    if git("fetch", "-q", "origin").returncode != 0:
        return "git fetch failed (offline?)"
    outside = [p for p in git("diff", "--name-only", "origin/main...HEAD").stdout.splitlines()
               if p and not p.startswith("data/")]
    if outside:  # someone's unpushed work besides the library: leave it for a person
        return "unpushed local commits change files outside data/ (" + ", ".join(outside[:3]) + ")"
    try:
        ours = {f: json.loads((ROOT / f).read_text(encoding="utf-8")) for f in MERGE_FILES if (ROOT / f).exists()}
    except (OSError, ValueError) as exc:
        return f"can't read this run's data to merge: {exc}"
    for step in (("reset", "-q", "--mixed", "origin/main"), ("checkout", "origin/main", "--", "data/")):
        r = git(*step)
        if r.returncode != 0:
            return f"merge step {step[0]} failed: {r.stderr.strip()[:200]}"
    for f, mine in ours.items():
        p = ROOT / f
        try:
            theirs = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except ValueError:
            theirs = {}
        MERGE_FILES[f](p, _union(theirs, mine))
    write_index(ROOT / "data" / "archive" / "INDEX.md", load_library(ROOT / "data" / "library.json"))
    git("add", "data/")
    if not git("diff", "--cached", "--name-only", "--", "data/").stdout.strip():
        return ""  # theirs already had everything of ours
    r = git("commit", "-q", "-m", message + "\n\n(merged with records pushed meanwhile)", "--", "data/")
    return "" if r.returncode == 0 else "git commit failed: " + r.stderr.strip()[:200]


def pull_or_merge(message: str) -> str:
    """Bring origin's commits in under ours; on a conflict merge the records instead. '' when done."""
    r = git("pull", "-q", "--rebase", "--autostash", "origin", "main")
    if r.returncode == 0:
        return ""
    git("rebase", "--abort")
    log.info("pull conflicted (someone pushed meanwhile); merging library records instead")
    problem = merge_with_origin(message)
    return f"couldn't merge with what was pushed meanwhile: {problem}" if problem else ""


def commit_and_push(message: str) -> str:
    """'' when data/ is pushed (or there was nothing to push); otherwise the reason it isn't."""
    git("add", "data/")
    if git("diff", "--cached", "--name-only", "--", "data/").stdout.strip():
        r = git("commit", "-q", "-m", message, "--", "data/")
        if r.returncode != 0:
            return "git commit failed: " + r.stderr.strip()[:200]
    if not git("rev-list", "origin/main..HEAD").stdout.strip():
        return ""  # nothing unpushed
    for _ in range(2):
        problem = pull_or_merge(message)
        if problem:
            return problem + " (the commit is kept locally; the next run retries)"
        if git("push", "-q", "origin", "main").returncode == 0:
            log.info("pushed")
            return ""
    return "git push failed twice (the commit is kept locally; the next run pushes it)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="run even if it ran in the last 12 hours")
    ap.add_argument("--no-visuals", action="store_true", help="skip screen capture this run")
    args = ap.parse_args(argv)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOG_DIR / "daily.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    now = datetime.now(timezone.utc)
    if not args.force and ran_recently(now):
        log.info("ran in the last %d hours — nothing to do", MIN_HOURS_BETWEEN)
        return 0
    LOCK.parent.mkdir(exist_ok=True)
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 3 * 3600:
        log.info("another collection holds the lock — skipping")
        return 0
    LOCK.write_text(str(os.getpid()))
    try:
        problem = preflight()
        if problem:
            log.error("not running: %s", problem)
            set_status(now, False, problem)
            return 1
        if cloud_is_back():
            log.info("the cloud digest is committing again — standing down")
            set_status(now, True, "standing down: the cloud digest is back")
            return 0
        settings, channels = C.load_config()
        state, library = load_state(C.STATE_PATH), load_library(C.LIBRARY_PATH)
        dates = {}
        new, failed = discover(settings, channels, state, now, dates=dates)
        log.info("%d new upload(s) on %d channels", len(new), len({ch.name for ch, _ in new}))
        dated = fill_missing_dates(library, dates)
        if dated:
            log.info("gave %d earlier-collected upload(s) their date from the feeds", dated)
        # Every feed failing means the proxy data is used up (feeds go through it too) or the
        # PC is offline: screen capture still runs, but the run doesn't count, so the next
        # hourly check tries again (it costs nothing while the proxy refuses).
        feeds_down = bool(channels) and failed == len(channels)
        done = collect(settings, new, state, library)
        read = 0
        if not args.no_visuals and os.environ.get("ANTHROPIC_API_KEY"):
            vstate = load_state(C.VISUALS_STATE_PATH)
            todo = capture_candidates(channels, vstate, library, now)
            if todo:
                from anthropic import Anthropic

                read = capture(settings, todo, vstate, Anthropic())
                save_state(C.VISUALS_STATE_PATH, vstate)
        write_index(C.INDEX_PATH, library)
        got = sum(1 for _, v in done if library.get("videos", {}).get(v.video_id, {}).get("transcript_available"))
        problem = commit_and_push(f"daily: +{got} transcripts, +{read} screen captures (local)")
        summary = f"{len(new)} new found, {len(done)} collected ({got} with transcripts), {read} screen-captured"
        if feeds_down and not problem:
            problem = "every channel feed failed (proxy data used up, or offline); retrying at the next check"
        if problem:
            log.error("%s — %s", summary, problem)
            set_status(now, False, f"{summary}; {problem}")
            return 1
        log.info("done: %s", summary)
        set_status(now, True, summary)
        STAMP.write_text(now.isoformat(), encoding="utf-8")
        return 0
    except Exception as exc:  # noqa: BLE001 — log it; the next trigger tries again
        log.exception("daily run failed")
        set_status(now, False, f"crashed: {exc}"[:300])
        return 1
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
