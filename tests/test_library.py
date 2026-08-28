"""Library index rendering (no network/API)."""

from datetime import datetime, timezone

from ytdigest.library import add_brief, render_index
from ytdigest.models import Brief, Video


def _brief():
    video = Video(
        video_id="RECENT12345",
        title="Pricing Your | Offer",  # pipe must be escaped in the table
        channel_name="Alex Hormozi",
        channel_id="UCUyDOdBWhC1MCxEjC46d-zw",
        url="https://www.youtube.com/watch?v=RECENT12345",
        published=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )
    return Brief(
        video=video,
        transcript_available=True,
        key_points=["a"],
        takeaway="Charge for value,\nnot time.",  # newline must collapse to one cell
        verdict="watch",
        verdict_reason="dense",
    )


def test_render_index_row_and_escaping():
    lib = {"videos": {}}
    add_brief(lib, _brief())
    md = render_index(lib)
    assert "# 📚 Library index" in md
    assert "1 video archived" in md
    assert "[Pricing Your \\| Offer](https://www.youtube.com/watch?v=RECENT12345)" in md
    assert "| Alex Hormozi |" in md
    assert "| watch |" in md
    assert "Charge for value, not time." in md
    assert "[transcript](RECENT12345/transcript.md)" in md


def test_render_index_empty():
    md = render_index({"videos": {}})
    assert "0 videos archived" in md
