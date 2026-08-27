"""Fetch captions for a video, degrading gracefully when none are available.

Out of scope (per project spec): transcribing videos that have no captions.
If no transcript exists or the fetch is blocked, we return ("", False, reason)
and the pipeline still produces a brief from the description + any materials.
"""

from __future__ import annotations

import logging

from youtube_transcript_api import YouTubeTranscriptApi

log = logging.getLogger(__name__)


def fetch_transcript(video_id: str, languages: list[str]) -> tuple[str, bool, str]:
    """Return (text, ok, error).

    text : space-joined caption text (empty when ok is False)
    ok   : whether a transcript was retrieved
    error: short reason when ok is False (for logging / the brief)
    """
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=list(languages))
    except Exception as exc:  # noqa: BLE001 — any failure means "no usable transcript"
        reason = f"{type(exc).__name__}: {exc}".strip()
        log.info("No transcript for %s (%s)", video_id, reason)
        return "", False, reason

    parts = []
    for snippet in fetched:
        piece = (getattr(snippet, "text", "") or "").replace("\n", " ").strip()
        if piece:
            parts.append(piece)
    text = " ".join(parts).strip()
    if not text:
        return "", False, "empty transcript"
    return text, True, ""
