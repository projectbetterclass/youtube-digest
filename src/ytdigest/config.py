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
# Phase 2 keeps its own ledger so the self-hosted visuals job never writes state.json
# (which the cloud digest rewrites every run) — the two jobs stay conflict-free.
VISUALS_STATE_PATH = DATA_DIR / "visuals_state.json"
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
    # Phase 2 (on-screen visuals) — runs as a separate self-hosted job (see visuals.py):
    visual_budget_per_run: int = 6      # videos to enrich with visuals per run
    visual_frame_cap: int = 24          # max candidate frames sent to Claude vision per video
    visual_max_height: int = 480        # download at/below this resolution (keeps files small)
    # Cost / safety guards (not exposed in the yaml, but easy to change here):
    max_transcript_chars: int = 200_000
    max_material_chars: int = 60_000
    max_download_bytes: int = 25 * 1024 * 1024
    max_video_bytes: int = 300 * 1024 * 1024  # skip pathologically large downloads


@dataclass
class Channel:
    name: str
    channel_id: str
    # Phase 2 opt-in. YAML `visual: true` (or "always"/"yes") captures on-screen
    # slides/charts for this channel; false / "auto" / "never" leaves it off.
    visual: object = "auto"
    backfill: int = 0  # import up to this many most-recent past videos (transcripts only)
    materials: bool = False  # during backfill, also download linked slides/PDFs for this channel
    skip_playlist_titles: list[str] = field(default_factory=list)  # exclude videos in playlists whose title contains any of these
    backfill_scan: int = 0  # how many uploads to scan when filtering (0 = just `backfill`)

    @property
    def wants_visuals(self) -> bool:
        """True when this channel is opted in to on-screen visual capture (Phase 2)."""
        v = self.visual
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"true", "always", "yes", "on", "1"}


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
        visual_budget_per_run=int(s.get("visual_budget_per_run", Settings.visual_budget_per_run)),
        visual_frame_cap=int(s.get("visual_frame_cap", Settings.visual_frame_cap)),
        visual_max_height=int(s.get("visual_max_height", Settings.visual_max_height)),
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
                visual=entry.get("visual", "auto"),  # may be bool (YAML true) or str; parsed by .wants_visuals
                backfill=int(entry.get("backfill") or 0),
                materials=bool(entry.get("materials") or False),
                skip_playlist_titles=list(entry.get("skip_playlist_titles") or []),
                backfill_scan=int(entry.get("backfill_scan") or 0),
            )
        )
    return settings, channels
