"""Plain data structures passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Video:
    """A single upload discovered from a channel RSS feed."""

    video_id: str
    title: str
    channel_name: str
    channel_id: str
    url: str
    published: Optional[datetime] = None
    description: str = ""
    short: bool = False  # a YouTube Short (from the channel's Shorts tab)


@dataclass
class Link:
    """A URL found in a video description, after classification."""

    url: str
    kind: str  # "download" (safe to fetch) or "list" (mention only)
    category: str  # pdf | pptx | slideshare | speakerdeck | github | paper | other


@dataclass
class Material:
    """A downloaded document whose text we extracted (or tried to)."""

    url: str
    category: str  # pdf | pptx | slideshare | speakerdeck
    filename: str = ""
    text: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.text) and not self.error


@dataclass
class Brief:
    """The finished summary for one video."""

    video: Video
    transcript_available: bool
    key_points: list[str]
    takeaway: str
    verdict: str  # skip | skim | watch
    verdict_reason: str
    materials_notes: str = ""
    reality_check: str = ""  # critical counterweight (adaptive; empty when disabled)
    listed_links: list[Link] = field(default_factory=list)
    downloaded_materials: list[Material] = field(default_factory=list)
    archive_dir: str = ""
    # A Short whose captions are mostly [music] markers: what the creator says is on screen
    music_captions: bool = False
    # Why there's no transcript (fetch_transcript's reason, e.g. "TranscriptsDisabled: ...")
    transcript_miss: str = ""

    @property
    def had_materials(self) -> bool:
        """True if at least one linked document was downloaded and extracted.

        Recorded in state so Phase 2 can cheaply skip videos that already have
        usable linked materials.
        """
        return any(m.ok for m in self.downloaded_materials)
