# YouTube Digest

Watch a list of YouTube channels and get a **daily brief** of every new video —
without watching them end to end. For each new upload the tool:

1. fetches the **transcript/captions** (no YouTube API key),
2. downloads **safe linked materials** (PDF / PPTX / SlideShare / Speaker Deck) and extracts their text — other links (GitHub, papers) are just listed,
3. **summarizes** transcript + materials into a short brief (key points, takeaway, notable materials, and a *skip / skim / watch* verdict) with the Claude API,
4. collects the briefs into a dated markdown **digest**, commits it, and opens a **GitHub Issue** so you get a push notification on phone + desktop.

It runs itself daily as a **GitHub Action** — nothing has to stay switched on.

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

## Quick start (run it once locally)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your ANTHROPIC_API_KEY in .env
```

Add channels to `config/watchlist.yml`. To get a channel's `channel_id`:

```bash
python scripts/resolve_channel.py https://www.youtube.com/@3blue1brown
```

Then do a dry run on the single newest new video (no commit, no Issue, no state change):

```bash
python scripts/run.py --dry-run --limit 1
```

Inspect the printed brief, `digests/*.md`, and `data/archive/*`. Run it again
**without** `--dry-run` and it records state; a second real run finds "no new videos".

Run the tests (no network/API needed):

```bash
pytest
```

---

## Deploy on GitHub (daily, in the cloud)

1. Push this repo to GitHub.
2. **Settings → Secrets and variables → Actions → New repository secret**, add:
   - `ANTHROPIC_API_KEY` — your Claude API key.
   - `WEBSHARE_PROXY_USERNAME` + `WEBSHARE_PROXY_PASSWORD` — residential proxy creds
     (see [Transcripts on the cloud](#transcripts-on-the-cloud-residential-proxy) below).
   (Delivery itself needs no secret — it uses the built-in token.)
3. **Actions tab → Daily YouTube Digest → Run workflow** to trigger it once by hand.
   Confirm a digest is committed and an Issue is opened.
4. After that it runs automatically on the schedule in
   [`.github/workflows/digest.yml`](.github/workflows/digest.yml) (06:00 UTC daily;
   change the `cron` line to re-time it).

### Get notified on phone + computer
Install the **GitHub Mobile** app and sign in — you'll get a push notification
whenever the digest Issue is opened, plus email/web notifications on your computer.
No credentials are stored anywhere for this; it's GitHub's own notification system.

---

## Configuration (`config/watchlist.yml`)

```yaml
settings:
  model: claude-haiku-4-5     # cheap + fast; use claude-sonnet-5 for richer briefs
  max_age_days: 3             # ignore uploads older than this (first-run backfill guard)
  transcript_languages: [en]
  request_delay_seconds: 1.0  # spacing between channel feed fetches
  max_videos_per_run: 50      # cost guard
channels:
  - name: 3Blue1Brown
    channel_id: UCYO_jab_esuFRV4b17AJtAw
```

---

## Transcripts on the cloud (residential proxy)

YouTube **blocks transcript requests from cloud-provider IPs**, including GitHub
Actions runners (`RequestBlocked`). It works from your home IP but not from the
runner, so the cloud job needs a **residential proxy**:

1. Create a **[Webshare](https://www.webshare.io/)** account and buy their
   **Residential** proxy (their datacenter proxies are also blocked by YouTube —
   it must be *residential*). Transcripts are tiny text, so bandwidth use is minimal.
2. From the Webshare dashboard, copy your **Proxy username** and **Proxy password**.
3. Add them as the `WEBSHARE_PROXY_USERNAME` / `WEBSHARE_PROXY_PASSWORD` repo secrets.

The code auto-detects those env vars and routes transcript fetches through the proxy
(`youtube-transcript-api` supports Webshare natively). With no proxy set it runs
proxy-free — fine locally, blocked on the cloud. Any generic HTTP/HTTPS proxy works
too via `YTDIGEST_PROXY_HTTP_URL` / `YTDIGEST_PROXY_HTTPS_URL`.

## Good to know (limits)

- **No captions → no transcript.** Videos without captions are *not* transcribed
  (out of scope); the brief is still built from the description + any materials, and
  says the transcript was missing.
- **Cloud IPs are blocked** for transcripts — see the residential-proxy section above.
  Any transcript failure is skipped gracefully rather than crashing the run.
- **RSS shows ~15 latest videos per channel.** Daily runs make missing anything unlikely.
- **Only allowlisted documents are downloaded** (https-only, size-capped, content-type
  checked); everything else is listed, never fetched.
