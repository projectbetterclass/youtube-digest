"""fetch_transcript retry policy (no network: the API class is faked)."""

import requests

from ytdigest import transcript as T


class IpBlocked(Exception):  # name matches the library's, which _is_ip_block keys on
    pass


class _Snip:
    def __init__(self, text):
        self.text = text


def _fake_api(outcomes, calls):
    """A YouTubeTranscriptApi stand-in that raises/returns `outcomes` in order."""

    class FakeApi:
        def __init__(self, proxy_config=None, http_client=None):
            calls.append(http_client)

        def fetch(self, video_id, languages):
            out = outcomes.pop(0)
            if isinstance(out, Exception):
                raise out
            return [_Snip(out)]

    return FakeApi


def test_proxy_retries_blocks_and_timeouts_immediately(monkeypatch):
    calls, slept = [], []
    monkeypatch.setattr(T, "_build_proxy_config", lambda: object())
    monkeypatch.setattr(T.time, "sleep", slept.append)
    monkeypatch.setattr(T, "YouTubeTranscriptApi", _fake_api(
        [IpBlocked("x"), requests.exceptions.ReadTimeout("slow"), "hello\nworld"], calls))
    text, ok, blocked, _ = T.fetch_transcript("vid", ["en"])
    assert (text, ok, blocked) == ("hello world", True, False)
    assert len(calls) == 3 and slept == []          # fresh IP each time, no back-off
    assert all(isinstance(c, T._TimeoutSession) for c in calls)


def test_proxy_exhausted_is_a_miss_not_a_block(monkeypatch):
    calls = []
    monkeypatch.setattr(T, "_build_proxy_config", lambda: object())
    monkeypatch.setattr(T, "YouTubeTranscriptApi",
                        _fake_api([IpBlocked("x")] * T.PROXY_ATTEMPTS, calls))
    text, ok, blocked, reason = T.fetch_transcript("vid", ["en"])
    assert (ok, blocked) == (False, False)          # don't halt the whole run
    assert len(calls) == T.PROXY_ATTEMPTS and "IpBlocked" in reason


def test_no_proxy_keeps_single_backoff_retry_and_reports_block(monkeypatch):
    calls, slept = [], []
    monkeypatch.setattr(T, "_build_proxy_config", lambda: None)
    monkeypatch.setattr(T.time, "sleep", slept.append)
    monkeypatch.setattr(T, "YouTubeTranscriptApi", _fake_api([IpBlocked("x"), IpBlocked("x")], calls))
    _, ok, blocked, _ = T.fetch_transcript("vid", ["en"])
    assert (ok, blocked) == (False, True) and slept == [20] and len(calls) == 2


def test_missing_captions_are_not_retried(monkeypatch):
    calls = []

    class TranscriptsDisabled(Exception):
        pass

    monkeypatch.setattr(T, "_build_proxy_config", lambda: object())
    monkeypatch.setattr(T, "YouTubeTranscriptApi", _fake_api([TranscriptsDisabled("off")], calls))
    _, ok, blocked, _ = T.fetch_transcript("vid", ["en"])
    assert (ok, blocked) == (False, False) and len(calls) == 1


def test_timeout_session_sets_a_default_timeout(monkeypatch):
    seen = {}
    monkeypatch.setattr(requests.Session, "request", lambda self, *a, **kw: seen.update(kw))
    T._TimeoutSession().get("https://example.com")
    assert seen["timeout"] == T.REQUEST_TIMEOUT
