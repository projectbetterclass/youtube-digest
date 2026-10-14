"""scripts/local_collect.py — channel selection only (no network, git, or API key)."""

import importlib.util
from pathlib import Path

import pytest

from ytdigest.config import Channel, load_config

_SPEC = importlib.util.spec_from_file_location(
    "local_collect", Path(__file__).resolve().parent.parent / "scripts" / "local_collect.py"
)
local_collect = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(local_collect)


def _ch(name):
    return Channel(name=name, channel_id="UC" + name.replace(" ", ""))


def test_select_is_case_insensitive_and_keeps_only_named():
    chans = [_ch("Ben Yanes"), _ch("JulienHimself"), _ch("Tom Nash")]
    picked = local_collect.select_channels(chans, ["ben yanes", "JULIENHIMSELF"])
    assert [c.name for c in picked] == ["Ben Yanes", "JulienHimself"]


def test_unknown_channel_is_an_error():
    with pytest.raises(SystemExit, match="Nobody"):
        local_collect.select_channels([_ch("Ben Yanes")], ["Ben Yanes", "Nobody"])


def test_priority_channels_are_all_in_the_watchlist():
    _, channels = load_config()
    picked = local_collect.select_channels(channels, local_collect.PRIORITY)
    assert len(picked) == len(local_collect.PRIORITY)


def test_failed_this_run_picks_only_this_runs_misses_for_these_channels():
    state = {"processed": {
        "a": {"channel": "Ben Yanes", "transcript_available": False, "processed_at": "2026-09-29T10:00:00+00:00"},
        "b": {"channel": "Ben Yanes", "transcript_available": True, "processed_at": "2026-09-29T10:00:00+00:00"},
        "c": {"channel": "Ben Yanes", "transcript_available": False, "processed_at": "2026-09-01T10:00:00+00:00"},
        "d": {"channel": "Tom Nash", "transcript_available": False, "processed_at": "2026-09-29T10:00:00+00:00"},
    }}
    got = local_collect.failed_this_run(state, {"Ben Yanes"}, "2026-09-29T09:00:00+00:00")
    assert got == ["a"]


def test_retry_pass_skips_videos_that_simply_have_no_captions():
    state = {"processed": {
        "blk": {"channel": "A", "transcript_available": False, "processed_at": "2026-10-24T10:00:00+00:00",
                "transcript_miss": "RequestBlocked: YouTube is blocking requests from your IP"},
        "off": {"channel": "A", "transcript_available": False, "processed_at": "2026-10-24T10:00:00+00:00",
                "transcript_miss": "TranscriptsDisabled: subtitles are disabled for this video"},
        "old": {"channel": "A", "transcript_available": False, "processed_at": "2026-10-24T10:00:00+00:00"},
    }}
    got = local_collect.failed_this_run(state, {"A"}, "2026-10-24T09:00:00+00:00")
    assert sorted(got) == ["blk", "old"]  # a block (or an unknown reason) is retried; captions-off isn't


def test_playlist_id_from_a_link_or_a_bare_id():
    pid = "PLqnSdW-e2Bah9Lh0MBn7JjW5kswNUDcZd"
    assert local_collect.playlist_id(pid) == pid
    assert local_collect.playlist_id(f"https://www.youtube.com/playlist?list={pid}") == pid
    assert local_collect.playlist_id(f"https://youtube.com/watch?v=abc&list={pid}&index=3") == pid
    with pytest.raises(SystemExit):
        local_collect.playlist_id("https://www.youtube.com/watch?v=abc")


def _sandbox(tmp_path, monkeypatch):
    """Point the collector at an empty data/ and record pushes instead of running git."""
    from ytdigest import backfill
    from ytdigest.config import Settings

    C = local_collect.C
    monkeypatch.setattr(C, "DATA_DIR", tmp_path)
    monkeypatch.setattr(C, "ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr(C, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(C, "LIBRARY_PATH", tmp_path / "library.json")
    monkeypatch.setattr(C, "INDEX_PATH", tmp_path / "archive" / "INDEX.md")
    monkeypatch.setattr(C, "load_config", lambda: (Settings(transcript_delay_seconds=0), []))
    (tmp_path / "archive").mkdir()
    lock = tmp_path / "lock"
    lock.touch()
    monkeypatch.setattr(local_collect, "LOCK", lock)
    pushes = []
    monkeypatch.setattr(local_collect, "push", lambda label, n: pushes.append((label, n)))
    return backfill, pushes


def test_collect_playlist_pulls_in_order_retries_misses_and_keeps_the_order(tmp_path, monkeypatch):
    import json

    from ytdigest.state import load_state, save_state

    backfill, pushes = _sandbox(tmp_path, monkeypatch)
    listing = {"id": "PLx", "title": "Buddhism made simple", "channel": "Owner", "channel_id": "UCo",
               "videos": [{"id": v, "title": f"t{v}", "channel": ch, "channel_id": "UC" + ch, "duration": 300}
                          for v, ch in (("a", "Owner"), ("b", "Owner"), ("c", "Guest"), ("off", "Owner"))]}
    monkeypatch.setattr(local_collect, "playlist_listing", lambda pid: listing)
    # From earlier runs: c missed because the proxy ran out, a ran under the English-only
    # collector (none in English), and "off" has no captions at all.
    save_state(local_collect.C.STATE_PATH, {"processed": {
        "c": {"channel": "Guest", "transcript_available": False, "processed_at": "2026-10-01T00:00:00+00:00",
              "transcript_miss": "ProxyError: out of data"},
        "off": {"channel": "Owner", "transcript_available": False, "processed_at": "2026-10-01T00:00:00+00:00",
                "transcript_miss": "TranscriptsDisabled: subtitles are disabled"},
        "a": {"channel": "Owner", "transcript_available": False, "processed_at": "2026-10-14T00:00:00+00:00",
              "transcript_miss": "NoTranscriptFound: No transcripts were found for any of the requested langua"},
    }})
    calls = []

    def fake_fetch(vid, langs):
        calls.append(vid)
        if vid == "b" and calls.count("b") == 1:  # a 429 on one exit IP: works on the retry
            return "", False, False, "RequestBlocked: too many requests", ""
        return f"words of {vid}", True, False, "", ("Thai (auto-generated)" if vid == "a" else "")

    monkeypatch.setattr(backfill, "fetch_transcript", lambda *a: (_ for _ in ()).throw(AssertionError("English-only fetch")))
    monkeypatch.setattr(backfill, "fetch_transcript_any_language", fake_fetch)
    assert local_collect.collect_playlist("PLx", 2000) == 3
    assert calls == ["a", "b", "c", "b"]  # in order, then the one retry; "off" is never re-fetched
    assert "_The captions are in Thai (auto-generated)" in (tmp_path / "archive" / "a" / "transcript.md").read_text(encoding="utf-8")
    state = load_state(local_collect.C.STATE_PATH)
    assert all(state["processed"][v]["transcript_available"] for v in "abc")
    assert pushes == [("playlist: Buddhism made simple", 3)]
    saved = json.loads((tmp_path / "playlists" / "PLx.json").read_text(encoding="utf-8"))
    assert [v["id"] for v in saved["videos"]] == ["a", "b", "c", "off"]
    assert "words of c" in (tmp_path / "archive" / "c" / "transcript.md").read_text(encoding="utf-8")

    # Run again: nothing new, nothing missing, the listing unchanged, so nothing to push.
    calls.clear()
    assert local_collect.collect_playlist("PLx", 2000) == 0
    assert calls == [] and len(pushes) == 1


def test_collect_still_retries_this_runs_misses_after_the_refactor(tmp_path, monkeypatch):
    from ytdigest.config import Channel, Settings

    backfill, pushes = _sandbox(tmp_path, monkeypatch)
    chans = [Channel(name="A", channel_id="UCa", backfill=5)]
    monkeypatch.setattr(local_collect.C, "load_config", lambda: (Settings(transcript_delay_seconds=0), chans))
    monkeypatch.setattr(backfill, "_candidates_for", lambda ch: [("x", "tx"), ("y", "ty")])
    calls = []

    def fake_fetch(vid, langs):
        calls.append(vid)
        if vid == "y" and calls.count("y") == 1:
            return "", False, False, "RequestBlocked: too many requests"
        return "hi", True, False, ""

    monkeypatch.setattr(backfill, "fetch_transcript", fake_fetch)
    assert local_collect.collect(["A"], 2000) == 2
    assert calls == ["x", "y", "y"]
    assert pushes == [("A", 2)]


def test_none_in_english_is_final_for_a_channel_but_retried_for_a_playlist():
    rec = {"channel": "A", "transcript_available": False, "processed_at": "2026-10-14T10:00:00+00:00",
           "transcript_miss": "NoTranscriptFound: No transcripts were found for any of the requested langua"}
    state = {"processed": {"v": rec}}
    assert local_collect.failed_this_run(state, {"A"}, "") == []
    assert local_collect.failed_this_run(state, {"A"}, "", {"v"}, local_collect.PLAYLIST_PERMANENT) == ["v"]
