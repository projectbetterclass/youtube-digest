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
    library.setdefault("videos", {})[brief.video.video_id] = record_from_brief(brief)


def _cell(text: str) -> str:
    """Make a value safe for a one-line markdown table cell."""
    return (text or "").replace("\n", " ").replace("|", "\\|").strip()


def render_index(library: dict) -> str:
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
        "| Date | Channel | Video | Verdict | Takeaway | Transcript |",
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
        out.append(
            f"| {date} | {channel} | {video_cell} | {verdict} | {takeaway} | [transcript]({vid}/transcript.md) |"
        )
    out.append("")
    return "\n".join(out)


def write_index(index_path: Path | str, library: dict) -> Path:
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as fh:
        fh.write(render_index(library))
    return index_path
