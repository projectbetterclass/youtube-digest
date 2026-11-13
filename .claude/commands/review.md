---
description: Grounded review — read the pipeline and run pytest before any remark
---
A review here READS the code and RUNS the tests before saying anything. No speculation.

## 0. Orient
- Read `CLAUDE.md` "Project state" for how the daily job runs, and the "stay critical / cite every
  claim / never financial advice" rules — those ARE the output spec.
- The daily job commits `data/` and `digests/`; `git pull` before editing.

## 1. Scope
From `$ARGUMENTS`, or ask: a module (`src/ytdigest/pipeline.py`, `summarize.py`, `visuals.py`,
`feeds`, `links`, backfill), the current diff / a PR, or a handed-off finding. State it in one line.

## 2. Read the actual code — never guess
Open the files in scope under `src/ytdigest/` and read them. Cite `path:line`. No claim you haven't
read the code for.

## 3. Run the tests — a review isn't done until they're green
`pytest` (the tests need no network or API key). Anything red is a real finding. If your change
touches visuals, `pytest tests/test_visuals.py` (9 tests, no cv2/network).

## 4. Judge against THIS project's contract (not generic style)
- **Summaries are grounded in the source** — a brief and its skip / skim / watch verdict come from
  the transcript + extracted materials, never invented, and claims are cited to the source video.
- **Stay critical, not a parrot** — distinguish certainty from opinion/prediction; surface risks the
  creator skipped; **never financial advice** (never tell the user what to buy / sell / do).
- **Safe linked materials only** — PDF / PPTX / SlideShare / Speaker Deck are extracted; other links
  are just listed, never fetched or executed. Confirm `links` keeps that boundary.
- **Secrets stay secret** — `ANTHROPIC_API_KEY` + Webshare creds come from env / CI secrets, never
  committed; YouTube traffic goes through the proxy.
- **No cross-writer conflicts** — the digest and the visuals job keep separate ledgers
  (`data/state.json` vs `data/visuals_state.json`) and write different files.

## 5. Report — grounded, specific, falsifiable
Each finding: `path:line`, one concrete sentence, and the check that proves it (a test, a command,
an input). Most-serious first; one-line verdict. Never claim something passes you didn't run.

## 6. Handed-off finding
Judging one claim: does the code address it — yes / partly / no — grounded in what you read/ran,
citing `path:line`.
