# Repo guide for Claude

This repo is two things:
1. **A tool** (`src/ytdigest/`) that summarizes new YouTube videos into a daily digest.
2. **A growing knowledge library** of what those videos say — full transcripts and
   extracted slide/PDF text under `data/archive/<video_id>/`.

## Answering questions from the library ("ask your library")

When the user asks about the **content** of the watched channels (not about the code),
treat `data/archive/` as the knowledge base and answer from it:

1. **Read `data/archive/INDEX.md` first** — it lists every archived video (channel,
   title, link, date, one-line takeaway). Use it to pick which videos are relevant.
2. **Search the transcripts:** `Grep` across `data/archive/**/transcript.md` (and
   `data/archive/**/materials/*.txt`) for the concepts in the question — try several
   phrasings, since wording in the transcript may differ from the question.
3. **Read the most relevant transcripts/materials** and synthesize a **concrete,
   specific** answer. Favor actionable detail (numbers, steps, named tactics) over
   generalities.
4. **Cite every claim** as `[Channel — Video Title](youtube-url)`, using the links in
   INDEX.md. If creators disagree, say so and attribute each view.
5. **Be honest about coverage:** say when the library has little on the topic. Answers
   are based on transcripts + linked slide/PDF text — **not** on-screen visuals (that
   visual-capture step, "Phase 2", isn't built yet).
6. **Stay critical — don't just parrot the creators.** These are opinionated YouTubers,
   not peer-reviewed sources. Distinguish claims stated as certainty from opinion or
   prediction; note when a creator may be selling something, sponsored, or talking their
   own position; surface risks/counterarguments they skipped; and when creators disagree,
   show the disagreement. For finance/investing questions, make clear it is speculation,
   **not financial advice** — never tell the user what to buy, sell, or do. Aim for a
   balanced, "here's the other side too" answer.

**Refresh before asking:** the digest runs on a self-hosted runner and pushes new data
to GitHub, so run `git pull` to include the latest videos.

## Working on the tool itself

Standard Python project. Package under `src/ytdigest/`; entry point `scripts/run.py`;
tests via `pytest` (they need no network or API key). Deployment and the self-hosted
runner setup are documented in `README.md`. The daily job commits `data/` and `digests/`
back to the repo, so pull before editing.
