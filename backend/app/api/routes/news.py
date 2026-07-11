"""News routes -- filesystem-only proxy for report-generating cron output.

Reads/deletes the markdown report archive written by report-generating
Hermes cron scripts (currently just ai-news-noon's run_ai_news.py, which
writes one dated file per run to `<profile>/reports/*.md` in addition to
its Telegram delivery) to each profile's `reports/` dir. No DB table backs
this -- same filesystem-only proxy pattern as foundation.py/
system_control.py/hindsight.py, since the content already lives on disk
and a DB copy would just be a second, driftable source of truth. See
CLAUDE.md's domain list for why these three (now four) routers skip the
usual db/models + api/schemas + api/routes triplet.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/news", tags=["news"])

PROFILES_DIR = Path("/profiles")
PREVIEW_MAX_CHARS = 280
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


class NewsReportOut(BaseModel):
    profile: str
    filename: str
    title: str
    date: str | None = None  # YYYY-MM-DD parsed from the filename, if any
    modified_at: str
    size_bytes: int
    article_count: int
    preview: str


class NewsReportListOut(BaseModel):
    reports: list[NewsReportOut]


class NewsReportContentOut(BaseModel):
    profile: str
    filename: str
    title: str
    content: str
    modified_at: str


class NewsDeleteOut(BaseModel):
    deleted: int


def _report_dirs() -> list[tuple[str, Path]]:
    """Every profile's reports/ dir that exists, as (profile, dir) pairs."""
    dirs: list[tuple[str, Path]] = []
    if not PROFILES_DIR.is_dir():
        return dirs
    for profile_dir in sorted(PROFILES_DIR.iterdir()):
        reports_dir = profile_dir / "reports"
        if reports_dir.is_dir():
            dirs.append((profile_dir.name, reports_dir))
    return dirs


def _safe_report_path(profile: str, filename: str) -> Path:
    """Resolve (profile, filename) to a real file strictly inside that
    profile's reports/ dir -- rejects path traversal / escapes."""
    if "/" in profile or "/" in filename or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid profile or filename")
    reports_dir = (PROFILES_DIR / profile / "reports").resolve()
    path = (reports_dir / filename).resolve()
    if path.parent != reports_dir:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return path


def _title_from_content(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def _preview_from_content(text: str) -> str:
    # run_ai_news.py's format nests each article under a "### " heading
    # (see the module docstring's sample) -- those headings make a far more
    # readable grid preview than the raw "- **Fonte:** ..." bullet noise
    # underneath them. Falls back to the first non-heading paragraph for
    # any other report shape that doesn't use "### " sections.
    titles = [line.strip()[4:].strip() for line in text.splitlines() if line.strip().startswith("### ")]
    if titles:
        return " · ".join(titles)[:PREVIEW_MAX_CHARS]

    body_chars: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(("Gerado em:", "Janela usada:")):
            continue
        if body_chars:
            body_chars.append(" ")
        body_chars.append(stripped)
        if sum(len(c) for c in body_chars) >= PREVIEW_MAX_CHARS:
            break
    return "".join(body_chars)[:PREVIEW_MAX_CHARS]


def _report_to_out(profile: str, path: Path) -> NewsReportOut | None:
    try:
        stat = path.stat()
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    date_match = _DATE_RE.search(path.stem)
    return NewsReportOut(
        profile=profile,
        filename=path.name,
        title=_title_from_content(text, path.stem),
        date=date_match.group(1) if date_match else None,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        size_bytes=stat.st_size,
        article_count=text.count("\n### "),
        preview=_preview_from_content(text),
    )


@router.get("", response_model=NewsReportListOut)
async def list_news_reports() -> NewsReportListOut:
    """List every report markdown file across every profile's reports/
    dir, newest first. Backs the News page's grid."""
    reports: list[NewsReportOut] = []
    for profile, reports_dir in _report_dirs():
        for path in reports_dir.glob("*.md"):
            out = _report_to_out(profile, path)
            if out is not None:
                reports.append(out)
    reports.sort(key=lambda r: r.modified_at, reverse=True)
    return NewsReportListOut(reports=reports)


@router.get("/{profile}/{filename}", response_model=NewsReportContentOut)
async def get_news_report(profile: str, filename: str) -> NewsReportContentOut:
    """Full markdown content of a single report, for the view dialog."""
    path = _safe_report_path(profile, filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    text = path.read_text(encoding="utf-8", errors="replace")
    stat = path.stat()
    return NewsReportContentOut(
        profile=profile,
        filename=filename,
        title=_title_from_content(text, path.stem),
        content=text,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    )


@router.delete("/{profile}/{filename}", response_model=NewsDeleteOut)
async def delete_news_report(profile: str, filename: str) -> NewsDeleteOut:
    """Delete a single report file."""
    path = _safe_report_path(profile, filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    path.unlink()
    return NewsDeleteOut(deleted=1)


@router.delete("", response_model=NewsDeleteOut)
async def delete_all_news_reports() -> NewsDeleteOut:
    """Delete every report across every profile. Backs the "Delete all"
    action on the News page."""
    deleted = 0
    for _profile, reports_dir in _report_dirs():
        for path in reports_dir.glob("*.md"):
            try:
                path.unlink()
                deleted += 1
            except OSError:
                continue
    return NewsDeleteOut(deleted=deleted)
