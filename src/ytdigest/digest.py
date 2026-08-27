"""Render briefs into the daily markdown digest."""

from __future__ import annotations

from pathlib import Path

from .models import Brief

_VERDICT_BADGE = {
    "watch": "✅ Watch in full",
    "skim": "🟡 Skim",
    "skip": "⏭️ Skip",
}

_CATEGORY_LABEL = {
    "pdf": "PDF",
    "pptx": "PPTX",
    "slideshare": "SlideShare",
    "speakerdeck": "Speaker Deck",
    "github": "GitHub",
    "paper": "Paper",
    "other": "Link",
}


def render_brief(brief: Brief) -> str:
    v = brief.video
    badge = _VERDICT_BADGE.get(brief.verdict, brief.verdict)
    out = [f"## [{v.title}]({v.url})", "", f"**{v.channel_name}** · {badge}"]
    if brief.verdict_reason:
        out.append(f"> {brief.verdict_reason}")
    out.append("")

    if brief.key_points:
        out.append("**Key points**")
        out += [f"- {p}" for p in brief.key_points]
        out.append("")

    if brief.takeaway:
        out += [f"**Takeaway:** {brief.takeaway}", ""]

    # Notable materials: extracted docs first, then mention-only links.
    material_lines = []
    for m in brief.downloaded_materials:
        label = _CATEGORY_LABEL.get(m.category, m.category)
        if m.ok:
            material_lines.append(f"- 📎 [{label}]({m.url}) — text extracted")
        elif m.error:
            material_lines.append(f"- 📎 [{label}]({m.url}) — not extracted ({m.error})")
    for ln in brief.listed_links:
        label = _CATEGORY_LABEL.get(ln.category, ln.category)
        material_lines.append(f"- [{label}]({ln.url})")

    if brief.materials_notes:
        out += [f"**Materials:** {brief.materials_notes}", ""]
    if material_lines:
        out.append("**Notable materials & links**")
        out += material_lines
        out.append("")

    if not brief.transcript_available:
        out += ["_No transcript/captions were available; brief is based on the description"
                " and any linked materials._", ""]

    if brief.archive_dir:
        # digests/*.md live one level below the repo root, so link up into data/.
        rel = brief.archive_dir.replace("\\", "/").strip("/")
        out += [f"[Full transcript & extracted text →](../{rel}/transcript.md)", ""]

    out.append("---")
    return "\n".join(out)


def render_digest(date_str: str, briefs: list[Brief]) -> str:
    n = len(briefs)
    header = [
        f"# 📺 YouTube Digest — {date_str}",
        "",
        f"{n} new video{'s' if n != 1 else ''} across your watchlist.",
        "",
        "---",
        "",
    ]
    body = "\n".join(render_brief(b) for b in briefs)
    return "\n".join(header) + "\n" + body + "\n"


def write_digest(digests_dir: Path, date_str: str, markdown: str) -> Path:
    digests_dir.mkdir(parents=True, exist_ok=True)
    path = digests_dir / f"{date_str}.md"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(markdown)
    return path
