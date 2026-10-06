"""Crash-safe writes: an interrupted write leaves the old file intact."""

import pytest

from ytdigest import fsutil


def test_atomic_write_replaces_whole_file(tmp_path):
    p = tmp_path / "INDEX.md"
    fsutil.atomic_write_text(p, "old\n")
    fsutil.atomic_write_text(p, "new content\n")
    assert p.read_text(encoding="utf-8") == "new content\n"
    assert [x.name for x in tmp_path.iterdir()] == ["INDEX.md"]  # no temp files left


def test_interrupted_write_keeps_the_old_file(tmp_path, monkeypatch):
    p = tmp_path / "state.json"
    fsutil.atomic_write_text(p, '{"ok": true}\n')

    def boom(src, dst):
        raise KeyboardInterrupt  # e.g. the process is stopped at the worst moment

    monkeypatch.setattr(fsutil.os, "replace", boom)
    with pytest.raises(KeyboardInterrupt):
        fsutil.atomic_write_text(p, "half-writ")
    assert p.read_text(encoding="utf-8") == '{"ok": true}\n'
    assert [x.name for x in tmp_path.iterdir()] == ["state.json"]
