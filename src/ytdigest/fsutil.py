"""Crash-safe file writes.

Several jobs rewrite the library's shared files (state.json, library.json, INDEX.md) and
any of them can be stopped mid-write — the PC sleeps, a run is cancelled, a process is
killed. A plain open(..., "w") truncates first, so an interruption leaves an empty or
half-written file behind (this happened to INDEX.md on 2026-10-06 and was committed).
Writing to a temp file in the same folder and swapping it in with os.replace means
readers only ever see the old file or the complete new one.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # atomic on Windows and POSIX within one volume
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
