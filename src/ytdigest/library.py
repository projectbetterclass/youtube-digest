"""Maintain a searchable index of the archived library.

Two artifacts, both committed to the repo:
  * data/library.json      — the source of truth: one rich record per processed video.
  * data/archive/INDEX.md  — rendered from library.json; a table Claude reads first to
                             pick relevant videos before grepping their transcripts.

This is what powers "ask your library": open Claude Code here and ask a question about
the video content — it reads INDEX.md, searches the transcripts, and answers with
citations. No embeddings or vector store needed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Brief


def load_library(path: Path | str) -> dict:
    path = Path(path)
    if not path.exists():
        return {"videos": {}}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("videos", {})
    return data


def save_library(path: Path | str, library: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(library, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def record_from_brief(brief: Brief) -> dict:
    v = brief.video
    return {
        "channel": v.channel_name,
        "channel_id": v.channel_id,  # lets Phase 2 match opted-in channels reliably
        "title": v.title,
        "url": v.url,
        "published": v.published.isoformat() if v.published else None,
        "verdict": brief.verdict,
        "takeaway": brief.takeaway,
        "had_materials": brief.had_materials,
        "transcript_available": brief.transcript_available,
        "transcript_path": f"data/archive/{v.video_id}/transcript.md",
    }


def add_brief(library: dict, brief: Brief) -> None:
    """Insert/update a video's record, preserving Phase 2 visual fields across re-runs."""
    videos = library.setdefault("videos", {})
    prev = videos.get(brief.video.video_id, {})
    rec = record_from_brief(brief)
    for k in ("has_visuals", "visuals_path"):  # written later by the visuals job
        if k in prev:
            rec[k] = prev[k]
    videos[brief.video.video_id] = rec


def _cell(text: str) -> str:
    """Make a value safe for a one-line markdown table cell."""
    return (text or "").replace("\n", " ").replace("|", "\\|").strip()


def _has_visuals(vid: str, rec: dict, archive_dir: Path | None) -> bool:
    """Whether to show a visuals link: recorded flag, or a visuals.md present on disk.

    Disk detection lets the (cloud) digest surface visuals produced by the separate
    self-hosted visuals job without the two jobs ever writing the same files.
    """
    if rec.get("has_visuals"):
        return True
    if archive_dir is not None:
        p = archive_dir / vid / "visuals.md"
        return p.exists() and p.stat().st_size > 0
    return False


def render_index(library: dict, archive_dir: Path | None = None) -> str:
    videos = library.get("videos", {})
    epoch = ""  # unknown dates sort last

    def sort_key(item):
        return item[1].get("published") or epoch

    rows = sorted(videos.items(), key=sort_key, reverse=True)

    out = [
        "# 📚 Library index",
        "",
        f"{len(rows)} video{'s' if len(rows) != 1 else ''} archived. This is the index for "
        "asking questions about the content — see the repo `CLAUDE.md` for how to answer.",
        "Each transcript link points to the full text under this folder.",
        "",
        "| Date | Channel | Video | Verdict | Takeaway | Sources |",
        "|---|---|---|---|---|---|",
    ]
    for vid, r in rows:
        date = (r.get("published") or "")[:10] or "—"
        channel = _cell(r.get("channel", ""))
        title = _cell(r.get("title", ""))
        url = r.get("url", "")
        verdict = _cell(r.get("verdict", "") or "—")
        takeaway = _cell(r.get("takeaway", "") or "—")
        video_cell = f"[{title}]({url})" if url else title
        sources = f"[transcript]({vid}/transcript.md)"
        if _has_visuals(vid, r, archive_dir):
            sources += f" · [visuals]({vid}/visuals.md)"
        out.append(
            f"| {date} | {channel} | {video_cell} | {verdict} | {takeaway} | {sources} |"
        )
    out.append("")
    return "\n".join(out)


def write_index(index_path: Path | str, library: dict) -> Path:
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    # The index lives at data/archive/INDEX.md, so its parent is the archive dir — pass it
    # so visuals links appear for any video that has a visuals.md on disk.
    with open(index_path, "w", encoding="utf-8") as fh:
        fh.write(render_index(library, archive_dir=index_path.parent))
    return index_path
