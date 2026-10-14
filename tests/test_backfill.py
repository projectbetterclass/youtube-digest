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


def test_run_backfill_cache_enumerates_each_channel_once(monkeypatch):
    # A caller running several batches passes one cache so a big channel's listing (many
    # pages through the metered proxy) happens once, not once per batch.
    from ytdigest import backfill
    from ytdigest.config import Channel, Settings

    calls = []

    def fake_candidates(channel):
        calls.append(channel.channel_id)
        return [(f"v{i}", f"t{i}") for i in range(4)]

    def fake_import(video, settings, session=None, fetch_materials=False):
        return Brief(video=video, transcript_available=True, key_points=[], takeaway="",
                     verdict="", verdict_reason="")

    monkeypatch.setattr(backfill, "_candidates_for", fake_candidates)
    monkeypatch.setattr(backfill, "import_video", fake_import)
    settings = Settings(backfill_budget_per_run=2, transcript_delay_seconds=0)
    chans = [Channel(name="A", channel_id="UCa", backfill=100)]
    state, library, cache = {}, {}, {}
    assert backfill.run_backfill(settings, chans, state, library, cache=cache) == 2
    assert backfill.run_backfill(settings, chans, state, library, cache=cache) == 2
    assert calls == ["UCa"]
    assert backfill.run_backfill(settings, chans, state, library) == 0  # no cache: lists again
    assert calls == ["UCa", "UCa"]


# ── Shorts (per-channel `shorts: N`, collected only when a run asks for them) ─────────

def test_config_parses_shorts(tmp_path):
    p = tmp_path / "wl.yml"
    p.write_text(
        "channels:\n"
        "  - name: A\n    channel_id: UCaaaaaaaaaaaaaaaaaaaaaa\n    backfill: 10\n    shorts: 300\n"
        "  - name: B\n    channel_id: UCbbbbbbbbbbbbbbbbbbbbbb\n    backfill: 5\n",
        encoding="utf-8",
    )
    _, channels = load_config(p)
    assert {c.name: c.shorts for c in channels} == {"A": 300, "B": 0}  # off unless set


def _fake_import_capturing(seen):
    def fake_import(video, settings, session=None, fetch_materials=False):
        seen.append(video)
        return Brief(video=video, transcript_available=True, key_points=[], takeaway="",
                     verdict="", verdict_reason="")
    return fake_import


def _fake_enumerate(tabs):
    def fake_enumerate(channel_id, limit, tab="videos"):
        tabs.append((tab, limit))
        return [(f"{tab[0]}{i}", f"{tab} {i}") for i in range(2)]
    return fake_enumerate


def test_shorts_are_off_unless_the_run_asks(monkeypatch):
    from ytdigest import backfill
    from ytdigest.config import Channel, Settings

    tabs, seen = [], []
    monkeypatch.setattr(backfill, "enumerate_channel", _fake_enumerate(tabs))
    monkeypatch.setattr(backfill, "import_video", _fake_import_capturing(seen))
    settings = Settings(backfill_budget_per_run=10, transcript_delay_seconds=0)
    chans = [Channel(name="A", channel_id="UCa", backfill=5, shorts=7),
             Channel(name="OnlyShorts", channel_id="UCo", backfill=0, shorts=7)]
    assert backfill.run_backfill(settings, chans, {}, {}) == 2  # routine run: videos only
    assert tabs == [("videos", 5)]                               # Shorts tab never listed


def test_shorts_come_after_videos_with_shorts_links(monkeypatch):
    from ytdigest import backfill
    from ytdigest.config import Channel, Settings

    tabs, seen = [], []
    monkeypatch.setattr(backfill, "enumerate_channel", _fake_enumerate(tabs))
    monkeypatch.setattr(backfill, "import_video", _fake_import_capturing(seen))
    settings = Settings(backfill_budget_per_run=10, transcript_delay_seconds=0)
    chans = [Channel(name="A", channel_id="UCa", backfill=5, shorts=7)]
    state, library, cache = {}, {}, {}
    assert backfill.run_backfill(settings, chans, state, library, cache=cache, include_shorts=True) == 4
    assert tabs == [("videos", 5), ("shorts", 7)]
    assert [(v.video_id, v.short) for v in seen] == [("v0", False), ("v1", False), ("s0", True), ("s1", True)]
    assert seen[2].url == "https://www.youtube.com/shorts/s0"
    assert library["videos"]["s0"]["short"] is True and "short" not in library["videos"]["v0"]
    backfill.run_backfill(settings, chans, state, library, cache=cache, include_shorts=True)
    assert tabs == [("videos", 5), ("shorts", 7)]  # cached: neither tab listed again


def test_one_failed_listing_does_not_lose_the_other(monkeypatch):
    from ytdigest import backfill
    from ytdigest.config import Channel, Settings

    def fake_enumerate(channel_id, limit, tab="videos"):
        if (channel_id, tab) in {("UCnoshorts", "shorts"), ("UCnovideos", "videos")}:
            raise RuntimeError(f"ERROR: [youtube:tab] {tab} listing failed")
        return [(f"{channel_id}-{tab}", "t")]

    seen = []
    monkeypatch.setattr(backfill, "enumerate_channel", fake_enumerate)
    monkeypatch.setattr(backfill, "import_video", _fake_import_capturing(seen))
    settings = Settings(backfill_budget_per_run=10, transcript_delay_seconds=0)
    chans = [Channel(name="NoShortsTab", channel_id="UCnoshorts", backfill=3, shorts=5),
             Channel(name="VideosFail", channel_id="UCnovideos", backfill=3, shorts=5)]
    assert backfill.run_backfill(settings, chans, {}, {}, include_shorts=True) == 2
    assert [v.video_id for v in seen] == ["UCnoshorts-videos", "UCnovideos-shorts"]


def test_music_flag_only_for_near_empty_captions_on_shorts(tmp_path, monkeypatch):
    from ytdigest import backfill
    from ytdigest import config as C
    from ytdigest.config import Settings

    monkeypatch.setattr(C, "ARCHIVE_DIR", tmp_path)
    texts = {
        "mus": "[Music] [Music] go [Music]",                         # music-only Short
        "one": "[Music]",                                             # a single marker, nothing else
        # spoken Short with a music bed: ~15 words per marker, like the library's real ones
        "tlk": ("[Music] keep your elbows tucked and drive through the floor on every rep "
                "[Music] then pause at the bottom and control the way down every single time"),
        "vid": "[Music] [Music] go [Music]",                          # same text, but not a Short
    }
    monkeypatch.setattr(backfill, "fetch_transcript", lambda vid, langs: (texts[vid], True, False, ""))
    s = Settings()

    def mk(vid, short):
        return Video(video_id=vid, title="T", channel_name="A", channel_id="UCa",
                     url=f"https://www.youtube.com/shorts/{vid}", short=short)

    flags = {vid: backfill.import_video(mk(vid, vid != "vid"), s).music_captions for vid in texts}
    assert flags == {"mus": True, "one": True, "tlk": False, "vid": False}
    assert "_A Short whose captions are mostly music" in (tmp_path / "mus" / "transcript.md").read_text(encoding="utf-8")
    assert "mostly music" not in (tmp_path / "tlk" / "transcript.md").read_text(encoding="utf-8")


def test_miss_reason_is_recorded_for_the_retry_pass(tmp_path, monkeypatch):
    from ytdigest import backfill
    from ytdigest import config as C
    from ytdigest.config import Channel, Settings

    monkeypatch.setattr(C, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(backfill, "_candidates_for", lambda ch: [("off", "t"), ("got", "t")])
    monkeypatch.setattr(backfill, "fetch_transcript", lambda vid, langs: (
        ("", False, False, "TranscriptsDisabled: subtitles are disabled") if vid == "off" else ("hi there", True, False, "")))
    state = {}
    settings = Settings(backfill_budget_per_run=10, transcript_delay_seconds=0)
    backfill.run_backfill(settings, [Channel(name="A", channel_id="UCa", backfill=5)], state, {})
    assert state["processed"]["off"]["transcript_miss"].startswith("TranscriptsDisabled")
    assert "transcript_miss" not in state["processed"]["got"]


def test_shorts_links_mark_shorts_even_from_rss_and_old_records():
    from ytdigest.library import render_index

    rss_short = Video(video_id="r1", title="T", channel_name="A", channel_id="UCa",
                      url="https://www.youtube.com/shorts/r1")  # as parse_feed builds it, before the flag
    rec = record_from_brief(Brief(video=rss_short, transcript_available=True, key_points=[], takeaway="",
                                  verdict="", verdict_reason=""))
    assert rec["short"] is True
    lib = {"videos": {
        "s1": {"channel": "A", "title": "Big lats", "url": "u", "short": True},
        "s2": {"channel": "A", "title": "Erectors", "url": "u", "short": True, "music_captions": True},
        "old": {"channel": "A", "title": "Old short", "url": "https://www.youtube.com/shorts/old"},
        "v1": {"channel": "A", "title": "Long talk", "url": "u"},
    }}
    rows = {l.split("[")[1].split("]")[0]: l for l in render_index(lib).splitlines()
            if l.startswith("| ") and "](" in l}
    assert rows["Big lats"].endswith("· Short |")
    assert "Short (music; content on screen)" in rows["Erectors"]
    assert rows["Old short"].endswith("· Short |")   # a record from before the flag, by its link
    assert "Short" not in rows["Long talk"]


# ── Playlists (one the user names; any channel, in playlist order) ─────────────────────

def test_playlist_listing_keeps_order_and_each_videos_channel(monkeypatch):
    import sys
    import types

    from ytdigest import backfill

    info = {"title": "Buddhism made simple", "channel": "Owner", "channel_id": "UCown", "entries": [
        {"id": "v1", "title": "The Four Noble Truths", "duration": 612.0},
        {"id": "v2", "title": "[Private video]"},
        {"id": "v3", "title": "Guest talk", "channel": "Guest", "channel_id": "UCgst", "duration": None},
        {"id": "v4", "title": "[Deleted video]"},
        {"title": "no id"},
    ]}

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            assert url.endswith("list=PLabc") and not download and self.opts["extract_flat"]
            return info

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYDL))
    got = backfill.playlist_listing("PLabc")
    assert (got["id"], got["title"], got["channel"]) == ("PLabc", "Buddhism made simple", "Owner")
    assert [v["id"] for v in got["videos"]] == ["v1", "v3"]  # gone slots dropped, order kept
    assert got["videos"][0] == {"id": "v1", "title": "The Four Noble Truths", "channel": "Owner",
                                "channel_id": "UCown", "duration": 612}
    assert (got["videos"][1]["channel"], got["videos"][1]["duration"]) == ("Guest", None)


def _playlist(*ids):
    return {"id": "PLx", "title": "P", "channel": "Owner", "channel_id": "UCo",
            "videos": [{"id": v, "title": f"t{v}", "channel": "Owner", "channel_id": "UCo",
                        "duration": None} for v in ids]}


def test_run_playlist_imports_in_order_skipping_done_ones(monkeypatch):
    from ytdigest import backfill
    from ytdigest.config import Settings

    seen = []

    def fake_import(video, settings, session=None, fetch_materials=False, any_language=False):
        assert any_language  # a playlist takes captions in any language
        seen.append(video.video_id)
        return Brief(video=video, transcript_available=True, key_points=[], takeaway="",
                     verdict="", verdict_reason="")

    monkeypatch.setattr(backfill, "import_video", fake_import)
    state = {"processed": {"b": {"channel": "Owner"}}}
    library = {}
    settings = Settings(transcript_delay_seconds=0)
    assert backfill.run_playlist(settings, _playlist("a", "b", "c", "d"), state, library, 2) == 2
    assert seen == ["a", "c"]
    rec = library["videos"]["c"]
    assert (rec["channel"], rec["channel_id"], rec["url"]) == ("Owner", "UCo", "https://www.youtube.com/watch?v=c")
    assert state["processed"]["c"]["channel"] == "Owner"


def test_run_playlist_stops_at_an_ip_block(monkeypatch):
    from ytdigest import backfill
    from ytdigest.config import Settings
    from ytdigest.transcript import TranscriptBlocked

    def fake_import(video, settings, session=None, fetch_materials=False, any_language=False):
        if video.video_id == "b":
            raise TranscriptBlocked(video.video_id)
        return Brief(video=video, transcript_available=True, key_points=[], takeaway="",
                     verdict="", verdict_reason="")

    monkeypatch.setattr(backfill, "import_video", fake_import)
    state = {}
    n = backfill.run_playlist(Settings(transcript_delay_seconds=0), _playlist("a", "b", "c"), state, {}, 10)
    assert n == 1 and list(state["processed"]) == ["a"]  # b and c wait for a re-run


def test_import_video_any_language_keeps_own_captions_under_a_note(tmp_path, monkeypatch):
    from ytdigest import backfill
    from ytdigest import config as C
    from ytdigest.config import Settings

    monkeypatch.setattr(C, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(backfill, "fetch_transcript_any_language", lambda vid, langs: (
        ("de vier edele waarheden", True, False, "", "Dutch (auto-generated)") if vid == "nl"
        else ("the four noble truths", True, False, "", "")))
    v = lambda vid: Video(video_id=vid, title="T", channel_name="A", channel_id="UCa", url="u")
    for vid in ("nl", "en"):
        backfill.import_video(v(vid), Settings(transcript_languages=["en"]), any_language=True)
    nl = (tmp_path / "nl" / "transcript.md").read_text(encoding="utf-8")
    assert "_The captions are in Dutch (auto-generated): this video has none in en._" in nl
    assert nl.rstrip().endswith("de vier edele waarheden")
    assert "captions are in" not in (tmp_path / "en" / "transcript.md").read_text(encoding="utf-8")
