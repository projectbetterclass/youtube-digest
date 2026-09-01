"""Load settings + watchlist, and centralize repo paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

# ── Repo paths (this file is src/ytdigest/config.py → parents[2] is the repo root)
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
STATE_PATH = DATA_DIR / "state.json"
ARCHIVE_DIR = DATA_DIR / "archive"
LIBRARY_PATH = DATA_DIR / "library.json"        # rich per-video index (for "ask your library")
INDEX_PATH = ARCHIVE_DIR / "INDEX.md"           # human/Claude-friendly library index
DIGESTS_DIR = REPO_ROOT / "digests"
TMP_DOWNLOADS = REPO_ROOT / "tmp_downloads"
CONFIG_PATH = REPO_ROOT / "config" / "watchlist.yml"

# Load .env for local runs (no-op in Actions, where the secret is a real env var).
load_dotenv(REPO_ROOT / ".env")


@dataclass
class Settings:
    model: str = "claude-haiku-4-5"
    max_age_days: int = 3
    transcript_languages: list[str] = field(default_factory=lambda: ["en"])
    request_delay_seconds: float = 1.0
    # Space out transcript fetches so a burst doesn't trip YouTube's per-IP rate limit
    # (seen as IpBlocked). Steady-state runs are small, so this is cheap.
    transcript_delay_seconds: float = 4.0
    max_videos_per_run: int = 50
    # How many back-catalog videos to import per run (slow auto-drip). See Channel.backfill.
    backfill_budget_per_run: int = 10
    # Add a critical "reality check" counterweight to each brief (and library answers).
    reality_check: bool = True
    # Cost / safety guards (not exposed in the yaml, but easy to change here):
    max_transcript_chars: int = 200_000
    max_material_chars: int = 60_000
    max_download_bytes: int = 25 * 1024 * 1024


@dataclass
class Channel:
    name: str
    channel_id: str
    visual: str = "auto"  # Phase 2 hint: auto | always | never
    backfill: int = 0  # import up to this many most-recent past videos (transcripts only)
    materials: bool = False  # during backfill, also download linked slides/PDFs for this channel
    skip_playlist_titles: list[str] = field(default_factory=list)  # exclude videos in playlists whose title contains any of these
    backfill_scan: int = 0  # how many uploads to scan when filtering (0 = just `backfill`)


def load_config(path: Path | str | None = None) -> tuple[Settings, list[Channel]]:
    """Parse watchlist.yml into (Settings, [Channel, ...])."""
    path = Path(path) if path else CONFIG_PATH
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    s = raw.get("settings") or {}
    settings = Settings(
        model=s.get("model", Settings.model),
        max_age_days=int(s.get("max_age_days", Settings.max_age_days)),
        transcript_languages=list(s.get("transcript_languages") or ["en"]),
        request_delay_seconds=float(s.get("request_delay_seconds", Settings.request_delay_seconds)),
        max_videos_per_run=int(s.get("max_videos_per_run", Settings.max_videos_per_run)),
        backfill_budget_per_run=int(s.get("backfill_budget_per_run", Settings.backfill_budget_per_run)),
        reality_check=bool(s.get("reality_check", Settings.reality_check)),
    )

    channels: list[Channel] = []
    for entry in raw.get("channels") or []:
        cid = (entry.get("channel_id") or "").strip()
        if not cid:
            continue
        channels.append(
            Channel(
                name=(entry.get("name") or cid).strip(),
                channel_id=cid,
                visual=(entry.get("visual") or "auto").strip(),
                backfill=int(entry.get("backfill") or 0),
                materials=bool(entry.get("materials") or False),
                skip_playlist_titles=list(entry.get("skip_playlist_titles") or []),
                backfill_scan=int(entry.get("backfill_scan") or 0),
            )
        )
    return settings, channels
