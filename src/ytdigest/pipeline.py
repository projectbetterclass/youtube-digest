"""Orchestrate one digest run: discover → transcript → materials → summarize → digest → deliver."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from anthropic import Anthropic

from . import config as C
from .backfill import run_backfill
from .config import Settings
from .delivery import deliver_github_issue
from .digest import render_digest, write_digest
from .feeds import fetch_channel_videos
from .library import add_brief, load_library, save_library, write_index
from .links import classify_links
from .materials import gather_materials
from .models import Brief, Material, Video
from .state import load_state, mark_processed, save_state, select_new_videos
from .summarize import summarize
from .transcript import TranscriptBlocked, fetch_transcript

log = logging.getLogger(__name__)


def _write_archive(video: Video, transcript_text: str, transcript_ok: bool, materials: list[Material]) -> str:
    """Persist transcript + extracted material text under data/archive/<video_id>/."""
    vdir = C.ARCHIVE_DIR / video.video_id
    (vdir / "materials").mkdir(parents=True, exist_ok=True)

    with open(vdir / "transcript.md", "w", encoding="utf-8") as fh:
        fh.write(f"# {video.title}\n\n<{video.url}>\n\n")
        if transcript_ok and transcript_text:
            fh.write(transcript_text)
        else:
            fh.write("_No transcript/captions were available for this video._")
        fh.write("\n")

    for i, m in enumerate(materials, start=1):
        if m.ok:
            with open(vdir / "materials" / f"{i:02d}_{m.category}.txt", "w", encoding="utf-8") as fh:
                fh.write(f"Source: {m.url}\n\n{m.text}\n")

    return f"data/archive/{video.video_id}"


def process_video(
    video: Video,
    settings: Settings,
    client: Optional[Anthropic] = None,
    session: Optional[requests.Session] = None,
) -> Brief:
    session = session or requests.Session()
    transcript_text, transcript_ok, blocked, _ = fetch_transcript(video.video_id, settings.transcript_languages)
    if blocked:
        # Transient IP rate-limit: defer this video (don't spend an API call or finalize
        # it) so a later run retries it with a transcript once the IP recovers.
        raise TranscriptBlocked(video.video_id)
    links = classify_links(video.description)
    materials = gather_materials(links, settings, session=session)

    data = summarize(video, transcript_text, transcript_ok, materials, links, settings, client=client)
    archive_dir = _write_archive(video, transcript_text, transcript_ok, materials)

    return Brief(
        video=video,
        transcript_available=transcript_ok,
        key_points=list(data.get("key_points") or []),
        takeaway=data.get("takeaway", ""),
        verdict=data.get("verdict", "skim"),
        verdict_reason=data.get("verdict_reason", ""),
        materials_notes=data.get("materials_notes", ""),
        reality_check=data.get("reality_check", ""),
        listed_links=[ln for ln in links if ln.kind == "list"],
        downloaded_materials=materials,
        archive_dir=archive_dir,
    )


def _discover(settings, channels, state, session, channel_filter, now) -> list[Video]:
    found: list[Video] = []
    for channel in channels:
        if channel_filter and channel.name.lower() != channel_filter.lower():
            continue
        try:
            videos = fetch_channel_videos(channel, session=session)
        except Exception as exc:  # noqa: BLE001 — one bad feed shouldn't kill the run
            log.warning("Feed fetch failed for %s: %s", channel.name, exc)
            continue
        found.extend(select_new_videos(videos, state, settings.max_age_days, now=now))
        time.sleep(settings.request_delay_seconds)

    # De-dup and order oldest-first so the digest reads chronologically.
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    seen: set[str] = set()
    ordered: list[Video] = []
    for v in sorted(found, key=lambda v: v.published or epoch):
        if v.video_id in seen:
            continue
        seen.add(v.video_id)
        ordered.append(v)
    return ordered


def run(
    config_path: Path | str | None = None,
    dry_run: bool = False,
    limit: Optional[int] = None,
    channel_filter: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[Brief]:
    settings, channels = C.load_config(config_path)
    state = load_state(C.STATE_PATH)
    library = load_library(C.LIBRARY_PATH)
    session = requests.Session()

    new_videos = _discover(settings, channels, state, session, channel_filter, now)
    if limit:
        new_videos = new_videos[:limit]
    new_videos = new_videos[: settings.max_videos_per_run]
    log.info("Found %d new video(s) to summarize.", len(new_videos))

    client = Anthropic() if new_videos else None
    briefs: list[Brief] = []
    for i, v in enumerate(new_videos):
        if i > 0:
            time.sleep(settings.transcript_delay_seconds)  # throttle transcript fetches
        try:
            brief = process_video(v, settings, client=client, session=session)
        except TranscriptBlocked:
            # IP is rate-limited now; every remaining transcript would block too.
            # Stop here and leave the rest unprocessed so a later run retries them.
            log.warning(
                "Transcript IP-block hit — deferring %d video(s) to a later run "
                "(left unprocessed so they're retried once the IP recovers).",
                len(new_videos) - i,
            )
            break
        except Exception as exc:  # noqa: BLE001 — skip a failed video, keep the run going
            log.exception("Failed to process '%s' (%s): %s", v.title, v.video_id, exc)
            continue
        briefs.append(brief)
        if not dry_run:
            mark_processed(
                state, v,
                had_materials=brief.had_materials,
                transcript_available=brief.transcript_available,
            )
            add_brief(library, brief)

    when = now or datetime.now(timezone.utc)
    if briefs:
        date_str = when.strftime("%Y-%m-%d")
        markdown = render_digest(date_str, briefs)
        path = write_digest(C.DIGESTS_DIR, date_str, markdown)
        log.info("Wrote digest: %s", path)
        if not dry_run:
            try:
                deliver_github_issue(
                    f"📺 YouTube Digest — {date_str}",
                    markdown,
                    digest_path=f"digests/{date_str}.md",
                )
            except Exception as exc:  # noqa: BLE001 — delivery is best-effort
                log.warning("Issue delivery failed: %s", exc)
    else:
        log.info("No new videos — nothing to summarize.")

    # Slow back-catalog drip (transcripts only), after the forward pass.
    imported = 0
    if not dry_run:
        try:
            imported = run_backfill(settings, channels, state, library)
            if imported:
                log.info("Back-catalog: imported %d transcript(s) this run.", imported)
        except Exception as exc:  # noqa: BLE001 — backfill is best-effort
            log.warning("Backfill error: %s", exc)

    if not dry_run:
        state["last_run"] = when.isoformat()
        save_state(C.STATE_PATH, state)
        if briefs or imported:
            save_library(C.LIBRARY_PATH, library)
            write_index(C.INDEX_PATH, library)
            log.info("Library index now has %d videos.", len(library.get("videos", {})))

    return briefs
