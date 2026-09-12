"""Phase 2 visuals — pure logic (no network, API key, or OpenCV needed).

ytdigest.visuals imports cv2/imagehash/PIL lazily inside functions, so these tests
exercise selection/rendering without those heavy deps installed.
"""

from pathlib import Path

from ytdigest.config import Channel
from ytdigest.library import render_index
from ytdigest.models import Video
from ytdigest.state import mark_visual_done, visual_done
from ytdigest.visuals import render_visuals_md, select_pending


# ── Channel opt-in parsing ────────────────────────────────────────────────────

def test_wants_visuals_parsing():
    assert Channel("n", "c", visual=True).wants_visuals is True
    assert Channel("n", "c", visual="always").wants_visuals is True
    assert Channel("n", "c", visual="yes").wants_visuals is True
    assert Channel("n", "c", visual=False).wants_visuals is False
    assert Channel("n", "c", visual="auto").wants_visuals is False
    assert Channel("n", "c", visual="never").wants_visuals is False
    assert Channel("n", "c").wants_visuals is False  # default


# ── select_pending ────────────────────────────────────────────────────────────

def _lib():
    return {"videos": {
        "vidNEW": {"channel_id": "CID_ON", "channel": "On", "title": "New",
                   "url": "u1", "published": "2026-09-05", "transcript_available": True},
        "vidOLD": {"channel_id": "CID_ON", "channel": "On", "title": "Old",
                   "url": "u2", "published": "2026-01-01", "transcript_available": True},
        "vidOFF": {"channel_id": "CID_OFF", "channel": "Off", "title": "Off-channel",
                   "url": "u3", "published": "2026-09-06", "transcript_available": True},
    }}


def _channels():
    return [Channel("On", "CID_ON", visual=True), Channel("Off", "CID_OFF", visual=False)]


def test_select_pending_only_optin_newest_first():
    state = {"visuals": {}}
    pending = select_pending(_channels(), state, _lib(), budget=10)
    ids = [v.video_id for v in pending]
    assert ids == ["vidNEW", "vidOLD"]  # opted-in only, newest first; off-channel excluded


def test_select_pending_respects_budget_and_ledger():
    state = {"visuals": {}}
    assert [v.video_id for v in select_pending(_channels(), state, _lib(), budget=1)] == ["vidNEW"]

    mark_visual_done(state, "vidNEW", slides=3)
    assert visual_done(state, "vidNEW")
    assert [v.video_id for v in select_pending(_channels(), state, _lib(), budget=10)] == ["vidOLD"]


def test_select_pending_matches_legacy_record_by_name():
    """Older library records predate channel_id — fall back to matching the display name."""
    lib = {"videos": {"legacy": {"channel": "On", "title": "L", "url": "u",
                                 "published": "2026-09-01", "transcript_available": True}}}
    pending = select_pending(_channels(), {"visuals": {}}, lib, budget=10)
    assert [v.video_id for v in pending] == ["legacy"]


def test_select_pending_none_when_no_optin():
    chans = [Channel("Off", "CID_OFF", visual=False)]
    assert select_pending(chans, {"visuals": {}}, _lib(), budget=10) == []


# ── render_visuals_md ─────────────────────────────────────────────────────────

def _video():
    return Video("vid1", "Chart Video", "On", "CID_ON", "https://youtu.be/vid1")


def test_render_visuals_md_formats_timestamps_and_text():
    kept = [
        {"timestamp": 5, "description": "Bar chart of AI capex", "key_text": "2026: $765bn"},
        {"timestamp": 125, "description": "Summary slide", "key_text": ""},
    ]
    md = render_visuals_md(_video(), kept)
    assert "# On-screen visuals — Chart Video" in md
    assert "## 1. [00:05] Bar chart of AI capex" in md
    assert "2026: $765bn" in md
    assert "## 2. [02:05] Summary slide" in md


def test_render_visuals_md_empty():
    md = render_visuals_md(_video(), [])
    assert "No informative on-screen visuals" in md


# ── INDEX visuals link (flag + on-disk detection) ─────────────────────────────

def test_render_index_shows_visuals_link_from_flag():
    lib = {"videos": {"v": {"channel": "On", "title": "T", "url": "u",
                            "published": "2026-09-05", "has_visuals": True}}}
    md = render_index(lib)
    assert "[visuals](v/visuals.md)" in md


def test_render_index_detects_visuals_on_disk(tmp_path: Path):
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "visuals.md").write_text("# visuals\n\n## 1. [00:01] x", encoding="utf-8")
    lib = {"videos": {"v": {"channel": "On", "title": "T", "url": "u", "published": "2026-09-05"}}}
    md = render_index(lib, archive_dir=tmp_path)
    assert "[visuals](v/visuals.md)" in md
    # and no link when nothing on disk / no flag
    assert "[visuals]" not in render_index(lib)
