"""Feed parsing + new-video selection (no network)."""

from datetime import datetime, timezone
from pathlib import Path

from ytdigest.config import Channel
from ytdigest.feeds import parse_feed
from ytdigest.state import select_new_videos

FIXTURE = Path(__file__).parent / "fixtures" / "sample_feed.xml"
CHANNEL = Channel(name="Test Channel", channel_id="UCtest0000000000000000")


def _videos():
    return parse_feed(FIXTURE.read_bytes(), CHANNEL)


def test_parse_feed_extracts_fields():
    videos = _videos()
    assert len(videos) == 2

    recent = videos[0]
    assert recent.video_id == "RECENT12345"
    assert recent.title == "Neural Rendering, Explained"
    assert recent.channel_name == "Test Channel"
    assert recent.url == "https://www.youtube.com/watch?v=RECENT12345"
    assert recent.published == datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc)
    # media:description survives parsing (drives link classification downstream)
    assert "talk-deck.pdf" in recent.description
    assert "github.com/example/neural-render" in recent.description


def test_select_new_videos_filters_old_and_processed():
    videos = _videos()
    now = datetime(2026, 8, 27, 6, 0, tzinfo=timezone.utc)

    # Empty state, 3-day window → only the recent upload qualifies.
    new = select_new_videos(videos, {"processed": {}}, max_age_days=3, now=now)
    assert [v.video_id for v in new] == ["RECENT12345"]

    # Already processed → excluded even though it's recent.
    state = {"processed": {"RECENT12345": {}}}
    assert select_new_videos(videos, state, max_age_days=3, now=now) == []
