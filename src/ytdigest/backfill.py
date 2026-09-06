"""Back-catalog importer: slowly pull past videos into the library.

Transcripts (and, for channels with `materials: true`, their linked slide/PDF text)
are imported with no Claude summary, so it costs ~nothing in API. It drips a small
budget per run (Settings.backfill_budget_per_run), reuses state.json for dedup/resume,
and honors the transcript throttle + IP-block circuit-breaker.

Candidates come from a pre-built queue at data/backfill_queue/<channel_id>.json when it
exists (see scripts/prepare_backfill.py — used to exclude course playlists), otherwise
from the channel's most-recent uploads. Enumeration uses yt-dlp (metadata only).
"""

from __future__ import annotations

import json
import logging
import time

import requests

from . import config as C
from .config import Channel, Settings
from .library import add_brief
from .links import classify_links
from .materials import gather_materials
from .models import Brief, Video
from .proxies import youtube_proxy_url
from .state import is_processed, mark_processed
from .transcript import TranscriptBlocked, fetch_transcript

log = logging.getLogger(__name__)


def _opts(**extra) -> dict:
    """Base yt-dlp options, routed through the residential proxy when configured."""
    o = {"quiet": True, "no_warnings": True, "skip_download": True, **extra}
    purl = youtube_proxy_url()
    if purl:
        o["proxy"] = purl
    return o


def enumerate_channel(channel_id: str, limit: int) -> list[tuple[str, str]]:
    """Up to `limit` most-recent (video_id, title) for a channel, newest first."""
    import yt_dlp

    url = f"https://www.youtube.com/channel/{channel_id}/videos"
    with yt_dlp.YoutubeDL(_opts(extract_flat=True, playlistend=limit)) as ydl:
        info = ydl.extract_info(url, download=False)
    return [(e["id"], e.get("title") or "") for e in (info.get("entries") or []) if e.get("id")]


def enumerate_playlists(channel_id: str) -> list[tuple[str, str]]:
    """All (playlist_id, title) on a channel's Playlists tab."""
    import yt_dlp

    url = f"https://www.youtube.com/channel/{channel_id}/playlists"
    with yt_dlp.YoutubeDL(_opts(extract_flat=True)) as ydl:
        info = ydl.extract_info(url, download=False)
    return [(e["id"], e.get("title") or "") for e in (info.get("entries") or []) if e.get("id")]


def enumerate_playlist(playlist_id: str, limit: int = 10000) -> list[str]:
    """Video IDs in a playlist."""
    import yt_dlp

    with yt_dlp.YoutubeDL(_opts(extract_flat=True, playlistend=limit)) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist_id}", download=False)
    return [e["id"] for e in (info.get("entries") or []) if e.get("id")]


def _fetch_description(video_id: str) -> str:
    import yt_dlp

    with yt_dlp.YoutubeDL(_opts()) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    return info.get("description") or ""


def _candidates_for(channel: Channel) -> list[tuple[str, str]]:
    """(video_id, title) candidates: the pre-built queue if present, else recent uploads."""
    qpath = C.DATA_DIR / "backfill_queue" / f"{channel.channel_id}.json"
    if qpath.exists():
        rows = json.loads(qpath.read_text(encoding="utf-8"))
        cands = [(r[0], r[1] if len(r) > 1 else "") for r in rows]
        return cands[: channel.backfill] if channel.backfill > 0 else cands
    return enumerate_channel(channel.channel_id, channel.backfill)


def import_video(video: Video, settings: Settings, session=None, fetch_materials: bool = False) -> Brief:
    """Archive a video's transcript (and optionally its linked slides). Raises TranscriptBlocked."""
    text, ok, blocked, _ = fetch_transcript(video.video_id, settings.transcript_languages)
    if blocked:
        raise TranscriptBlocked(video.video_id)

    materials, listed = [], []
    if fetch_materials:
        try:
            video.description = _fetch_description(video.video_id)
            links = classify_links(video.description)
            listed = [ln for ln in links if ln.kind == "list"]
            materials = gather_materials(links, settings, session=session or requests.Session())
        except Exception as exc:  # noqa: BLE001 — materials are best-effort
            log.warning("Backfill materials failed for %s: %s", video.video_id, exc)

    vdir = C.ARCHIVE_DIR / video.video_id
    (vdir / "materials").mkdir(parents=True, exist_ok=True)
    with open(vdir / "transcript.md", "w", encoding="utf-8") as fh:
        fh.write(f"# {video.title}\n\n<{video.url}>\n\n")
        fh.write(text if (ok and text) else "_No transcript/captions were available for this video._")
        fh.write("\n")
    for i, m in enumerate(materials, start=1):
        if m.ok:
            with open(vdir / "materials" / f"{i:02d}_{m.category}.txt", "w", encoding="utf-8") as fh:
                fh.write(f"Source: {m.url}\n\n{m.text}\n")

    return Brief(
        video=video,
        transcript_available=ok,
        key_points=[],
        takeaway="",
        verdict="",
        verdict_reason="",
        listed_links=listed,
        downloaded_materials=materials,
        archive_dir=f"data/archive/{video.video_id}",
    )


def run_backfill(settings: Settings, channels: list[Channel], state: dict, library: dict) -> int:
    """Drip up to backfill_budget_per_run past videos into the library. Returns the count."""
    budget = settings.backfill_budget_per_run
    if budget <= 0:
        return 0

    session = requests.Session()
    imported = 0
    for channel in channels:
        if imported >= budget:
            break
        if channel.backfill <= 0:
            continue
        try:
            candidates = _candidates_for(channel)
        except Exception as exc:  # noqa: BLE001 — one bad channel shouldn't stop the drip
            log.warning("Backfill enumerate failed for %s: %s", channel.name, exc)
            continue

        for vid, title in candidates:
            if imported >= budget:
                break
            if is_processed(state, vid):
                continue
            video = Video(
                video_id=vid, title=title, channel_name=channel.name,
                channel_id=channel.channel_id,
                url=f"https://www.youtube.com/watch?v={vid}", published=None, description="",
            )
            time.sleep(settings.transcript_delay_seconds)  # throttle
            try:
                brief = import_video(video, settings, session=session, fetch_materials=channel.materials)
            except TranscriptBlocked:
                log.warning("Backfill hit a transcript IP-block; stopping drip (resumes next run).")
                return imported
            except Exception as exc:  # noqa: BLE001
                log.warning("Backfill failed for %s (%s): %s", title, vid, exc)
                continue
            add_brief(library, brief)
            mark_processed(state, video, had_materials=brief.had_materials, transcript_available=brief.transcript_available)
            imported += 1

    return imported
