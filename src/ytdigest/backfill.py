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
import re
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
from .transcript import TranscriptBlocked, fetch_transcript, fetch_transcript_any_language

log = logging.getLogger(__name__)


def _opts(**extra) -> dict:
    """Base yt-dlp options, routed through the residential proxy when configured."""
    o = {"quiet": True, "no_warnings": True, "skip_download": True, **extra}
    purl = youtube_proxy_url()
    if purl:
        o["proxy"] = purl
    return o


def enumerate_channel(channel_id: str, limit: int, tab: str = "videos") -> list[tuple[str, str]]:
    """Up to `limit` most-recent (video_id, title) on a channel tab ("videos" or "shorts"), newest first."""
    import yt_dlp

    url = f"https://www.youtube.com/channel/{channel_id}/{tab}"
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


# What a flat listing shows for a playlist slot whose video is gone: nothing to fetch.
_GONE = ("[Deleted video]", "[Private video]")


def playlist_listing(playlist_id: str, limit: int = 10000) -> dict:
    """A playlist's title, owner and videos in playlist order (metadata only, one listing).

    Each video carries its own channel (a playlist can mix channels), falling back to the
    playlist's owner, plus its length in seconds when YouTube gives it. Deleted and private
    slots are left out.
    """
    import yt_dlp

    with yt_dlp.YoutubeDL(_opts(extract_flat=True, playlistend=limit)) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist_id}", download=False)
    owner = info.get("channel") or info.get("uploader") or ""
    owner_id = info.get("channel_id") or info.get("uploader_id") or ""
    videos = []
    for e in info.get("entries") or []:
        if not e.get("id") or (e.get("title") or "") in _GONE:
            continue
        videos.append({
            "id": e["id"],
            "title": e.get("title") or "",
            "channel": e.get("channel") or e.get("uploader") or owner,
            "channel_id": e.get("channel_id") or e.get("uploader_id") or owner_id,
            "duration": int(e["duration"]) if e.get("duration") else None,
        })
    return {"id": playlist_id, "title": info.get("title") or "", "channel": owner,
            "channel_id": owner_id, "videos": videos}


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


def _short_candidates(channel: Channel) -> list[tuple[str, str]]:
    """(video_id, title) of the channel's most-recent Shorts, up to `channel.shorts` (0 = none)."""
    if channel.shorts <= 0:
        return []
    return enumerate_channel(channel.channel_id, channel.shorts, tab="shorts")


_MUSIC = re.compile(r"\[\s*music\s*\]", re.I)


def _music_only_captions(text: str) -> bool:
    """True when a Short's captions are [music] markers with next to no words.

    Many training Shorts are a song plus text on screen: their captions are then just
    "[Music]", and the creator's actual tips are only in the picture. Rule: at least one
    marker and at most ~5 other words per marker. Calibrated on the library's Shorts: the
    one music-only Short sits at ~1.7 words per marker, while spoken Shorts with music under
    them sit at 15-31, so they aren't flagged. Captions that write out a song's words (with or
    without markers) can't be told apart from speech this way and are not flagged.
    """
    markers = len(_MUSIC.findall(text))
    if markers < 1:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z']*", _MUSIC.sub(" ", text))
    return len(words) <= 5 * markers


def import_video(video: Video, settings: Settings, session=None, fetch_materials: bool = False,
                 any_language: bool = False) -> Brief:
    """Archive a video's transcript (and optionally its linked slides). Raises TranscriptBlocked.

    With `any_language`, a video with no captions in the configured languages keeps its
    own-language captions, under a note naming the language (used for playlists the user names).
    """
    if any_language:
        text, ok, blocked, reason, lang = fetch_transcript_any_language(video.video_id, settings.transcript_languages)
    else:
        (text, ok, blocked, reason), lang = fetch_transcript(video.video_id, settings.transcript_languages), ""
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

    music = bool(video.short and ok and text and _music_only_captions(text))
    vdir = C.ARCHIVE_DIR / video.video_id
    (vdir / "materials").mkdir(parents=True, exist_ok=True)
    with open(vdir / "transcript.md", "w", encoding="utf-8") as fh:
        fh.write(f"# {video.title}\n\n<{video.url}>\n\n")
        if music:  # an italic note line: readers that skip placeholder notes skip it too
            fh.write("_A Short whose captions are mostly music: its content is probably shown "
                     "as text on screen, not spoken._\n\n")
        if ok and lang:  # same italic-note form: the captions aren't in a configured language
            fh.write(f"_The captions are in {lang}: this video has none in "
                     f"{', '.join(settings.transcript_languages)}._\n\n")
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
        music_captions=music,
        transcript_miss="" if ok else (reason or "no transcript"),
    )


def run_backfill(
    settings: Settings, channels: list[Channel], state: dict, library: dict,
    cache: dict | None = None, include_shorts: bool = False,
) -> int:
    """Drip up to backfill_budget_per_run past videos into the library. Returns the count.

    `cache` (channel_id -> candidates) lets a caller that runs several batches in a row
    enumerate each channel once instead of once per batch — enumeration goes through the
    metered proxy, and a whole-channel listing is many pages.

    Shorts are opt-in per run: with `include_shorts`, a channel with `shorts: N` also gets
    its N most-recent Shorts, after its videos. Routine runs (the cloud drip, a plain
    "collect my priority channels") leave it off, so a channel's Shorts tab is only listed and
    fetched when someone asks for it. The Videos and Shorts listings are separate: either can
    fail without losing the other.
    """
    budget = settings.backfill_budget_per_run
    if budget <= 0:
        return 0

    session = requests.Session()
    imported = 0
    for channel in channels:
        if imported >= budget:
            break
        wants_shorts = include_shorts and channel.shorts > 0
        if channel.backfill <= 0 and not wants_shorts:
            continue
        candidates: list[tuple[str, str, bool]] = []
        if channel.backfill > 0:
            try:
                if cache is not None and channel.channel_id in cache:
                    videos = cache[channel.channel_id]
                else:
                    videos = _candidates_for(channel)
                    if cache is not None:
                        cache[channel.channel_id] = videos
                candidates += [(v, t, False) for v, t in videos]
            except Exception as exc:  # noqa: BLE001 — one bad channel shouldn't stop the drip
                log.warning("Backfill enumerate failed for %s: %s", channel.name, exc)
        if wants_shorts:
            key = f"{channel.channel_id}#shorts"
            try:
                if cache is not None and key in cache:
                    shorts = cache[key]
                else:
                    shorts = _short_candidates(channel)
                    if cache is not None:
                        cache[key] = shorts
            except Exception as exc:  # noqa: BLE001 — e.g. "does not have a shorts tab"
                log.warning("Backfill Shorts listing failed for %s: %s", channel.name, exc)
                shorts = []
                if cache is not None:
                    cache[key] = shorts  # don't re-list a missing tab on every batch
            candidates += [(v, t, True) for v, t in shorts]

        for vid, title, short in candidates:
            if imported >= budget:
                break
            if is_processed(state, vid):
                continue
            video = Video(
                video_id=vid, title=title, channel_name=channel.name,
                channel_id=channel.channel_id,
                url=(f"https://www.youtube.com/shorts/{vid}" if short
                     else f"https://www.youtube.com/watch?v={vid}"),
                published=None, description="", short=short,
            )
            try:
                if _import_one(video, settings, session, state, library, channel.materials):
                    imported += 1
            except TranscriptBlocked:
                log.warning("Backfill hit a transcript IP-block; stopping drip (resumes next run).")
                return imported

    return imported


def run_playlist(settings: Settings, playlist: dict, state: dict, library: dict, budget: int) -> int:
    """Import up to `budget` of a playlist's videos not yet in the library, in playlist order.

    `playlist` is what playlist_listing returns. Videos keep their own channel, so a
    playlist can bring in channels that aren't on the watchlist (the user named the playlist),
    and a video with no captions in the configured languages keeps its own-language ones.
    """
    session = requests.Session()
    imported = 0
    for v in playlist["videos"]:
        if imported >= budget:
            break
        if is_processed(state, v["id"]):
            continue
        video = Video(video_id=v["id"], title=v["title"], channel_name=v["channel"],
                      channel_id=v["channel_id"], url=f"https://www.youtube.com/watch?v={v['id']}")
        try:
            if _import_one(video, settings, session, state, library, any_language=True):
                imported += 1
        except TranscriptBlocked:
            log.warning("Playlist import hit a transcript IP-block; stopping (a re-run resumes).")
            break
    return imported


def _import_one(video: Video, settings: Settings, session, state: dict, library: dict,
                materials: bool = False, any_language: bool = False) -> bool:
    """Throttle, import one video and record it. False when it failed (logged); raises TranscriptBlocked."""
    time.sleep(settings.transcript_delay_seconds)  # throttle
    try:
        brief = import_video(video, settings, session=session, fetch_materials=materials,
                             **({"any_language": True} if any_language else {}))
    except TranscriptBlocked:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("Backfill failed for %s (%s): %s", video.title, video.video_id, exc)
        return False
    add_brief(library, brief)
    mark_processed(state, video, had_materials=brief.had_materials,
                   transcript_available=brief.transcript_available,
                   transcript_miss=brief.transcript_miss)
    return True
