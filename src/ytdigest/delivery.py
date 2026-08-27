"""Deliver the digest as a GitHub Issue (native phone + desktop notifications).

Uses the Action-provided GITHUB_TOKEN and GITHUB_REPOSITORY env vars. On a local
run (no token) this is a no-op, so `scripts/run.py` never needs a real token.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests

log = logging.getLogger(__name__)

_API = "https://api.github.com"
# GitHub Issue bodies are capped at 65536 chars; leave headroom for a footer.
_MAX_BODY = 60000


def deliver_github_issue(title: str, body: str, digest_path: str = "") -> Optional[str]:
    """Create a labelled Issue with the digest. Returns the issue URL, or None if skipped."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        log.info("No GITHUB_TOKEN/GITHUB_REPOSITORY — skipping Issue delivery (local run).")
        return None

    if len(body) > _MAX_BODY:
        footer = f"\n\n… _truncated; full digest committed at `{digest_path}`._"
        body = body[: _MAX_BODY - len(footer)] + footer

    resp = requests.post(
        f"{_API}/repos/{repo}/issues",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"title": title, "body": body, "labels": ["digest"]},
        timeout=30,
    )
    resp.raise_for_status()
    url = resp.json().get("html_url")
    log.info("Opened digest issue: %s", url)
    return url
