"""Back-catalog config + record shaping (no network)."""

from ytdigest.config import load_config
from ytdigest.library import record_from_brief
from ytdigest.models import Brief, Video


def test_config_parses_backfill(tmp_path):
    p = tmp_path / "wl.yml"
    p.write_text(
        "settings:\n"
        "  backfill_budget_per_run: 15\n"
        "channels:\n"
        "  - name: A\n    channel_id: UCaaaaaaaaaaaaaaaaaaaaaa\n    backfill: 100\n"
        "  - name: B\n    channel_id: UCbbbbbbbbbbbbbbbbbbbbbb\n",
        encoding="utf-8",
    )
    settings, channels = load_config(p)
    assert settings.backfill_budget_per_run == 15
    by = {c.name: c.backfill for c in channels}
    assert by["A"] == 100
    assert by["B"] == 0  # omitted = no backfill


def test_backfill_record_has_no_brief_fields():
    # A back-catalog import builds a Brief with empty summary fields (transcript only).
    video = Video(
        video_id="VID12345678",
        title="Old talk",
        channel_name="A",
        channel_id="UCx",
        url="https://www.youtube.com/watch?v=VID12345678",
    )
    brief = Brief(
        video=video,
        transcript_available=True,
        key_points=[],
        takeaway="",
        verdict="",
        verdict_reason="",
        archive_dir="data/archive/VID12345678",
    )
    rec = record_from_brief(brief)
    assert rec["verdict"] == ""
    assert rec["takeaway"] == ""
    assert rec["transcript_available"] is True
    assert rec["transcript_path"] == "data/archive/VID12345678/transcript.md"
