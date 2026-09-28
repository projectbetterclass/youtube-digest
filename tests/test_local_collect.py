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
