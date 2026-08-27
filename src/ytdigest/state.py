"""Track which videos have already been processed (persisted as JSON, committed by CI)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .models import Video


def load_state(path: Path | str) -> dict:
    """Load state, returning a fresh skeleton if the file does not exist yet."""
    path = Path(path)
    if not path.exists():
        return {"last_run": None, "processed": {}}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("processed", {})
    data.setdefault("last_run", None)
    return data


def save_state(path: Path | str, state: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")


def is_processed(state: dict, video_id: str) -> bool:
    return video_id in state.get("processed", {})


def mark_processed(
    state: dict,
    video: Video,
    *,
    had_materials: bool = False,
    transcript_available: bool = False,
) -> None:
    """Record a video as done, plus signals Phase 2 will use for auto-detection."""
    state.setdefault("processed", {})[video.video_id] = {
        "title": video.title,
        "channel": video.channel_name,
        "published": video.published.isoformat() if video.published else None,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "had_materials": had_materials,
        "transcript_available": transcript_available,
    }


def select_new_videos(
    videos: list[Video],
    state: dict,
    max_age_days: int,
    now: Optional[datetime] = None,
) -> list[Video]:
    """Filter a feed to videos not yet processed and published within max_age_days."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)
    out: list[Video] = []
    for v in videos:
        if is_processed(state, v.video_id):
            continue
        if v.published is not None and v.published < cutoff:
            continue
        out.append(v)
    return out
