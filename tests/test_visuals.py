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


def test_render_index_detects_materials_on_disk(tmp_path: Path):
    (tmp_path / "v" / "materials").mkdir(parents=True)
    (tmp_path / "v" / "materials" / "01_pdf.txt").write_text("Source: u\n\nslide text", encoding="utf-8")
    lib = {"videos": {"v": {"channel": "On", "title": "T", "url": "u", "published": "2026-09-05"}}}
    md = render_index(lib, archive_dir=tmp_path)
    assert "[materials](v/materials/)" in md
    # flag alone also works, and nothing shows without disk or flag
    assert "[materials]" in render_index({"videos": {"v": {"had_materials": True}}})
    assert "[materials]" not in render_index(lib)


# ── Capture-only (frames saved now, read later) ──────────────────────────────

import pytest

from ytdigest import config as C
from ytdigest import visuals as V


def test_capture_only_skips_captured_and_records_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "FRAMES_DIR", tmp_path)
    V.save_frames("vidNEW", [])  # already captured (no frames kept) → skipped
    captured = []

    def fake_capture(video, settings):
        if video.video_id == "vidOLD":
            raise RuntimeError("HTTP Error 403")
        captured.append(video.video_id)
        V.save_frames(video.video_id, [])  # what the real capture_frames does
        return 0

    monkeypatch.setattr(V, "capture_frames", fake_capture)
    lib = _lib()
    lib["videos"]["vidMID"] = {"channel_id": "CID_ON", "channel": "On", "title": "Mid",
                               "url": "u4", "published": "2026-05-01"}
    done, failed = V.run_capture_only(None, _channels(), {"visuals": {}}, lib, budget=10)
    assert (done, failed) == (1, 1) and captured == ["vidMID"]
    frames, err = V.load_frames("vidOLD")
    assert frames == [] and "403" in err          # failure noted, so not retried next run
    assert V.run_capture_only(None, _channels(), {"visuals": {}}, lib, budget=10) == (0, 0)


def test_reader_uses_stored_frames_without_downloading(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "FRAMES_DIR", tmp_path / "frames")
    monkeypatch.setattr(C, "ARCHIVE_DIR", tmp_path / "archive")
    V.save_frames("vidNEW", [])
    monkeypatch.setattr(V, "_download_and_extract",
                        lambda *a, **k: pytest.fail("should not download when frames are stored"))
    video = Video(video_id="vidNEW", title="New", channel_name="On", channel_id="CID_ON", url="u1")
    assert V.process_video_visuals(video, None, client=None) == 0
    assert (tmp_path / "archive" / "vidNEW" / "visuals.md").exists()


def test_reader_reports_an_earlier_capture_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "FRAMES_DIR", tmp_path)
    V.save_frames("vidOLD", [], error="members-only video")
    video = Video(video_id="vidOLD", title="Old", channel_name="On", channel_id="CID_ON", url="u2")
    with pytest.raises(RuntimeError, match="members-only"):
        V.process_video_visuals(video, None, client=None)


def test_save_and_load_frames_round_trip(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    monkeypatch.setattr(C, "FRAMES_DIR", tmp_path)
    img = np.full((48, 64, 3), 200, np.uint8)
    V.save_frames("vidX", [(12.5, img, 7.0), (40.0, img, 3.0)])
    frames, err = V.load_frames("vidX")
    assert err == "" and [(ts, round(sc)) for ts, _, sc in frames] == [(12.5, 7), (40.0, 3)]
    assert frames[0][1].shape == (48, 64, 3)


def test_slide_items_tolerates_json_strings_and_junk():
    good = [{"index": 0, "description": "chart"}]
    assert V._slide_items({"slides": good}) == good
    assert V._slide_items({"slides": '[{"index": 0, "description": "chart"}]'}) == good
    assert V._slide_items('{"slides": [{"index": 0, "description": "chart"}]}') == good
    assert V._slide_items({"slides": ["oops", {"index": 0, "description": "chart"}]}) == good
    assert V._slide_items({"slides": "not json"}) == []
    assert V._slide_items({"slides": None}) == []


def test_stored_only_reads_captured_videos_and_credit_errors_dont_mark(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "FRAMES_DIR", tmp_path)
    V.save_frames("vidOLD", [])                      # captured; vidNEW is not
    seen = []

    def fake_process(video, settings, client):
        seen.append(video.video_id)
        raise RuntimeError("Your credit balance is too low to access the Anthropic API")

    monkeypatch.setattr(V, "process_video_visuals", fake_process)
    state = {"visuals": {}}
    assert V.run_visuals(None, _channels(), state, _lib(), client=object(), budget=10, stored_only=True) == 0
    assert seen == ["vidOLD"]                         # vidNEW skipped: no stored frames
    assert state["visuals"] == {}                     # credit stop leaves it to retry later


def test_download_retries_transient_errors_then_gives_up(monkeypatch):
    calls, slept = [], []
    outcomes = [RuntimeError("ERROR: unable to download video data: HTTP Error 403: Forbidden"),
                RuntimeError("Read timed out."), "path/to/video.mp4"]

    def fake_once(video_id, dest_dir, settings):
        calls.append(video_id)
        out = outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    import time as _time
    monkeypatch.setattr(V, "_download_video_once", fake_once)
    monkeypatch.setattr(_time, "sleep", slept.append)
    assert V._download_video("vid", "C:/nonexistent-dir", None) == "path/to/video.mp4"
    assert len(calls) == 3 and slept == list(V.DOWNLOAD_BACKOFF)

    outcomes[:] = [RuntimeError("HTTP Error 403")] * 3
    with pytest.raises(RuntimeError, match="403"):
        V._download_video("vid", "C:/nonexistent-dir", None)


def test_permanent_download_errors_are_not_retried(monkeypatch):
    calls = []

    def fake_once(video_id, dest_dir, settings):
        calls.append(1)
        raise RuntimeError("ERROR: [youtube] abc: Join this channel to get access to members-only content")

    monkeypatch.setattr(V, "_download_video_once", fake_once)
    with pytest.raises(RuntimeError):
        V._download_video("vid", "C:/nonexistent-dir", None)
    assert calls == [1]
    assert V._is_transient_download_error(RuntimeError("download produced no file (format unavailable or too large)")) is False


def test_capture_only_parallel_workers_handle_every_video(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "FRAMES_DIR", tmp_path)
    lib = {"videos": {f"v{i:02d}": {"channel_id": "CID_ON", "channel": "On", "title": f"T{i}",
                                     "url": f"u{i}", "published": f"2026-01-{i + 1:02d}"} for i in range(9)}}

    def fake_capture(video, settings):
        if video.video_id == "v03":
            raise RuntimeError("Video unavailable")
        V.save_frames(video.video_id, [])
        return 0

    monkeypatch.setattr(V, "capture_frames", fake_capture)
    done, failed = V.run_capture_only(None, _channels(), {"visuals": {}}, lib, budget=100, workers=4)
    assert (done, failed) == (8, 1)
    assert all(V.has_stored_frames(f"v{i:02d}") for i in range(9))  # the failure is noted too


BOT = "ERROR: [youtube] abc: Sign in to confirm you\u2019re not a bot. Use --cookies-from-browser"
# yt-dlp 2026.08.19's other "YouTube is throttling this PC" wordings
THROTTLES = [
    BOT,
    "ERROR: [youtube] abc: This content isn't available, try again later. The current session "
    "has been rate-limited by YouTube for up to an hour. It is recommended to use `-t sleep`",
    # the same reason with YouTube's curly apostrophe, which yt-dlp passes through un-rewritten
    "ERROR: [youtube] abc: This content isn’t available, try again later.",
    "ERROR: [youtube] abc: Video unavailable. YouTube is requiring a captcha challenge before playback",
    "ERROR: [youtube] abc: All player responses are invalid. Your IP is likely being blocked by Youtube",
    "ERROR: [youtube] abc: Failed to extract any player response; please report this issue on "
    "https://github.com/yt-dlp/yt-dlp/issues",
]


@pytest.mark.parametrize("msg", THROTTLES)
def test_throttle_wordings_are_recognised_and_not_retried(msg):
    assert V._is_bot_check(RuntimeError(msg))
    assert V._is_transient_download_error(RuntimeError(msg)) is False  # stop, don't hammer
    # dead videos stay dead, and the Claude API's own rate limit isn't YouTube throttling
    for other in ("ERROR: [youtube] abc: Join this channel to get access to members-only content",
                  "ERROR: [youtube] abc: Private video. Sign in if you've been granted access",
                  "ERROR: [youtube] abc: Sign in to confirm your age. This video may be inappropriate",
                  "ERROR: [youtube] abc: Video unavailable. Please try again later.",
                  "Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "
                  "'... reduce the prompt length or the maximum tokens requested, or try again later.'}}"):
        assert not V._is_bot_check(RuntimeError(other)), other


def test_persistent_stream_429_is_retried_then_stops_the_capture(tmp_path, monkeypatch):
    import time as _time

    monkeypatch.setattr(C, "FRAMES_DIR", tmp_path)
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    calls = []

    def always_429(video_id, dest_dir, settings):
        calls.append(video_id)
        raise RuntimeError("ERROR: unable to download video data: HTTP Error 429: Too Many Requests")

    monkeypatch.setattr(V, "_download_video_once", always_429)
    monkeypatch.setattr(V, "capture_frames",
                        lambda video, settings: V._download_video(video.video_id, str(tmp_path), settings))
    assert V.run_capture_only(None, _channels(), {"visuals": {}}, _lib(), budget=10) == (0, 0)
    assert calls == ["vidNEW"] * V.DOWNLOAD_ATTEMPTS          # retried, then the run stopped
    assert not V.has_stored_frames("vidNEW") and not V.has_stored_frames("vidOLD")


@pytest.mark.parametrize("msg", THROTTLES)
def test_capture_only_stops_on_any_throttle_without_marking(tmp_path, monkeypatch, msg):
    monkeypatch.setattr(C, "FRAMES_DIR", tmp_path)
    lib = {"videos": {f"v{i:02d}": {"channel_id": "CID_ON", "channel": "On", "title": f"T{i}",
                                     "url": f"u{i}", "published": f"2026-01-{i + 1:02d}"} for i in range(6)}}
    attempts = []

    def fake_capture(video, settings):
        attempts.append(video.video_id)
        if len(attempts) >= 2:
            raise RuntimeError(msg)
        V.save_frames(video.video_id, [])
        return 0

    monkeypatch.setattr(V, "capture_frames", fake_capture)
    assert V.run_capture_only(None, _channels(), {"visuals": {}}, lib, budget=100) == (1, 0)
    assert attempts == ["v05", "v04"]
    assert [v for v in lib["videos"] if V.has_stored_frames(v)] == ["v05"]


def test_reader_requeues_every_old_throttle_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "FRAMES_DIR", tmp_path)
    # both noted as failed by a capture run before this fix (newest first: vidNEW, vidOLD)
    V.save_frames("vidNEW", [], error=THROTTLES[1][:200])
    V.save_frames("vidOLD", [], error=BOT)
    state = {"visuals": {}}
    assert V.run_visuals(None, _channels(), state, _lib(), client=object(), budget=10, stored_only=True) == 0
    assert state["visuals"] == {}                            # nothing marked failed ...
    assert not V.has_stored_frames("vidNEW") and not V.has_stored_frames("vidOLD")  # ... both re-queued


def test_live_throttle_stops_the_run_after_one_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "FRAMES_DIR", tmp_path)
    calls = []

    def throttled(video, settings, client):
        calls.append(video.video_id)
        raise RuntimeError(THROTTLES[1])

    monkeypatch.setattr(V, "process_video_visuals", throttled)
    state = {"visuals": {}}
    assert V.run_visuals(None, _channels(), state, _lib(), client=object(), budget=10) == 0
    assert calls == ["vidNEW"]                               # stopped; vidOLD never tried
    assert state["visuals"] == {}
