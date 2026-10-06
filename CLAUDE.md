# Repo guide for Claude

This repo is two things:
1. **A tool** (`src/ytdigest/`) that summarizes new YouTube videos into a daily digest.
2. **A growing knowledge library** of what those videos say — full transcripts,
   extracted slide/PDF text, and (for chart-heavy channels) on-screen slides/charts
   read by Claude vision, all under `data/archive/<video_id>/`.

---

## Project state (keep this section current)

### Snapshot (2026-10-02)
Library: **7,625 videos, 7,439 with transcripts**, 699 with linked documents, 273 with
on-screen visuals (2,396 charts/slides). 20 channels in `config/watchlist.yml`.

**GitHub Actions is currently disabled on the account** (HTTP 422 "Actions has been
disabled for this user"), so neither the cloud digest nor the visuals job is running;
last cloud digest was 2026-09-22. Waiting on GitHub Support.

**"Collect my priority channels"** — until Actions is back, when the user says this, run on
the PC (not possible from a cloud session):
`.venv\Scripts\python.exe scripts\local_collect.py`. It pulls transcripts (no briefs — the
PC has no Anthropic key) for the user's **priority channels: JulienHimself, HealthyGamerGG,
Ben Yanes, Tom Nash, Ticker Symbol: YOU, BWB, David Carbutt, Felix & Friends, New Money,
Starter Story, Greg Isenberg, Riley Brown, Justin Sung** (`PRIORITY` in the script), through the Webshare proxy (`.env`), then commits
and pushes `data/`. It stands down by itself once the cloud digest commits again. Nothing
schedules it — the user chose to trigger it by hand. Only collect the channels the user
names; they haven't decided on the others.

### Where the copies live
- **User's PC (Windows):** working copy at `C:\Users\Gebruiker\Downloads\Youtube Scraper`
  (the folder name differs from the repo name). Local Claude Code sessions run here. To
  update it in PowerShell: `cd "C:\Users\Gebruiker\Downloads\Youtube Scraper"` then `git pull`.
- `C:\actions-runner\_work\youtube-digest\...` is the self-hosted runner's own checkout —
  don't work in it.
- Cloud Claude Code sessions clone the repo fresh; they can't reach the PC, so give the
  user the commands above when the PC copy needs updating.
- Chat history is **not** shared between sessions — anything every session should know
  goes in this file.

### How the daily job runs
Runs on **GitHub-hosted cloud runners** (`ubuntu-latest`) 3×/day (06:00 / 14:00 / 22:00 UTC).
All YouTube traffic (RSS, transcripts, yt-dlp) goes through a **Webshare residential proxy**
so cloud IPs aren't blocked. Secrets needed: `ANTHROPIC_API_KEY`, `WEBSHARE_PROXY_USERNAME`,
`WEBSHARE_PROXY_PASSWORD`. Webshare plan: 3 GB/month (cycle resets on the 24th); a
transcript fetch costs ~0.5 MB because it downloads the whole watch page. The Sep 24 – Oct 24
cycle is estimated at **~2.8 of 3 GB** used after the whole-channel runs — **no big backfills
until it resets on Oct 24**; routine "collect my priority channels" runs are small.

### Back-catalog backfill
- **Aswath Damodaran:** effectively done. 819 of his 1,413 videos collected (771 with
  transcripts); the rest are the valuation courses, excluded on purpose via
  `skip_playlist_titles`. `materials: true` means his slide PDFs and spreadsheets are
  extracted too (822 PDFs + 394 Excel files). Queue file: `data/backfill_queue/UCLvnJL8htRR1T9cbSccaoVw.json`.
- **Priority channels** (JulienHimself, HealthyGamerGG, Ben Yanes; since 2026-10-01 also Tom
  Nash, Ticker Symbol: YOU, BWB, David Carbutt, Felix & Friends; since 2026-10-02 also New
  Money, Starter Story, Greg Isenberg, Riley Brown, Justin Sung): target is the **whole
  channel** (`backfill` set just above each catalog size), collected via `local_collect.py`.
  **All 13 complete as of 2026-10-02:** HealthyGamerGG 1,035, David Carbutt 1,022, Tom Nash 869,
  Ben Yanes 612, JulienHimself 572, Greg Isenberg 455, New Money 440, Ticker Symbol: YOU 412,
  Felix & Friends 243, Justin Sung 236, Starter Story 203, Riley Brown 190, BWB 184. The few
  without a transcript are unplayable (private/removed), captions-off, or non-English.
- **Other channels** (Alex Hormozi, Vinh Giang, Leila Hormozi, Chris Raroque, Aswath): at their
  target as of 2026-10-02, collected from the PC.
  Chris Williamson and The Diary Of A CEO are new-uploads-only and miss everything since
  2026-09-22 (user chose not to catch them up).
- **Aswath's interviews on other channels** (173 transcripts + a CSV of 302 appearances)
  live in the separate Valuation Agent repo, not here.

### Phase 2 — on-screen visual capture (runs on the self-hosted runner)
What it does:
- `src/ytdigest/visuals.py` — downloads video (480p, no proxy), samples frames at ~1fps,
  deduplicates with perceptual hash, scores by "slide prior" (flat fill + straight lines),
  sends top candidates to Claude vision to classify and transcribe on-screen text
- `scripts/run_visuals.py` — entry point (`--budget`, `--channel` to target one channel)
- `.github/workflows/visuals.yml` — separate **self-hosted** workflow (video downloads
  stay off the metered proxy; cloud digest is unaffected); manual dispatch takes the
  same `budget` / `channel` inputs
- `tests/test_visuals.py` — no cv2/network needed
- Output: `data/archive/<video_id>/visuals.md` alongside the transcript

Opted in (`visual: true`): Ticker Symbol: YOU (163 read), BWB (100 read), David Carbutt (10 read,
+100 captured waiting), New Money,
and — from the 2026-10-01 screen check, user's choice — Greg Isenberg, Tom Nash, Justin Sung,
plus the borderline Riley Brown, Alex Hormozi, Starter Story, Chris Raroque.
Checked and kept **audio-only**: Felix & Friends, HealthyGamerGG, JulienHimself, Ben Yanes,
Chris Williamson, Leila Hormozi, Vinh Giang, The Diary Of A CEO; Aswath is excluded (his
slides are PDFs). Every channel has now been checked. Visuals can be switched on for a
channel later without re-fetching transcripts — the job enriches videos already in the library.
User's current run order for screen capture: Ticker Symbol: YOU, BWB, David Carbutt first.

**Capture-only mode (no API key needed):** `run_visuals.py --capture-only --channel X --budget N`
downloads videos and saves candidate frames to `frames/<id>/` (gitignored, PC-only); a normal
run later reads them with Claude vision instead of re-downloading. The PC's `.env` now has its
own `ANTHROPIC_API_KEY` ("PC screen capture" key, 2026-10-06). On 2026-10-06 the captured
Ticker Symbol: YOU and BWB batches were read (~9 charts kept per video, ~20s each). **David
Carbutt's 100 captured videos are still waiting** — his frames are mostly b-roll, so the user
should decide before spending on them: `run_visuals.py --channel "David Carbutt" --budget 25`.

The visuals job only advances while the PC's runner is online; the cloud digest is
independent. It keeps its own ledger `data/visuals_state.json` and writes only
`visuals.md`, so it never conflicts with the digest's commits.

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
