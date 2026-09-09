# YouTube Digest

Watch a list of YouTube channels and get a **daily brief** of every new video —
without watching them end to end. For each new upload the tool:

1. fetches the **transcript/captions** (no YouTube API key),
2. downloads **safe linked materials** (PDF / PPTX / SlideShare / Speaker Deck) and extracts their text — other links (GitHub, papers) are just listed,
3. **summarizes** transcript + materials into a short brief (key points, takeaway, notable materials, and a *skip / skim / watch* verdict) with the Claude API,
4. collects the briefs into a dated markdown **digest**, commits it, and opens a **GitHub Issue** so you get a push notification on phone + desktop.

It runs as a scheduled **GitHub Action on GitHub's cloud runners**, routing transcript
fetches through a residential proxy so cloud IPs aren't blocked by YouTube.

> This is **Phase 1** (transcript + linked materials). Phase 2 (on-screen visual
> capture for slide-heavy videos) is intentionally not built yet.

---

## Where things live

| What | Where |
|---|---|
| The notification / brief you read | the **GitHub Issue** opened each run |
| Archive of all briefs | `digests/YYYY-MM-DD.md` |
| Raw transcripts + extracted slide text | `data/archive/<video_id>/` (linked from each brief) |
| What's already been processed | `data/state.json` |

---

## How the daily job runs (no PC required)

YouTube **blocks transcript requests from cloud-provider IPs**. The workflow routes
all traffic (RSS feeds, transcripts, yt-dlp enumeration) through a **Webshare
residential proxy**, so GitHub-hosted `ubuntu-latest` runners work fine.

**What that means day to day:**

- Runs automatically 3×/day (06:00 / 14:00 / 22:00 UTC) on GitHub's free hosted
  runners — your PC does not need to be on.
- The look-back window is `max_age_days` (default **3 days**), so a missed run catches
  up automatically.
- No PC required. The only ongoing cost is the Webshare residential proxy
  (~a few $/mo; transcripts are tiny so bandwidth is minimal).

### First-time repo setup (one-time, on your PC)

These steps get the repo wired up so GitHub Actions run automatically. Do them once
on any PC; after that the daily job runs in the cloud without your machine.

1. **Fork / clone the repo** (or use it as a template):
   ```bash
   git clone https://github.com/projectbetterclass/youtube-digest.git
   cd youtube-digest
   ```

2. **Add your secrets** under **Settings → Secrets and variables → Actions**:
   | Secret | Where to get it |
   |---|---|
   | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
   | `WEBSHARE_PROXY_USERNAME` | [Webshare](https://www.webshare.io/) → Proxy → Residential |
   | `WEBSHARE_PROXY_PASSWORD` | same |

3. **Edit `config/watchlist.yml`** — add the channels you want to watch (see
   [Configuration](#configuration-configwatchlistyml) below).

4. **Trigger a first run** from the **Actions** tab → *Daily YouTube Digest* →
   *Run workflow* to confirm everything works.

5. **Install GitHub Mobile** on your phone — you'll get a push notification each time
   the digest Issue opens.

After step 4, the workflow runs on its own schedule forever.

---

## Ask your library

Every run adds the full transcript + extracted slide/PDF text to `data/archive/`, so the
repo becomes a growing **knowledge base** of what your channels say. To query it, just
**open Claude Code in this folder and ask** — no separate app, no embeddings:

```bash
git pull                        # get the newest videos first
# then, in Claude Code, ask e.g.:
#   "Across my channels, what's the consensus on pricing a new offer?"
```

Claude reads `data/archive/INDEX.md` (a table of every archived video), searches the
transcripts, and answers with **citations** to the specific creators/videos. The
[`CLAUDE.md`](CLAUDE.md) file primes it to do this and to cite sources.

- Build/refresh the index without waiting for a run: `python scripts/build_index.py`.
- Scope: answers draw on transcripts + linked slide/PDF text, **not** on-screen visuals
  (that's Phase 2). Retrieval is Claude Code's built-in search — plenty until the
  library gets very large, at which point an index/embeddings step can be added.

## Import a channel's back-catalog

By default the tool only sees a channel's ~15 latest uploads (RSS limit), so the library
grows *forward*. To also pull in **past** videos, add a `backfill: N` to a channel — it
imports that channel's **N most-recent past videos** (transcripts only, no AI brief, so
it costs ~nothing in API):

```yaml
  - name: "Justin Sung"
    channel_id: UC2Zs9v2hL2qZZ7vsAENsg4w
    backfill: 100        # import the last 100 videos' transcripts
```

It runs as a **slow auto-drip**: each daily run imports up to `backfill_budget_per_run`
(default 10) old videos and resumes day after day until each channel's target is met. It
reuses `state.json`, so it never re-imports and self-terminates. Enumeration uses `yt-dlp`
(metadata only — no video downloads).

**Reality check:** the binding constraint is YouTube's per-IP transcript rate limit
(you're not using a proxy), so deep backfills across many channels drip in over
**weeks**, not hours — a block just defers and resumes next run. Raise
`backfill_budget_per_run` to push harder (more block risk), or add a residential proxy
(see below) to go much faster.

**Per-channel extras:**
- `materials: true` — also download that channel's linked slide/PDF decks during
  backfill (great for slide-heavy creators like Aswath Damodaran — no screenshots needed).
- `skip_playlist_titles: ["..."]` + `backfill_scan: N` — exclude videos in playlists whose
  title contains any of those strings (e.g. courses you've already watched) and scan `N`
  uploads deep to find the rest. After setting these, run
  `python scripts/prepare_backfill.py` to build the filtered queue at
  `data/backfill_queue/<channel_id>.json`.

## Reality-check lens

Every brief includes a **🔍 Reality check** — a short critical counterweight that flags
hype, overconfidence, undisclosed bias/selling, and skipped risks, leaning hardest on
finance/investing (and never giving buy/sell advice — it's speculation, not advice). It's
adaptive: strong pushback on hype, and just a quick "no major caveats" on measured
content. Your "ask the library" answers stay balanced the same way (see `CLAUDE.md`).
Turn it off with `reality_check: false` in the watchlist settings.

## Configuration (`config/watchlist.yml`)

```yaml
settings:
  model: claude-haiku-4-5     # cheap + fast; use claude-sonnet-5 for richer briefs
  max_age_days: 3             # look-back window; also the "missed a day" catch-up
  transcript_languages: [en]
  request_delay_seconds: 1.0  # spacing between channel feed fetches
  max_videos_per_run: 50      # cost guard
channels:
  - name: 3Blue1Brown
    channel_id: UCYO_jab_esuFRV4b17AJtAw
```

Add a channel by pasting a `- name: / channel_id:` block. To find a `channel_id`:

```bash
python scripts/resolve_channel.py https://www.youtube.com/@3blue1brown
```

The daily schedule and secrets live in the workflow:
- **Schedule:** [`.github/workflows/digest.yml`](.github/workflows/digest.yml) —
  `cron: "0 6,14,22 * * *"` (06:00 / 14:00 / 22:00 UTC). Re-time with [crontab.guru](https://crontab.guru/).
- **Secrets:** add `ANTHROPIC_API_KEY`, `WEBSHARE_PROXY_USERNAME`, and
  `WEBSHARE_PROXY_PASSWORD` under **Settings → Secrets and variables → Actions**.
  The digest Issue uses the built-in `GITHUB_TOKEN` — no extra setup needed for that.

### Get notified on phone + computer
Install the **GitHub Mobile** app and sign in — you get a push notification whenever
the digest Issue opens, plus email/web on your computer. No extra credentials; it's
GitHub's own notification system.

---

## Run it once locally (optional)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # put your ANTHROPIC_API_KEY in .env
python scripts/run.py --dry-run --limit 1   # summarize 1 newest video; no commit/Issue/state
```

Inspect the printed brief, `digests/*.md`, and `data/archive/*`. Tests (no network/API):

```bash
pytest
```

---

## Good to know (limits)

- **No captions → no transcript.** Videos without captions are *not* transcribed
  (out of scope); the brief is still built from the description + any materials, and
  says the transcript was missing.
- **RSS shows ~15 latest videos per channel.** Daily runs make missing anything unlikely.
- **Only allowlisted documents are downloaded** (https-only, size-capped, content-type
  checked); everything else is listed, never fetched. Any transcript/download failure is
  skipped gracefully rather than crashing the run.

### Alternative: run on a self-hosted runner (no proxy needed)
If you'd rather not use a proxy, you can run the workflow on your own PC where your
home IP isn't blocked by YouTube. Install a GitHub Actions self-hosted runner on your
machine (see [GitHub docs](https://docs.github.com/en/actions/hosting-your-own-runners)),
then change `runs-on: ubuntu-latest` in `.github/workflows/digest.yml` to
`runs-on: self-hosted`. Your PC needs to be on around the scheduled time, but no proxy
is required and there's no monthly cost beyond electricity.
