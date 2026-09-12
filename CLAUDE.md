# Repo guide for Claude

This repo is two things:
1. **A tool** (`src/ytdigest/`) that summarizes new YouTube videos into a daily digest.
2. **A growing knowledge library** of what those videos say — full transcripts,
   extracted slide/PDF text, and (for chart-heavy channels) on-screen slides/charts
   read by Claude vision, all under `data/archive/<video_id>/`.

---

## Project state (keep this section current)

### How the daily job runs
Runs on **GitHub-hosted cloud runners** (`ubuntu-latest`) 3×/day (06:00 / 14:00 / 22:00 UTC).
All YouTube traffic (RSS, transcripts, yt-dlp) goes through a **Webshare residential proxy**
so cloud IPs aren't blocked. Secrets needed: `ANTHROPIC_API_KEY`, `WEBSHARE_PROXY_USERNAME`,
`WEBSHARE_PROXY_PASSWORD`.

### Back-catalog backfill (Aswath Damodaran)
- **Target:** 1000 videos (`backfill: 1000` in `config/watchlist.yml`)
- **Budget:** 100 videos per run (`backfill_budget_per_run: 100`)
- **Progress as of 2026-09-11:** ~302 done, ~698 remaining, ~817 in queue
- **Materials:** `materials: true` — slide PDFs also downloaded and extracted for each video
- **ETA:** ~3 days at current pace (100/run × 3 runs/day)
- Queue file: `data/backfill_queue/UCLvnJL8htRR1T9cbSccaoVw.json`

### Phase 2 — on-screen visual capture (merged; runs on the self-hosted runner)
Merged to `main` (was branch `phase2-visuals`, PR #18).

What it does:
- `src/ytdigest/visuals.py` — downloads video (480p, no proxy), samples frames at ~1fps,
  deduplicates with perceptual hash, scores by "slide prior" (flat fill + straight lines),
  sends top candidates to Claude vision to classify and transcribe on-screen text
- `scripts/run_visuals.py` — entry point
- `.github/workflows/visuals.yml` — separate **self-hosted** workflow (video downloads
  stay off the metered proxy; cloud digest is unaffected)
- `tests/test_visuals.py` — 9 tests (no cv2/network needed)
- Opted-in channels: Ticker Symbol: YOU, David Carbutt (Aswath excluded — his slides are PDFs)
- Output: `data/archive/<video_id>/visuals.md` alongside the transcript

Status: merged and deployed. The `visuals.yml` workflow runs on the self-hosted runner
(schedule + manual dispatch), so visuals only advance while the PC's runner is online;
the cloud digest is independent. It keeps its own ledger `data/visuals_state.json` and
writes only `visuals.md`, so it never conflicts with the digest's commits.

---

## Answering questions from the library ("ask your library")

When the user asks about the **content** of the watched channels (not about the code),
treat `data/archive/` as the knowledge base and answer from it:

1. **Read `data/archive/INDEX.md` first** — it lists every archived video (channel,
   title, link, date, one-line takeaway). Use it to pick which videos are relevant.
2. **Search the transcripts:** `Grep` across `data/archive/**/transcript.md` (plus
   `data/archive/**/materials/*.txt` for slide/PDF text and `data/archive/**/visuals.md`
   for on-screen slides/charts) for the concepts in the question — try several
   phrasings, since wording in the transcript may differ from the question.
3. **Read the most relevant transcripts/materials/visuals** and synthesize a **concrete,
   specific** answer. Favor actionable detail (numbers, steps, named tactics) over
   generalities. `visuals.md` holds figures the narration often skips (chart values,
   labeled diagrams) — use it for the numbers, but note its text is vision-read and may
   contain OCR errors.
4. **Cite every claim** as `[Channel — Video Title](youtube-url)`, using the links in
   INDEX.md. If creators disagree, say so and attribute each view.
5. **Be honest about coverage:** say when the library has little on the topic. Answers
   are based on transcripts + linked slide/PDF text, plus on-screen slides/charts for
   the chart-heavy channels opted in to visual capture (`visual: true`). Channels
   without it have **no** on-screen visuals captured — say so rather than guessing what
   was shown. Visual capture only runs when the self-hosted PC runner is online, so a
   just-uploaded video on an opted-in channel may not have its `visuals.md` yet.
6. **Stay critical — don't just parrot the creators.** These are opinionated YouTubers,
   not peer-reviewed sources. Distinguish claims stated as certainty from opinion or
   prediction; note when a creator may be selling something, sponsored, or talking their
   own position; surface risks/counterarguments they skipped; and when creators disagree,
   show the disagreement. For finance/investing questions, make clear it is speculation,
   **not financial advice** — never tell the user what to buy, sell, or do. Aim for a
   balanced, "here's the other side too" answer.

**Refresh before asking:** run `git pull` to include the latest videos before querying.

---

## Working on the tool itself

Standard Python project. Package under `src/ytdigest/`; entry point `scripts/run.py`;
tests via `pytest` (they need no network or API key). The daily job commits `data/` and
`digests/` back to the repo, so pull before editing.

Key files:
- `config/watchlist.yml` — channels, backfill targets, settings
- `src/ytdigest/pipeline.py` — main per-video processing pipeline
- `src/ytdigest/summarize.py` — Claude API calls for briefs
- `src/ytdigest/visuals.py` — Phase 2 on-screen visual capture
- `.github/workflows/digest.yml` — cloud runner workflow
- `.github/workflows/visuals.yml` — self-hosted visual capture workflow
