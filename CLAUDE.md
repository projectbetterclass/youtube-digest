# Repo guide for Claude

This repo is two things:
1. **A tool** (`src/ytdigest/`) that summarizes new YouTube videos into a daily digest.
2. **A growing knowledge library** of what those videos say — full transcripts,
   extracted slide/PDF text, and (for chart-heavy channels) on-screen slides/charts
   read by Claude vision, all under `data/archive/<video_id>/`.

---

## Project state (keep this section current)

### Snapshot (2026-10-27)
Library: **11,511 videos, 11,146 with transcripts**, 699 with linked documents, 1,911 with
on-screen visuals read (12,076 charts/slides). 24 channels in `config/watchlist.yml` (Invest with Henry added 2026-10-14, collected 2026-10-15) plus the 42-video Buddha playlist (no transcripts yet, see Playlists below); 1,568 of the videos are YouTube Shorts.
**The daily local job is ON since 2026-10-23** (details below). Proxy data is used up until
the next Webshare reset; whether the 1 GB plan bought 2026-10-11 replaced the 3 GB plan (then
no 3 GB reset on 24 Oct) is unconfirmed — ask the user to check the dashboard.

**GitHub Actions is currently disabled on the account** (HTTP 422 "Actions has been
disabled for this user"), so neither the cloud digest nor the visuals job is running;
last cloud digest was 2026-09-22. Waiting on GitHub Support.

**"Collect my priority channels"** — until Actions is back, when the user says this, run on
the PC (not possible from a cloud session):
`.venv\Scripts\python.exe scripts\local_collect.py`. It pulls transcripts (no briefs — the
PC has no Anthropic key) for the user's **priority channels: JulienHimself, HealthyGamerGG,
Ben Yanes, Tom Nash, Ticker Symbol: YOU, BWB, David Carbutt, Felix & Friends, New Money,
Starter Story, Greg Isenberg, Riley Brown, Justin Sung** (`PRIORITY` in the script), through the Webshare proxy (`.env`), then commits
and pushes `data/`. It stands down by itself once the cloud digest commits again.
`local_collect.py` itself isn't scheduled (it's for back catalogs, earlier misses and named
channels); for any of that, only collect the channels the user names.

**Daily local job (user asked 2026-10-23: "run every day when the pc is on"; PR #66, merged and
switched on 2026-10-23 at the user's request):**
`scripts/daily_local.py`, run by the Windows Task Scheduler task **"YouTube library - daily"**
(install/update: `powershell -ExecutionPolicy Bypass -File scripts\install_daily_task.ps1`;
turn off: same with `-Remove`). It checks hourly 10:00–24:00 and 15 min after log-on, runs at
most twice a day (12 h after its last *successful* run, so a failed run is retried at the next
check), with no window, independent of chat sessions. Each run, for every watchlist channel:
reads the RSS feed (15 newest uploads); collects transcripts (no briefs) for uploads from the
last 30 days not yet in the library — 5 days (`max_age_days`) for the new-uploads-only channels
Chris Williamson and The Diary Of A CEO, so their skipped backlog stays skipped; Shorts only
where `shorts:` is set — at most 150 per run; then screen-captures up to 10 recent (≤30 days)
uncaptured uploads on `visual: true` channels (needs the PC's `ANTHROPIC_API_KEY`; uploads that
`local_collect.py` stored without a date get it from the feed, back catalogs stay dateless and
are never captured by it); then commits
and pushes `data/`. On a push conflict it merges library records (theirs + ours) instead of
stopping; it refuses (and says so) when the copy isn't on `main`, a rebase is half-done, or
unpushed local commits touch files outside `data/`. It stops cleanly, marking nothing, when the
proxy data runs out (every attempt a ProxyError) or YouTube blocks the PC (RSS goes through the
proxy too: when every feed fails, the run doesn't count and retries hourly); stands down once the
cloud digest commits again; shares `local_collect.py`'s lock. Log:
`%LOCALAPPDATA%\ytdigest\daily.log`; last result (OK/FAILED + counts): `daily_status.txt` next
to it. Expected cost: ~65–130 MB of proxy a month, well under $1/month of API credit.
First run under the scheduler (2026-10-23 15:31): every feed got `402 Payment Required` from the
proxy, so it reported FAILED and retries hourly until the proxy data is back. To check on it:
read `daily_status.txt` / `daily.log`, or `Get-ScheduledTaskInfo -TaskName "YouTube library - daily"`.

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
- **Who reads this library:** the Valuation Agent (`video_source.py`, private repo), the
  Assistant (`scripts/video_source.py`, public repo) and, since 2026-10-11, the exercise app
  intensity-applied (`scripts/video_source.py`, private; for Ben Yanes, the training channel)
  — one video by URL (transcript + chart readings), or `--search "words"` across every video
  (ranked, with excerpts). The three copies are the same code (only the path to this repo
  differs); change all three together. Event watcher and Market-Forensics have no access.

### How the daily job runs
Runs on **GitHub-hosted cloud runners** (`ubuntu-latest`) 3×/day (06:00 / 14:00 / 22:00 UTC).
All YouTube traffic (RSS, transcripts, yt-dlp) goes through a **Webshare residential proxy**
so cloud IPs aren't blocked. Secrets needed: `ANTHROPIC_API_KEY`, `WEBSHARE_PROXY_USERNAME`,
`WEBSHARE_PROXY_PASSWORD`. Webshare plan: 3 GB/month (cycle resets on the 24th); a
transcript fetch costs ~0.5 MB because it downloads the whole watch page. The Sep 24 – Oct 24
cycle: the user's Webshare dashboard showed **2.5 of 3 GB** (19,870 requests) on 2026-10-08
21:58; ~975 transcripts since then put it at an estimated **~2.85–2.9 GB** — **no big runs until
it resets on Oct 24**; a "collect my priority channels" catch-up (~20–50 videos) is fine.
Measured cost this cycle: **~0.35–0.43 MB per transcript**. The PC has no Webshare API key, so
ask the user for the dashboard figure before any big run. (Its "projected usage" warning is a
straight-line extrapolation; ignore it.)

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
- **Alex Hormozi, Leila Hormozi, Vinh Giang: whole channel, complete 2026-10-09** (user's
  choice and order; targets 600 / 350 / 450): Alex 573 (558 with transcripts), Leila 305 (299),
  Vinh 411 (409). They are not in `PRIORITY`; collect their new uploads with
  `local_collect.py --channel "<name>"` when the user asks. While `local_collect.py` runs, pause
  the screen reader if one is running (both commit `data/` in the same working copy).
- **Training channels (user, 2026-10-11): Sean Nalewanyj, TheQuadfatherBW, JPG Coaching** added,
  with Ben Yanes the fourth. **All collected 2026-10-11, videos + Shorts** (the proxy ran out once
  mid-run; the guarded run stopped cleanly, the user bought a new 1 GB Webshare plan, it resumed):
  Ben Yanes 598 videos + 684 Shorts, Sean Nalewanyj 397 + 289, TheQuadfatherBW 6 + 67, JPG Coaching
  25 + 306. 36 Shorts are flagged `music_captions` (Ben 19, Sean 12, JPG 5): their content is on
  screen; reading just those would cost ~65 cents if the user ever wants it. New Shorts later need
  `local_collect.py --channel "<name>" --shorts`. Guard for any big run: when the proxy runs out every
  fetch fails with ProxyError and would be recorded as "no transcript"; stop at the first
  `No transcript for ... (ProxyError` line, delete entries whose `transcript_miss` mentions
  ProxyError, and transcript folders not in library.json.
- **Instagram:** the user asked to collect these creators' Instagram Reels too. Decision: don't
  scrape Instagram (no captions to fetch, needs a login, against Instagram's terms, risks the
  account). Their Reels are mostly cross-posted as YouTube Shorts, so the Shorts route covers them;
  a one-off reel that's only on Instagram can be transcribed by hand from a file the user saves.
  Many training Shorts/Reels are music + text on screen: their captions are lyrics, flagged
  `music_captions` by the Shorts PR; their content needs screen capture to be read.
- **Other channels** (Chris Raroque, Aswath): at their target as of 2026-10-02.
  No transcript collection has run for the priority channels since 2026-10-02, so their
  newer uploads (20+ by 2026-10-07) wait for the next "collect my priority channels".
  **Without the proxy** (home connection; run with WEBSHARE_PROXY_USERNAME/PASSWORD set empty —
  from **bash** (`WEBSHARE_PROXY_USERNAME= WEBSHARE_PROXY_PASSWORD= .venv/Scripts/python.exe ...`);
  in Windows PowerShell `$env:X = ''` *deletes* the variable, so `.env` refills it and the proxy is used):
  safe, since an IP block stops the run without marking anything, but YouTube allows few: on
  2026-10-19 it gave 15 (Felix 7, Greg Isenberg 4, Ticker 2, HealthyGamerGG 2) then IpBlocked;
  on 2026-10-24 (user asked, block had lifted after 5 days) 18 more (BWB 5, Riley Brown 4,
  HealthyGamerGG 4, Felix 3, Ticker 1, Greg 1) then IpBlocked again, in ~2 minutes; on
  2026-10-27 (3 days later) 16 more (Riley Brown 6, Felix 2, Starter Story 2, New Money 2,
  HealthyGamerGG 1, Greg 1, Ticker 1, BWB 1) then IpBlocked. The proxy still answered 402 on
  2026-10-27, three days after the expected 24 Oct reset: the 3 GB plan most likely didn't renew.
  Use it only for a handful; the rest waits for the proxy reset.
  Chris Williamson and The Diary Of A CEO are new-uploads-only and miss everything from
  2026-09-22 until about 2026-10-18 (user chose not to catch them up); the daily local job
  takes their new uploads from then on (its 5-day window).
- **Aswath's interviews on other channels** (173 transcripts + a CSV of 302 appearances)
  live in the separate Valuation Agent repo, not here.
- **Playlists the user names** (since 2026-10-12): `local_collect.py --playlist <id or link>`
  pulls one playlist's videos in playlist order, from whatever channel (nothing is added to
  the watchlist), and keeps the order in `data/playlists/<id>.json` (title, channel, and each
  video's id, title, channel, length). Re-running it fetches only new videos and earlier misses.
  A playlist takes captions in **any language**: a video with none in `transcript_languages`
  keeps its own-language captions (hand-made before auto-generated), under an italic note in
  `transcript.md` naming the language. Channel runs and the cloud digest stay English-only.
  (The Buddha playlist's first run, 2026-10-14 20:32–20:38, started minutes before this fix was
  merged and looked for English only: **all 42 videos are still without a transcript**, each a
  `NoTranscriptFound` miss = captions exist in another language. Re-run
  `local_collect.py --playlist PLqnSdW-e2Bah9Lh0MBn7JjW5kswNUDcZd` after the proxy reset (~17 MB);
  it retries these misses. Checked 2026-10-23.)
  ~0.4 MB of proxy per video. First one: the **Buddha playlist** `PLqnSdW-e2Bah9Lh0MBn7JjW5kswNUDcZd`
  (the Buddha's teaching in plain words), for the Buddha goal in the user's time-tracker
  app (the Assistant repo); the user has listened to it once already.
- **Invest with Henry** (`UC2Zg12phLyX1KTnH6D47d9g`, options trading; user named it 2026-10-14
  for the Options trading branch of their time-tracker app): whole channel incl. Shorts (`backfill:
  1000`, `shorts: 120`). **All 883 videos collected (2026-10-14/15)**, plus 27 of his 89 Shorts; the
  proxy data (the 1 GB plan bought 2026-10-11) ran out at 22:32 on 2026-10-15 and the guarded run
  stopped cleanly. **Left: ~62 Shorts (~25 MB)** — collect after the 24 Oct reset with
  `local_collect.py --channel "Invest with Henry" --shorts` (guarded). Not in `PRIORITY`. He sells
  paid courses, and his return figures are his own claims, so stay critical when answering from his
  videos. Screen check pending (`visual: false` until then): option chains and P/L diagrams may be
  worth reading.

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

Opted in (`visual: true`): Ticker Symbol: YOU, BWB, Tom Nash, New Money (whole channels — see
progress below), and — from the 2026-10-01 screen check, user's choice — Greg Isenberg, Tom Nash, Justin Sung,
plus the borderline Riley Brown, Alex Hormozi, Starter Story, Chris Raroque.
**David Carbutt: transcripts only** since 2026-10-06 (user's choice; 20 videos were read, then
switched off — his frames are mostly b-roll). Checked and kept **audio-only**: Felix & Friends, HealthyGamerGG, JulienHimself, Ben Yanes,
Chris Williamson, Leila Hormozi, Vinh Giang, The Diary Of A CEO, and (screen check 2026-10-11, 17 sampled
videos/Shorts, frames reviewed against the transcripts) Sean Nalewanyj, TheQuadfatherBW, JPG Coaching; Ben
Yanes's Shorts too. These creators teach by talking: frames are speech subtitles, exercise labels, b-roll and
ads. Exceptions, small: Sean's videos sometimes show a study screenshot (citation + design); JPG Coaching's
music-only Shorts carry their one-line tip as on-screen text. If ever wanted, read only Shorts flagged
`music_captions` (a few cents), and sample Shorts evenly over their length (the pipeline's frames cluster in
the first ~15 s, missing later tips). Aswath is excluded (his
slides are PDFs). Every channel has now been checked. Visuals can be switched on for a
channel later without re-fetching transcripts — the job enriches videos already in the library.
User's run order for screen capture: Ticker Symbol: YOU, Tom Nash, BWB, New Money.

**Capture-only mode (no API key needed):** `run_visuals.py --capture-only --channel X --budget N`
downloads videos and saves candidate frames to `frames/<id>/` (gitignored, PC-only); a normal
run later reads them with Claude vision instead of re-downloading. The PC's `.env` now has its
own `ANTHROPIC_API_KEY` ("PC screen capture" key, 2026-10-06). On 2026-10-06 the captured
Ticker Symbol: YOU and BWB batches were read (~9 charts kept per video, ~20s each, ~1.8¢ each).
**User's plan (2026-10-06): screen capture for the WHOLE channel of Ticker Symbol: YOU, Tom
Nash, BWB and New Money** — the valuation agent is the main consumer. Capture-only runs fill
`frames/`; `run_visuals.py --stored-only --channel X --budget 25` reads alongside without
downloading. An out-of-credit API error stops a read batch without marking videos, so a
re-run after topping up continues cleanly.
**DONE 2026-10-08 10:20 — the whole-channel plan is complete:** Ticker Symbol: YOU 412/412
(3,509 charts), BWB 184/184 (1,714), Tom Nash 855/869 (2,756; the other 14 are members-only and
can't be downloaded), New Money 440/440 (3,961). Library: 1,911 videos read, 1,568 with charts,
12,076 charts. The API credit ran out once mid-run (the reader stopped cleanly, the user topped
up, reading resumed). Nothing is running now. New uploads on these channels need a screen run
after their transcripts arrive (gently: one channel at a time, `--workers 2`).
**YouTube throttling, 2026-10-07 03:15:** after ~3.5 h of 6 parallel downloads, YouTube started
answering every download from the PC with "Sign in to confirm you're not a bot" (a temporary
rate limit on the home connection). The jobs were stopped and the 38 videos wrongly marked
failed were re-queued (23289cd6). It had cleared by 17:17 (14 h later).
**Resumed 17:19, gently:** one channel at a time (Ticker → Tom Nash → New Money), `--workers 2`,
under a supervisor script (session scratchpad `capture_chain.py`) that kills capture at the
first throttle message and re-queues anything it noted. **That stop is now built into
`visuals.py` (PR #62, merged 2026-10-11):** on a bot check, rate limit, captcha, IP block or a
persistent 429, capture stops the whole run and marks nothing, and an old throttle note is
re-queued; plain `--capture-only` runs are safe without the supervisor. Never work around
YouTube's check with browser cookies.
**Long jobs live only as long as the chat session.** Anything started from a Claude Code
session is killed when that session closes, including processes launched with PowerShell
`Start-Process` (they stay in the session's Windows job). That stopped capture at 21:32 on
2026-10-07 and a transcript run at 22:13 on 2026-10-08. Run long jobs in-session with
keep-awake on, and tell the user to keep the chat open; or give them the command to paste into
their own PowerShell window. The app's Terminal-panel tool would outlive the session, but on
this PC its shell integration file is missing, so it can't type commands. Both
`local_collect.py` (saves every 10) and the visuals reader (ledger per batch) resume cleanly
after a kill. Before committing, delete transcript folders from a cut-off batch that aren't in
`library.json`.
A download that drops mid-file ("N bytes read, M more expected") is noted as failed by the
current code but is not a dead video: re-queue it (delete its ledger entry and `frames/<id>/`).

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

---

## Reviewing the tool (the review contract)

A review of the tool is **grounded by construction** — read the code and run `pytest` before any remark:
- **Read before you remark** — open the files under `src/ytdigest/`; cite `path:line`; no claim you
  haven't read the code for.
- **Run `pytest` before concluding** (no network / API key needed); never say something passes you didn't run.
- **Judge against this repo's rules** — summaries grounded in the transcript (never invented), stay
  critical / never financial advice, safe-linked-materials-only, secrets from CI never committed — not generic style.
- **Every finding cites `path:line`** + the check that proves it; specific, falsifiable, most-serious first.

Run a full pass with **`/review`** (`.claude/commands/review.md`). (When answering *content* questions
from the library, the "ask your library" rules above apply instead.)
