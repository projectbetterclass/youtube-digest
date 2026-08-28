"""Back-catalog importer: slowly pull past videos' transcripts into the library.

Transcripts only — no Claude summary — so it costs ~nothing in API; the transcripts
are what "ask your library" reads. It drips a small budget per run (Settings.
backfill_budget_per_run), reuses state.json for dedup/resume, and honors the same
transcript throttle + IP-block circuit-breaker as the main pipeline (a block just
stops the drip for this run and resumes next run).

Enumeration uses yt-dlp in flat/metadata mode (no video download).
"""

from __future__ import annotations

import logging
import time

from . import config as C
from .config import Channel, Settings
from .library import add_brief
from .models import Brief, Video
from .state import is_processed, mark_processed
from .transcript import TranscriptBlocked, fetch_transcript

log = logging.getLogger(__name__)


def enumerate_channel(channel_id: str, limit: int) -> list[tuple[str, str]]:
    """Return up to `limit` most-recent (video_id, title) for a channel, newest first."""
    import yt_dlp  # imported lazily so the rest of the tool doesn't need it

    url = f"https://www.youtube.com/channel/{channel_id}/videos"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "playlistend": limit,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    out: list[tuple[str, str]] = []
    for e in info.get("entries") or []:
        vid = e.get("id")
        if vid:
            out.append((vid, e.get("title") or ""))
    return out


def import_video(video: Video, settings: Settings) -> Brief:
    """Fetch a video's transcript and archive it (no summary). Raises TranscriptBlocked."""
    text, ok, blocked, _ = fetch_transcript(video.video_id, settings.transcript_languages)
    if blocked:
        raise TranscriptBlocked(video.video_id)

    vdir = C.ARCHIVE_DIR / video.video_id
    vdir.mkdir(parents=True, exist_ok=True)
    with open(vdir / "transcript.md", "w", encoding="utf-8") as fh:
        fh.write(f"# {video.title}\n\n<{video.url}>\n\n")
        fh.write(text if (ok and text) else "_No transcript/captions were available for this video._")
        fh.write("\n")

    return Brief(
        video=video,
        transcript_available=ok,
        key_points=[],
        takeaway="",
        verdict="",
        verdict_reason="",
        materials_notes="",
        listed_links=[],
        downloaded_materials=[],
        archive_dir=f"data/archive/{video.video_id}",
    )


def run_backfill(settings: Settings, channels: list[Channel], state: dict, library: dict) -> int:
    """Drip up to backfill_budget_per_run past videos into the library. Returns the count."""
    budget = settings.backfill_budget_per_run
    if budget <= 0:
        return 0

    imported = 0
    for channel in channels:
        if imported >= budget:
            break
        if channel.backfill <= 0:
            continue
        try:
            candidates = enumerate_channel(channel.channel_id, channel.backfill)
        except Exception as exc:  # noqa: BLE001 — one bad channel shouldn't stop the drip
            log.warning("Backfill enumerate failed for %s: %s", channel.name, exc)
            continue

        for vid, title in candidates:
            if imported >= budget:
                break
            if is_processed(state, vid):
                continue
            video = Video(
                video_id=vid,
                title=title,
                channel_name=channel.name,
                channel_id=channel.channel_id,
                url=f"https://www.youtube.com/watch?v={vid}",
                published=None,
                description="",
            )
            time.sleep(settings.transcript_delay_seconds)  # throttle
            try:
                brief = import_video(video, settings)
            except TranscriptBlocked:
                log.warning("Backfill hit a transcript IP-block; stopping drip (resumes next run).")
                return imported
            except Exception as exc:  # noqa: BLE001
                log.warning("Backfill failed for %s (%s): %s", title, vid, exc)
                continue
            add_brief(library, brief)
            mark_processed(state, video, had_materials=False, transcript_available=brief.transcript_available)
            imported += 1

    return imported
