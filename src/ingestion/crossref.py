from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import html
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "day10-data-observability-lab/0.1 (educational; Crossref polite pool)"

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def strip_markup(value: Any) -> str:
    """Remove JATS/HTML tags (e.g. `<jats:p>`), unescape entities and collapse whitespace."""
    if value is None:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", str(value)))
    return normalize_whitespace(text)


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            text = strip_markup(item)
            if text:
                return text
        return ""
    return strip_markup(value)


def _format_date_parts(date_obj: Any) -> str:
    """Crossref dates look like {"date-parts": [[2026, 5, 20]]}; missing month/day default to 01."""
    if not isinstance(date_obj, dict):
        return ""
    parts_list = date_obj.get("date-parts") or []
    if parts_list and parts_list[0] and parts_list[0][0]:
        parts = [int(part) for part in parts_list[0] if part is not None]
        year, month, day = (parts + [1, 1])[:3]
        return f"{year:04d}-{month:02d}-{day:02d}"
    date_time = date_obj.get("date-time")
    if isinstance(date_time, str) and len(date_time) >= 10:
        return date_time[:10]
    return ""


def _published_date(item: dict[str, Any]) -> str:
    for key in ("published", "published-print", "published-online", "issued", "created"):
        value = _format_date_parts(item.get(key))
        if value:
            return value
    return ""


def _updated_date(item: dict[str, Any], published: str) -> str:
    for key in ("updated", "created", "deposited"):
        value = _format_date_parts(item.get(key))
        if value:
            return value
    return published


def _authors(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = normalize_whitespace(f"{author.get('given', '')} {author.get('family', '')}")
        name = name or normalize_whitespace(str(author.get("name", "")))
        if name:
            names.append(name)
    return names


def _categories(item: dict[str, Any]) -> list[str]:
    categories: list[str] = []
    for subject in item.get("subject") or []:
        text = strip_markup(subject)
        if text and text not in categories:
            categories.append(text)
    if not categories and item.get("type"):
        categories.append(strip_markup(item["type"]))
    return categories or ["Uncategorized"]


def _pdf_url(item: dict[str, Any], fallback: str) -> str:
    for link in item.get("link") or []:
        if isinstance(link, dict) and "pdf" in str(link.get("content-type", "")).lower() and link.get("URL"):
            return str(link["URL"])
    return fallback


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse a Crossref `/works` payload into `PaperRecord`s.

    Records without DOI, title, abstract or publication date cannot be answered
    by the agent, so they are skipped here instead of leaking downstream.
    """
    items = (payload.get("message") or {}).get("items") or []
    records: list[PaperRecord] = []
    for item in items:
        doi = normalize_whitespace(str(item.get("DOI") or ""))
        title = _first_text(item.get("title"))
        summary = strip_markup(item.get("abstract"))
        published = _published_date(item)
        if not doi or not title or not summary or not published:
            continue
        categories = _categories(item)
        abs_url = str(item.get("URL") or f"https://doi.org/{doi}")
        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=summary,
                authors=_authors(item),
                categories=categories,
                primary_category=categories[0],
                published=published,
                updated=_updated_date(item, published),
                abs_url=abs_url,
                pdf_url=_pdf_url(item, abs_url),
                comment=f"Crossref record {doi}",
            )
        )
    return records


def _request_crossref(settings: Settings) -> dict[str, Any]:
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }
    headers = {"User-Agent": USER_AGENT}
    last_error = "no attempt made"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                CROSSREF_WORKS_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            if response.status_code == 200:
                return response.json()
            last_error = f"HTTP {response.status_code}"
            if response.status_code not in RETRYABLE_STATUS_CODES:
                break
            retry_after = response.headers.get("Retry-After", "")
            if retry_after.isdigit() and attempt < MAX_ATTEMPTS:
                time.sleep(min(int(retry_after), 30))
                continue
        if attempt < MAX_ATTEMPTS:
            time.sleep(BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
    raise RuntimeError(f"Crossref API unavailable after {MAX_ATTEMPTS} attempts ({last_error}).")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Load source records and persist both raw artifacts.

    - Dev/offline mode (default): parse the local snapshot `data/raw/crossref_response.json`.
    - Live mode (`REFRESH_SOURCE=1`): call Crossref with retry/backoff for 429/5xx and
      overwrite the snapshot; on failure fall back to the snapshot when it exists.
    """
    snapshot_path = settings.paths.raw_api_response
    payload: dict[str, Any] | None = None

    if settings.refresh_source or not snapshot_path.exists():
        try:
            payload = _request_crossref(settings)
            write_json(snapshot_path, payload)
            print(f"[ingestion] Live Crossref fetch OK -> {snapshot_path.name}")
        except RuntimeError as exc:
            if not snapshot_path.exists():
                raise
            print(f"[ingestion] {exc} Falling back to local snapshot {snapshot_path.name}.")

    if payload is None:
        payload = read_json(snapshot_path)
        print(f"[ingestion] Offline mode: loaded snapshot {snapshot_path.name}")

    records = parse_crossref_payload(payload)
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Read `crossref_records.json` back into `PaperRecord`s, tolerating missing optional fields."""
    field_names = [field.name for field in fields(PaperRecord)]
    list_fields = {"authors", "categories"}
    records: list[PaperRecord] = []
    for row in read_json(path):
        values = {
            name: list(row.get(name) or []) if name in list_fields else str(row.get(name) or "")
            for name in field_names
        }
        records.append(PaperRecord(**values))
    return records
