"""Download safe linked documents (allowlist only) and extract their text.

Safety posture:
  * https-only, except a tiny trusted-host allowlist for plain http (enforced upstream
    in links.classify_url — e.g. Aswath Damodaran's NYU pages).
  * Size cap while streaming (never trust Content-Length alone).
  * Content-type must look like the expected document type.
  * Short timeouts; nothing is ever executed.
PDF/PPTX/Excel direct links and SlideShare/Speaker Deck pages are fetched. Everything
downloaded lives in memory (BytesIO) — no binaries are written to disk or committed.
"""

from __future__ import annotations

import io
import logging
import re
from typing import Optional

import requests

from .config import Settings
from .links import Link
from .models import Material

log = logging.getLogger(__name__)

_UA = {"User-Agent": "ytdigest/0.1 document fetcher"}
_SPEAKERDECK_PDF_RE = re.compile(
    r"https://files\.speakerdeck\.com/[^\s\"'<>]+\.pdf", re.IGNORECASE
)
# Generic .pdf link on a slide-host page (best-effort fallback).
_ANY_PDF_RE = re.compile(r"https://[^\s\"'<>]+\.pdf", re.IGNORECASE)


def _download(url: str, session: requests.Session, max_bytes: int, timeout: int = 30):
    """Stream a URL into memory with a hard size cap. Returns (bytes, content_type)."""
    with session.get(url, headers=_UA, timeout=timeout, stream=True, allow_redirects=True) as resp:
        resp.raise_for_status()
        ctype = (resp.headers.get("Content-Type") or "").lower()
        declared = resp.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise ValueError(f"file too large ({declared} bytes > {max_bytes})")
        buf = io.BytesIO()
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"file exceeded size cap of {max_bytes} bytes")
            buf.write(chunk)
        return buf.getvalue(), ctype


def _resolve_slide_pdf(url: str, category: str, session: requests.Session, timeout: int = 30) -> Optional[str]:
    """Best-effort: turn a SlideShare/Speaker Deck page URL into a downloadable PDF URL."""
    resp = session.get(url, headers=_UA, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    html = resp.text
    if category == "speakerdeck":
        m = _SPEAKERDECK_PDF_RE.search(html)
        if m:
            return m.group(0)
    m = _ANY_PDF_RE.search(html)
    return m.group(0) if m else None


def _extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 — skip unextractable pages
            continue
    return "\n".join(p.strip() for p in pages if p.strip()).strip()


def _extract_pptx_text(data: bytes) -> str:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    blocks = []
    for i, slide in enumerate(prs.slides, start=1):
        lines = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    txt = "".join(run.text for run in para.runs).strip()
                    if txt:
                        lines.append(txt)
        if lines:
            blocks.append(f"Slide {i}:\n" + "\n".join(lines))
    return "\n\n".join(blocks).strip()


def _extract_xlsx_text(data: bytes, max_cells_per_sheet: int = 5000) -> str:
    """Dump non-empty cell values from an .xlsx/.xlsm workbook, sheet by sheet.

    Uses computed values (data_only) so numbers come through rather than formula
    strings. Legacy .xls (binary BIFF) isn't handled here — the raw file is what a
    valuation project wants anyway; this text is just for search/'ask your library'.
    """
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks = []
    for ws in wb.worksheets:
        rows = []
        cells = 0
        for row in ws.iter_rows(values_only=True):
            vals = [str(c) for c in row if c is not None and str(c).strip()]
            cells += len(vals)
            if vals:
                rows.append(" | ".join(vals))
            if cells >= max_cells_per_sheet:
                rows.append("[sheet truncated]")
                break
        if rows:
            blocks.append(f"Sheet: {ws.title}\n" + "\n".join(rows))
    wb.close()
    return "\n\n".join(blocks).strip()


def fetch_material(link: Link, settings: Settings, session: requests.Session) -> Material:
    """Download one allowlisted link and extract its text. Never raises — errors go in Material.error."""
    mat = Material(url=link.url, category=link.category)
    try:
        download_url = link.url
        if link.category in ("slideshare", "speakerdeck"):
            resolved = _resolve_slide_pdf(link.url, link.category, session)
            if not resolved:
                mat.error = "could not resolve a downloadable PDF from the slide page"
                return mat
            download_url = resolved

        data, ctype = _download(download_url, session, settings.max_download_bytes)
        mat.filename = download_url.rsplit("/", 1)[-1][:120]

        low = download_url.lower()
        is_pptx = link.category == "pptx" or low.endswith(".pptx")
        is_excel = link.category == "excel" or low.endswith((".xlsx", ".xlsm", ".xls"))
        if is_pptx:
            if not ("presentationml" in ctype or "octet-stream" in ctype or low.endswith(".pptx")):
                mat.error = f"unexpected content-type for pptx: {ctype!r}"
                return mat
            text = _extract_pptx_text(data)
        elif is_excel:
            if not ("spreadsheet" in ctype or "excel" in ctype or "octet-stream" in ctype
                    or low.endswith((".xlsx", ".xlsm", ".xls"))):
                mat.error = f"unexpected content-type for excel: {ctype!r}"
                return mat
            if low.endswith(".xls"):
                # Legacy binary .xls: no text extractor wired in; the raw file is the
                # deliverable. Record a marker so it isn't retried as "no text".
                mat.text = f"[legacy .xls workbook: {mat.filename} — see raw file]"
                return mat
            text = _extract_xlsx_text(data)
        else:
            if not ("pdf" in ctype or "octet-stream" in ctype or low.endswith(".pdf")):
                mat.error = f"unexpected content-type for pdf: {ctype!r}"
                return mat
            text = _extract_pdf_text(data)

        if not text:
            mat.error = "no extractable text"
            return mat
        mat.text = text[: settings.max_material_chars]
    except Exception as exc:  # noqa: BLE001 — any failure is non-fatal for the run
        mat.error = f"{type(exc).__name__}: {exc}"
        log.warning("Material fetch failed for %s (%s)", link.url, mat.error)
    return mat


def gather_materials(links: list[Link], settings: Settings, session: Optional[requests.Session] = None) -> list[Material]:
    sess = session or requests.Session()
    return [fetch_material(link, settings, sess) for link in links if link.kind == "download"]
