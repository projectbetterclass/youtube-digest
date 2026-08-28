# YouTube Digest

Watch a list of YouTube channels and get a **daily brief** of every new video —
without watching them end to end. For each new upload the tool:

1. fetches the **transcript/captions** (no YouTube API key),
2. downloads **safe linked materials** (PDF / PPTX / SlideShare / Speaker Deck) and extracts their text — other links (GitHub, papers) are just listed,
3. **summarizes** transcript + materials into a short brief (key points, takeaway, notable materials, and a *skip / skim / watch* verdict) with the Claude API,
4. collects the briefs into a dated markdown **digest**, commits it, and opens a **GitHub Issue** so you get a push notification on phone + desktop.

It runs as a scheduled **GitHub Action on a self-hosted runner** — i.e. on your own
PC — so it uses your home IP (see [Why self-hosted](#why-self-hosted-your-own-pc)).

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

## Why self-hosted (your own PC)

YouTube **blocks transcript requests from cloud-provider IPs**, including GitHub's
hosted Actions runners (`RequestBlocked`) — so a normal cloud Action returns
description-only briefs. Your **home IP is not blocked**, so the job runs on a
**self-hosted runner** installed on your machine and transcripts come through.

**What that means day to day:**

- The daily run takes only **~1–2 minutes**; your PC just needs to be on briefly
  around the scheduled time — not all day.
- If the PC is off at the scheduled time, the run waits and executes once your PC is
  back on. Even if a day is missed entirely, the next run looks back `max_age_days`
  (default **3 days**), so nothing recent is lost.
- No monthly cost. The trade-off is only that the PC must be on sometime within a few
  days of an upload.

### The runner (one-time setup, already done)
The GitHub Actions runner is installed at `C:\actions-runner` and registered with the
repo. To make it start automatically at login, a hidden launcher lives in your Startup
folder (`ytdigest-runner.vbs`, which runs `C:\actions-runner\run.cmd`). Delete that
file to stop it auto-starting. For a run without being logged in, install the runner as
a Windows service instead (needs admin).

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

The daily schedule and secret live in the workflow:
- **Schedule:** [`.github/workflows/digest.yml`](.github/workflows/digest.yml) —
  `cron: "0 6 * * *"` (06:00 UTC). Re-time with [crontab.guru](https://crontab.guru/).
- **Secret:** add `ANTHROPIC_API_KEY` under **Settings → Secrets and variables →
  Actions**. That's the only secret needed — the digest Issue uses the built-in token.

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

### Alternative: run in the cloud with a proxy
If you'd rather run on GitHub's hosted runners (no PC required), route transcript
fetches through a **residential** proxy: set `WEBSHARE_PROXY_USERNAME` /
`WEBSHARE_PROXY_PASSWORD` (Webshare residential — datacenter proxies are also blocked)
as repo secrets, and change `runs-on: self-hosted` back to `ubuntu-latest`. The code
auto-detects the proxy env vars (or a generic `YTDIGEST_PROXY_HTTP_URL` /
`YTDIGEST_PROXY_HTTPS_URL`). This costs a few $/mo; transcripts are tiny so bandwidth
use is minimal.
