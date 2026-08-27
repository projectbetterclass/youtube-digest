"""Digest rendering (no network, no API)."""

from datetime import datetime, timezone

from ytdigest.digest import render_digest
from ytdigest.models import Brief, Link, Material, Video


def _brief(**overrides):
    video = Video(
        video_id="RECENT12345",
        title="Neural Rendering, Explained",
        channel_name="Test Channel",
        channel_id="UCtest",
        url="https://www.youtube.com/watch?v=RECENT12345",
        published=datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc),
    )
    defaults = dict(
        video=video,
        transcript_available=True,
        key_points=["Point one", "Point two"],
        takeaway="It's a solid overview.",
        verdict="watch",
        verdict_reason="Dense and well explained.",
        materials_notes="The slide deck adds the math.",
        listed_links=[Link(url="https://github.com/example/x", kind="list", category="github")],
        downloaded_materials=[Material(url="https://example.com/deck.pdf", category="pdf", text="hi")],
        archive_dir="data/archive/RECENT12345",
    )
    defaults.update(overrides)
    return Brief(**defaults)


def test_render_digest_contains_core_fields():
    md = render_digest("2026-08-27", [_brief()])
    assert "# 📺 YouTube Digest — 2026-08-27" in md
    assert "1 new video across your watchlist." in md
    assert "[Neural Rendering, Explained](https://www.youtube.com/watch?v=RECENT12345)" in md
    assert "✅ Watch in full" in md
    assert "- Point one" in md
    assert "It's a solid overview." in md
    # extracted material + mention-only link both surfaced
    assert "https://example.com/deck.pdf" in md
    assert "https://github.com/example/x" in md
    # archive link points up out of digests/
    assert "(../data/archive/RECENT12345/transcript.md)" in md


def test_render_flags_missing_transcript():
    md = render_digest("2026-08-27", [_brief(transcript_available=False)])
    assert "No transcript/captions were available" in md


def test_render_pluralizes_multiple():
    md = render_digest("2026-08-27", [_brief(), _brief()])
    assert "2 new videos across your watchlist." in md
