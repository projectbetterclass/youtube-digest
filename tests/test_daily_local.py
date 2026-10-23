"""scripts/daily_local.py: the daily local job (no network: feeds, transcripts and vision are faked)."""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ytdigest.config import Channel, Settings
from ytdigest.models import Brief, Video
from ytdigest.transcript import TranscriptBlocked

_spec = importlib.util.spec_from_file_location(
    "daily_local", Path(__file__).resolve().parent.parent / "scripts" / "daily_local.py")
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
S = Settings(request_delay_seconds=0, transcript_delay_seconds=0)


def _v(vid, ch, days_ago=1, short=False):
    return Video(video_id=vid, title=vid, channel_name=ch.name, channel_id=ch.channel_id,
                 url=f"https://www.youtube.com/{'shorts/' if short else 'watch?v='}{vid}",
                 published=NOW - timedelta(days=days_ago), short=short)


def _brief(video, ok=True):
    return Brief(video=video, transcript_available=ok, key_points=[], takeaway="", verdict="",
                 verdict_reason="", transcript_miss="" if ok else "TranscriptsDisabled: off")


def test_discover_takes_new_uploads_and_shorts_only_where_switched_on():
    talk = Channel(name="Talk", channel_id="UCt", backfill=100)
    train = Channel(name="Train", channel_id="UCr", backfill=100, shorts=50)
    feeds = {
        "UCt": [_v("t-new", talk), _v("t-short", talk, short=True), _v("t-old", talk, days_ago=40),
                _v("t-done", talk)],
        "UCr": [_v("r-short", train, days_ago=2, short=True)],
    }
    state = {"processed": {"t-done": {}}}
    new, failed = D.discover(S, [talk, train], state, NOW, fetch=lambda ch: feeds[ch.channel_id], sleep=lambda s: None)
    assert failed == 0
    assert [v.video_id for _, v in new] == ["r-short", "t-new"]  # oldest first; Shorts only on Train


def test_new_uploads_only_channels_keep_the_short_window():
    whole = Channel(name="Whole", channel_id="UCw", backfill=100)
    new_only = Channel(name="NewOnly", channel_id="UCn")   # no backfill: the user chose not to catch up
    feeds = {"UCw": [_v("w-20d", whole, days_ago=20)],
             "UCn": [_v("n-20d", new_only, days_ago=20), _v("n-2d", new_only, days_ago=2)]}
    s = Settings(request_delay_seconds=0, transcript_delay_seconds=0, max_age_days=5)
    new, _ = D.discover(s, [whole, new_only], {}, NOW, fetch=lambda ch: feeds[ch.channel_id], sleep=lambda s: None)
    assert [v.video_id for _, v in new] == ["w-20d", "n-2d"]


def test_one_failing_feed_does_not_stop_the_rest():
    a, b = Channel(name="A", channel_id="UCa"), Channel(name="B", channel_id="UCb")

    def fetch(ch):
        if ch.channel_id == "UCa":
            raise RuntimeError("feed down")
        return [_v("b1", b)]

    new, failed = D.discover(S, [a, b], {}, NOW, fetch=fetch, sleep=lambda s: None)
    assert [v.video_id for _, v in new] == ["b1"] and failed == 1


def test_collect_stops_at_a_proxy_run_out_and_marks_nothing_after_it(monkeypatch):
    ch = Channel(name="A", channel_id="UCa", backfill=10)
    new = [(ch, _v(f"v{i}", ch)) for i in range(5)]
    monkeypatch.setattr(D, "_save", lambda state, library: None)

    def importer(video, settings, fetch_materials=False):
        if video.video_id == "v2":
            raise TranscriptBlocked(video.video_id)  # what a ProxyError run-out now raises
        return _brief(video, ok=video.video_id != "v1")

    state, library = {}, {}
    done = D.collect(S, new, state, library, importer=importer, sleep=lambda s: None)
    assert [v.video_id for _, v in done] == ["v0", "v1"]
    assert sorted(state["processed"]) == ["v0", "v1"]                      # v2..v4 left for next time
    assert state["processed"]["v1"]["transcript_miss"].startswith("TranscriptsDisabled")


def test_collect_respects_the_per_run_cap(monkeypatch):
    ch = Channel(name="A", channel_id="UCa", backfill=10)
    monkeypatch.setattr(D, "MAX_NEW", 3)
    monkeypatch.setattr(D, "_save", lambda state, library: None)
    new = [(ch, _v(f"v{i}", ch)) for i in range(5)]
    done = D.collect(S, new, {}, {}, importer=lambda v, s, fetch_materials=False: _brief(v), sleep=lambda s: None)
    assert len(done) == 3


def _rec(ch, days_ago):
    published = (NOW - timedelta(days=days_ago)).isoformat() if days_ago is not None else None
    return {"channel": ch.name, "channel_id": ch.channel_id, "title": "t", "published": published}


def test_capture_candidates_are_recent_uploads_on_visual_channels_newest_first(monkeypatch):
    chart = Channel(name="Chart", channel_id="UCc", visual=True)
    talk = Channel(name="Talk", channel_id="UCt", visual=False)
    library = {"videos": {
        "c-old-run": _rec(chart, 20),   # collected by an earlier run, never captured: picked up now
        "c-new": _rec(chart, 1),
        "c-done": _rec(chart, 2),       # already captured
        "c-stale": _rec(chart, 45),     # older than the window
        "c-backfill": _rec(chart, None),  # back catalog (no upload date): never picked
        "t-new": _rec(talk, 1),         # audio-only channel
    }}
    vstate = {"visuals": {"c-done": {"slides": 3}}}
    picked = D.capture_candidates([chart, talk], vstate, library, NOW)
    assert [v.video_id for v in picked] == ["c-new", "c-old-run"]

    monkeypatch.setattr(D, "VISUAL_BUDGET", 1)
    assert [v.video_id for v in D.capture_candidates([chart, talk], vstate, library, NOW)] == ["c-new"]


def test_uploads_collected_without_a_date_get_it_from_the_feed_and_are_captured():
    chart = Channel(name="Chart", channel_id="UCc", backfill=100, visual=True)
    library = {"videos": {"c-recent": _rec(chart, None),       # collected by local_collect, no date
                          "c-catalog": _rec(chart, None)}}     # old back catalog: not in the feed
    feed = [_v("c-recent", chart, days_ago=4), _v("c-new", chart, days_ago=1)]
    dates = {}
    new, _ = D.discover(S, [chart], {"processed": {"c-recent": {}}}, NOW,
                        fetch=lambda ch: feed, sleep=lambda s: None, dates=dates)
    assert [v.video_id for _, v in new] == ["c-new"]               # already collected: not again
    assert D.fill_missing_dates(library, dates) == 1
    assert library["videos"]["c-recent"]["published"].startswith((NOW - timedelta(days=4)).date().isoformat())
    assert library["videos"]["c-catalog"]["published"] is None
    assert [v.video_id for v in D.capture_candidates([chart], {"visuals": {}}, library, NOW)] == ["c-recent"]


def test_capture_stops_on_throttle_and_marks_nothing_after_it():
    chart = Channel(name="Chart", channel_id="UCc", visual=True)
    todo = [_v(f"c{i}", chart) for i in range(4)]
    seen = []

    def process(video, settings, client):
        seen.append(video.video_id)
        if video.video_id == "c1":
            raise RuntimeError("download failed: 404")       # a dead video: marked, not retried
        if video.video_id == "c2":
            raise RuntimeError("ERROR: [youtube] c2: Sign in to confirm you’re not a bot")
        return 3

    vstate = {"visuals": {}}
    assert D.capture(S, todo, vstate, client=object(), process=process) == 1
    assert seen == ["c0", "c1", "c2"]                   # stopped at the bot check
    assert sorted(vstate["visuals"]) == ["c0", "c1"]    # c2 and c3 left for the next run
    assert vstate["visuals"]["c1"].get("error")


def test_union_keeps_theirs_and_adds_ours():
    theirs = {"processed": {"a": {"x": 1}, "b": {"x": 2}}, "version": 2}
    ours = {"processed": {"b": {"x": 99}, "c": {"x": 3}}, "version": 1, "extra": True}
    assert D._union(theirs, ours) == {"processed": {"a": {"x": 1}, "b": {"x": 2}, "c": {"x": 3}},
                                      "version": 2, "extra": True}


def _git_env(monkeypatch, tmp_path):
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[user]\n\tname = t\n\temail = t@example.com\n[init]\n\tdefaultBranch = main\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _run(cwd, *args):
    import subprocess
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _records(root, f):
    import json
    return json.loads((root / f).read_text(encoding="utf-8"))


def _write_records(root, state_ids, library_ids):
    from ytdigest.library import save_library
    from ytdigest.state import save_state
    save_state(root / "data/state.json", {"processed": {i: {"title": i} for i in state_ids}})
    save_library(root / "data/library.json", {"videos": {i: {"title": i, "channel": "C", "url": ""} for i in library_ids}})
    save_state(root / "data/visuals_state.json", {"visuals": {}})


@pytest.mark.skipif(__import__("shutil").which("git") is None, reason="needs git")
def test_push_conflict_merges_the_records_instead_of_stopping(monkeypatch, tmp_path):
    """Someone pushed library records while the daily run collected: both sets end up on origin."""
    _git_env(monkeypatch, tmp_path)
    origin, other, pc = tmp_path / "origin.git", tmp_path / "other", tmp_path / "pc"
    _run(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _run(tmp_path, "clone", "-q", str(origin), str(other))
    _write_records(other, ["base"], ["base"])
    (other / "README.md").write_text("x", encoding="utf-8")
    _run(other, "add", "-A")
    _run(other, "commit", "-qm", "seed")
    _run(other, "push", "-q", "origin", "main")
    _run(tmp_path, "clone", "-q", str(origin), str(pc))

    _write_records(other, ["base", "theirs"], ["base", "theirs"])      # pushed meanwhile
    _run(other, "commit", "-qam", "digest: theirs")
    _run(other, "push", "-q", "origin", "main")

    _write_records(pc, ["base", "ours"], ["base", "ours"])             # this run's work
    (pc / "data/archive/ours").mkdir(parents=True)
    (pc / "data/archive/ours/transcript.md").write_text("ours", encoding="utf-8")
    monkeypatch.setattr(D, "ROOT", pc)

    assert D.commit_and_push("daily: test") == ""
    _run(other, "pull", "-q")
    assert "merged with records pushed meanwhile" in _run(other, "log", "-1", "--format=%B")
    assert sorted(_records(other, "data/state.json")["processed"]) == ["base", "ours", "theirs"]
    assert sorted(_records(other, "data/library.json")["videos"]) == ["base", "ours", "theirs"]
    assert (other / "data/archive/ours/transcript.md").read_text(encoding="utf-8") == "ours"
    assert "ours" in (other / "data/archive/INDEX.md").read_text(encoding="utf-8")
    assert not (pc / ".git/rebase-merge").exists() and not (pc / ".git/rebase-apply").exists()
    assert _run(pc, "status", "--porcelain").strip() == ""            # nothing left half-done


@pytest.mark.skipif(__import__("shutil").which("git") is None, reason="needs git")
def test_merge_refuses_when_unpushed_commits_touch_more_than_data(monkeypatch, tmp_path):
    _git_env(monkeypatch, tmp_path)
    origin, other, pc = tmp_path / "origin.git", tmp_path / "other", tmp_path / "pc"
    _run(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _run(tmp_path, "clone", "-q", str(origin), str(other))
    _write_records(other, ["base"], ["base"])
    _run(other, "add", "-A")
    _run(other, "commit", "-qm", "seed")
    _run(other, "push", "-q", "origin", "main")
    _run(tmp_path, "clone", "-q", str(origin), str(pc))
    _write_records(other, ["base", "theirs"], ["base", "theirs"])
    _run(other, "commit", "-qam", "theirs")
    _run(other, "push", "-q", "origin", "main")

    (pc / "notes.md").write_text("someone's unpushed work", encoding="utf-8")
    _write_records(pc, ["base", "ours"], ["base", "ours"])
    _run(pc, "add", "-A")
    _run(pc, "commit", "-qm", "local work")
    monkeypatch.setattr(D, "ROOT", pc)

    problem = D.commit_and_push("daily: test")
    assert "outside data/" in problem and "notes.md" in problem
    assert _run(pc, "log", "-1", "--format=%s").strip() == "local work"   # left exactly as it was


def test_ran_recently(tmp_path):
    stamp = tmp_path / "last.txt"
    assert D.ran_recently(NOW, stamp) is False                       # never ran
    stamp.write_text((NOW - timedelta(hours=5)).isoformat(), encoding="utf-8")
    assert D.ran_recently(NOW, stamp) is True
    stamp.write_text((NOW - timedelta(hours=30)).isoformat(), encoding="utf-8")
    assert D.ran_recently(NOW, stamp) is False
