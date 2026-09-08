"""Phase 2 — capture on-screen visuals (slides, charts, diagrams) for opted-in channels.

Why this is a separate job from the digest:
  * It downloads the actual video (video-only, ≤480p), which is bandwidth-heavy.
  * The cloud digest routes everything through a metered 1GB/mo residential proxy;
    pushing video through it would burn the month's bandwidth in a handful of clips.
  * So visuals run on the SELF-HOSTED (home) runner instead, on the home IP, with no
    proxy — free, unmetered. The cloud digest + library are unaffected and keep running.

How it works, per video (opt-in channels only, `visual: true` in the watchlist):
  1. Download the video, video-only, ≤ visual_max_height, to a temp file (yt-dlp).
  2. Reduce to a bounded set of CANDIDATE frames cheaply and locally:
       sample ~1 fps → keep scene changes (histogram shift) → de-dup near-identical
       frames (perceptual hash) → rank by a "slide prior" (flat fills + long straight
       lines, which charts have and b-roll does not) → cap to Settings.visual_frame_cap.
  3. Claude vision is the ACTUAL judge: it sees the candidates and returns only the
     ones that are informative slides/charts/diagrams, with a description + key text.
     (Validated during prototyping: no cheap pixel statistic reliably separates polished
     cinematic b-roll from real slides — vision does; the local step only bounds cost.)
  4. Write data/archive/<id>/visuals.md; delete the video; record the attempt in state.

The result feeds "ask your library": visuals.md sits next to transcript.md and is read
the same way (see CLAUDE.md).
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

from . import config as C
from .config import Channel, Settings
from .models import Video
from .state import mark_visual_done, visual_done

log = logging.getLogger(__name__)

# Lazy heavy imports (cv2/numpy/PIL/imagehash/yt_dlp) live inside functions so that
# importing this module — e.g. in the cloud digest, which never runs visuals — is cheap
# and does not require OpenCV to be installed there.

SYSTEM_PROMPT = (
    "You review frames sampled from a single YouTube video and identify which ones are "
    "INFORMATIVE ON-SCREEN VISUALS worth archiving: slides, charts, graphs, tables, "
    "diagrams, framework figures, or screens with readable data/text (numbers, labels, "
    "bullet points).\n\n"
    "IGNORE and do NOT return: cinematic b-roll and stock footage, talking-head shots, "
    "scenery/animation/simulations with no readable data, channel intros/outros, logos, "
    "lower-thirds, and transition frames. Polished b-roll can look 'clean' — judge by "
    "whether there is actual readable information, not by how pretty it is.\n\n"
    "For every frame you keep, extract the important on-screen text verbatim and briefly, "
    "especially numbers, axis labels, chart titles, and headings. Report only what is "
    "actually visible; never invent figures. If none of the frames are informative "
    "visuals, return an empty list."
)

VISUALS_TOOL = {
    "name": "submit_visuals",
    "description": "Record which sampled frames are informative on-screen visuals worth keeping.",
    "input_schema": {
        "type": "object",
        "properties": {
            "slides": {
                "type": "array",
                "description": "One entry per KEPT frame (informative visual). Empty if none.",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {
                            "type": "integer",
                            "description": "The frame number exactly as labeled above the image (0-based).",
                        },
                        "description": {
                            "type": "string",
                            "description": "One line: what this visual shows.",
                        },
                        "key_text": {
                            "type": "string",
                            "description": "The important on-screen text/numbers, transcribed concisely. Empty if none.",
                        },
                    },
                    "required": ["index", "description"],
                },
            }
        },
        "required": ["slides"],
    },
}


# ── Frame extraction ─────────────────────────────────────────────────────────

def _slide_prior(bgr) -> float:
    """Cheap 'slideness' score for ranking (NOT a classifier — Claude vision decides).

    Slides have large solid fills (high flat-pixel fraction) and long straight lines
    (axes, bars, rules, text baselines); photographic b-roll has neither. Validated on
    sample frames: a real bar chart scored ~15 vs ≤2.5 for desert/smoke/render b-roll.
    """
    import cv2
    import numpy as np

    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gi = g.astype(np.int16)
    gx = np.abs(np.diff(gi, axis=1))[:-1, :]
    gy = np.abs(np.diff(gi, axis=0))[:, :-1]
    flat = float((np.maximum(gx, gy) <= 2).mean())

    edges = cv2.Canny(g, 80, 200)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=80,
        minLineLength=max(20, g.shape[1] // 5), maxLineGap=6,
    )
    n_lines = 0 if lines is None else min(len(lines), 20)
    return flat * (1 + n_lines)


def candidate_frames(video_path: str, settings: Settings) -> list[tuple[float, object, float]]:
    """Return a bounded, de-duplicated, ranked list of (timestamp, bgr_frame, score).

    Sample ~1 fps, keep scene changes, drop near-duplicates via perceptual hash, then
    keep the top `visual_frame_cap` frames by slide prior. Bounding the count here is
    what keeps the downstream vision call cheap regardless of video length/style.
    """
    import cv2
    import imagehash
    from PIL import Image

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(round(fps)))  # ~1 sampled frame per second

    prev_hist = None
    idx = 0
    scenes: list[tuple[float, object]] = []
    while True:
        # grab() advances the stream cheaply; we only pay for the full decode+convert
        # (retrieve) on the ~1-per-second frames we actually sample.
        if not cap.grab():
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
            cv2.normalize(hist, hist)
            if prev_hist is None or cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL) < 0.72:
                scenes.append((idx / fps, frame.copy()))
            prev_hist = hist
        idx += 1
    cap.release()

    # De-dup near-identical frames (animated/incremental reveals collapse to one).
    kept: list[tuple[float, object, float]] = []
    hashes: list = []
    for ts, frame in scenes:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        ph = imagehash.phash(Image.fromarray(rgb))
        if any((ph - h) <= 8 for h in hashes):
            continue
        hashes.append(ph)
        kept.append((ts, frame, _slide_prior(frame)))

    # Cap: keep the most slide-like frames, then restore chronological order.
    kept.sort(key=lambda t: t[2], reverse=True)
    kept = kept[: settings.visual_frame_cap]
    kept.sort(key=lambda t: t[0])
    return kept


def _download_video(video_id: str, dest_dir: str, settings: Settings) -> str:
    """Download video-only ≤ visual_max_height to dest_dir; return the file path.

    No proxy: this job runs on the home runner, where the home IP is not blocked, so
    video downloads stay off the metered residential proxy.
    """
    import yt_dlp

    h = settings.visual_max_height
    out = os.path.join(dest_dir, f"{video_id}.mp4")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": out,
        # Video-only, no audio, ≤ target height — no ffmpeg merge needed, small files.
        "format": f"bestvideo[height<={h}][ext=mp4]/bestvideo[height<={h}]/best[height<={h}]",
        "max_filesize": settings.max_video_bytes,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    # yt-dlp may append a different container extension; find whatever landed.
    for p in Path(dest_dir).glob(f"{video_id}.*"):
        if p.is_file() and p.stat().st_size > 0:
            return str(p)
    raise RuntimeError("download produced no file (format unavailable or too large)")


def _encode_jpeg(bgr, max_width: int = 1024) -> str:
    """Downscale to <=max_width and return base64 JPEG (keeps the vision payload small)."""
    import cv2

    h, w = bgr.shape[:2]
    if w > max_width:
        bgr = cv2.resize(bgr, (max_width, int(h * max_width / w)))
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def describe_slides(
    video: Video,
    frames: list[tuple[float, object, float]],
    settings: Settings,
    client: Anthropic,
) -> list[dict]:
    """Ask Claude vision which candidate frames are real visuals; return kept slides.

    Each returned dict: {index, timestamp, description, key_text}. `index` maps back to
    `frames`, so the caller can recover the timestamp even if the model omits it.
    """
    content: list[dict] = [{
        "type": "text",
        "text": (
            f"Video: {video.title}\nChannel: {video.channel_name}\n\n"
            f"{len(frames)} frames sampled in chronological order follow, each labeled "
            "with its frame number. Return the frame numbers that are informative "
            "on-screen visuals."
        ),
    }]
    for i, (ts, frame, _score) in enumerate(frames):
        content.append({"type": "text", "text": f"Frame {i} (t={int(ts)}s):"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": _encode_jpeg(frame)},
        })

    message = client.messages.create(
        model=settings.model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        tools=[VISUALS_TOOL],
        tool_choice={"type": "tool", "name": "submit_visuals"},
        messages=[{"role": "user", "content": content}],
    )

    kept: list[dict] = []
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_visuals":
            for item in block.input.get("slides", []) or []:
                try:
                    idx = int(item.get("index"))
                except (TypeError, ValueError):
                    continue
                if not (0 <= idx < len(frames)):
                    continue
                kept.append({
                    "index": idx,
                    "timestamp": frames[idx][0],
                    "description": (item.get("description") or "").strip(),
                    "key_text": (item.get("key_text") or "").strip(),
                })
            break
    kept.sort(key=lambda k: k["timestamp"])
    return kept


def render_visuals_md(video: Video, kept: list[dict]) -> str:
    """Render the archived on-screen visuals as markdown (sits beside transcript.md)."""
    lines = [
        f"# On-screen visuals — {video.title}",
        "",
        f"<{video.url}>",
        "",
        "_Slides, charts, and diagrams read from the video by Claude vision. Text is "
        "transcribed from the screen and may contain OCR errors; not on-screen visuals "
        "are omitted._",
        "",
    ]
    if not kept:
        lines.append("_No informative on-screen visuals were found in this video._")
        lines.append("")
        return "\n".join(lines)

    for n, k in enumerate(kept, start=1):
        mm, ss = divmod(int(k["timestamp"]), 60)
        lines.append(f"## {n}. [{mm:02d}:{ss:02d}] {k['description']}".rstrip())
        if k.get("key_text"):
            lines.append("")
            lines.append(k["key_text"])
        lines.append("")
    return "\n".join(lines)


def process_video_visuals(
    video: Video, settings: Settings, client: Anthropic
) -> int:
    """Download, extract candidates, describe via vision, write visuals.md. Returns #slides.

    The temp video is always deleted (finally), even on failure.
    """
    tmp = tempfile.mkdtemp(prefix="ytvis_")
    try:
        path = _download_video(video.video_id, tmp, settings)
        frames = candidate_frames(path, settings)
        log.info("%s: %d candidate frame(s) after dedup/cap", video.video_id, len(frames))
        kept = describe_slides(video, frames, settings, client) if frames else []

        vdir = C.ARCHIVE_DIR / video.video_id
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "visuals.md").write_text(render_visuals_md(video, kept), encoding="utf-8")
        return len(kept)
    finally:
        try:
            for p in Path(tmp).glob("*"):
                p.unlink(missing_ok=True)
            os.rmdir(tmp)
        except OSError:
            pass


def select_pending(
    channels: list[Channel], state: dict, library: dict, budget: int,
) -> list[Video]:
    """Videos on opt-in channels that are archived but not yet visually captured.

    Ordered newest-first (most recent uploads get visuals first), capped to `budget`.
    """
    visual_ids = {c.channel_id for c in channels if c.wants_visuals}
    names = {c.channel_id: c.name for c in channels}
    if not visual_ids:
        return []

    videos = library.get("videos", {})
    pending: list[tuple[str, Video]] = []
    for vid, rec in videos.items():
        # Match by channel: library records store the display name, so resolve via
        # the watchlist name for any opted-in channel.
        cid = rec.get("channel_id")
        if cid is None:
            # Older records lack channel_id — fall back to matching the display name.
            cid = next((c.channel_id for c in channels if c.name == rec.get("channel")), None)
        if cid not in visual_ids:
            continue
        if visual_done(state, vid):
            continue
        # A missing transcript is fine here — a chart-heavy video with no captions is
        # exactly where captured visuals add the most, so we still process it.
        pending.append((
            rec.get("published") or "",
            Video(
                video_id=vid,
                title=rec.get("title") or vid,
                channel_name=rec.get("channel") or names.get(cid, ""),
                channel_id=cid,
                url=rec.get("url") or f"https://www.youtube.com/watch?v={vid}",
            ),
        ))
    pending.sort(key=lambda t: t[0], reverse=True)
    return [v for _, v in pending[:budget]]


def run_visuals(
    settings: Settings,
    channels: list[Channel],
    state: dict,
    library: dict,
    client: Optional[Anthropic] = None,
    budget: Optional[int] = None,
) -> int:
    """Enrich up to `budget` pending videos with on-screen visuals. Returns #processed.

    Marks every attempt in state (success or hard failure) so expensive downloads are
    not repeated. Records visuals_path on the library entry so the index can link it.
    """
    budget = settings.visual_budget_per_run if budget is None else budget
    pending = select_pending(channels, state, library, budget)
    if not pending:
        log.info("No pending videos for visual capture.")
        return 0

    client = client or Anthropic()
    done = 0
    for video in pending:
        try:
            n = process_video_visuals(video, settings, client)
        except Exception as exc:  # noqa: BLE001 — one bad video shouldn't stop the batch
            log.warning("Visual capture failed for %s (%s): %s", video.title, video.video_id, exc)
            mark_visual_done(state, video.video_id, slides=0, error=str(exc)[:200])
            continue
        mark_visual_done(state, video.video_id, slides=n)
        # The library/INDEX are owned by the (cloud) digest; it surfaces the visuals link
        # by detecting visuals.md on disk on its next run, so we don't write them here.
        log.info("Visuals: %s → %d slide(s)", video.video_id, n)
        done += 1
    return done
