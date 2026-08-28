"""Summarize a video (transcript + linked materials) into a structured brief via Claude.

Uses forced tool-use so the model must return a valid, typed object — no fragile
free-text JSON parsing. Model + token budgets come from Settings.
"""

from __future__ import annotations

import copy
import logging
from typing import Optional

from anthropic import Anthropic

from .config import Settings
from .models import Link, Material, Video

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You write short, factual briefs that help a busy person decide whether to watch a "
    "YouTube video in full. Base every statement ONLY on the transcript and materials "
    "provided — never invent facts. Be concise and specific. If no transcript was "
    "available, say so and work from the description and any materials.\n\n"
    "Verdict guidance:\n"
    "  - 'watch': high signal; the full video is worth the time.\n"
    "  - 'skim': a few useful bits; jump around or read the key points here.\n"
    "  - 'skip': low value, promotional, or fully captured by the key points.\n"
)

# Appended to the system prompt (and adds the field below) when reality_check is on.
REALITY_CHECK_INSTRUCTION = (
    "\n\nAlso fill in 'reality_check': a short, critical counterweight so the reader does "
    "not take the video at face value. Call out claims stated as certainty that are really "
    "opinion or prediction, FOMO/hype framing, signs the creator may be selling something, "
    "sponsored, or talking their own position, and any risks or counterarguments they "
    "skipped. Lean hardest on finance/investing content and ALWAYS note there that it is "
    "speculation, not financial advice — never tell the reader what to buy, sell, or do. "
    "Be proportional: if the video is measured and evidence-based, keep it to something "
    "like 'Measured and evidence-based — no major caveats.' Base it only on the provided "
    "transcript/description; do not invent bias you cannot support."
)

REALITY_CHECK_FIELD = {
    "type": "string",
    "description": "A short critical counterweight (see instructions), proportional to how "
    "overstated the content is. Never financial/other advice.",
}

BRIEF_TOOL = {
    "name": "submit_brief",
    "description": "Record the structured brief for one video.",
    "input_schema": {
        "type": "object",
        "properties": {
            "key_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-6 concise bullet points of the most important content.",
            },
            "takeaway": {
                "type": "string",
                "description": "The single main takeaway, in 1-2 sentences.",
            },
            "materials_notes": {
                "type": "string",
                "description": "Notable linked materials/resources and why they matter. Empty string if none.",
            },
            "verdict": {
                "type": "string",
                "enum": ["skip", "skim", "watch"],
            },
            "verdict_reason": {
                "type": "string",
                "description": "One sentence justifying the verdict.",
            },
        },
        "required": ["key_points", "takeaway", "verdict", "verdict_reason"],
    },
}


def _build_content(
    video: Video,
    transcript_text: str,
    transcript_ok: bool,
    materials: list[Material],
    listed_links: list[Link],
    settings: Settings,
) -> str:
    lines = [
        f"Video title: {video.title}",
        f"Channel: {video.channel_name}",
        f"URL: {video.url}",
        "",
    ]

    if video.description:
        lines += ["Description:", video.description.strip()[:4000], ""]

    if transcript_ok and transcript_text:
        clip = transcript_text[: settings.max_transcript_chars]
        if len(transcript_text) > settings.max_transcript_chars:
            clip += "\n[transcript truncated]"
        lines += ["Transcript:", clip, ""]
    else:
        lines += ["Transcript: (none available — do not fabricate spoken content)", ""]

    usable = [m for m in materials if m.ok]
    if usable:
        lines.append("Extracted text from linked materials:")
        for m in usable:
            lines.append(f"--- {m.category}: {m.filename or m.url} ---")
            lines.append(m.text)
            lines.append("")

    mention = [ln for ln in listed_links if ln.kind == "list"]
    if mention:
        lines.append("Other links in the description (not downloaded — for the materials list):")
        for ln in mention:
            lines.append(f"- {ln.url} ({ln.category})")
        lines.append("")

    return "\n".join(lines)


def summarize(
    video: Video,
    transcript_text: str,
    transcript_ok: bool,
    materials: list[Material],
    listed_links: list[Link],
    settings: Settings,
    client: Optional[Anthropic] = None,
) -> dict:
    """Return the brief dict: {key_points, takeaway, materials_notes, verdict, verdict_reason}."""
    client = client or Anthropic()
    content = _build_content(video, transcript_text, transcript_ok, materials, listed_links, settings)

    system = SYSTEM_PROMPT
    tool = BRIEF_TOOL
    if settings.reality_check:
        system = SYSTEM_PROMPT + REALITY_CHECK_INSTRUCTION
        tool = copy.deepcopy(BRIEF_TOOL)
        tool["input_schema"]["properties"]["reality_check"] = REALITY_CHECK_FIELD
        tool["input_schema"]["required"].append("reality_check")

    message = client.messages.create(
        model=settings.model,
        max_tokens=1800,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": "submit_brief"},
        messages=[{"role": "user", "content": content}],
    )

    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_brief":
            data = dict(block.input)
            data.setdefault("key_points", [])
            data.setdefault("takeaway", "")
            data.setdefault("materials_notes", "")
            data.setdefault("verdict", "skim")
            data.setdefault("verdict_reason", "")
            data.setdefault("reality_check", "")
            return data

    raise RuntimeError("Claude did not return a submit_brief tool call")
