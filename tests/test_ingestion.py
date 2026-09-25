from __future__ import annotations

from dataclasses import asdict, replace

import pytest
import requests

from core.utils import read_json, write_json
from ingestion import crossref
from ingestion.crossref import fetch_source_records, load_raw_records, parse_crossref_payload


class FakeResponse:
    def __init__(self, status_code: int, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_parse_snapshot_reproduces_committed_records(settings):
    records = parse_crossref_payload(read_json(settings.paths.raw_api_response))
    assert len(records) == 24
    assert [asdict(r) for r in records] == read_json(settings.paths.raw_records_json)
    assert all("<jats" not in r.summary for r in records)


def test_parse_handles_markup_missing_fields_and_fallbacks():
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1/A",
                    "title": ["  A   <i>Good</i> Title  "],
                    "abstract": "<jats:p>Abstract &amp; more   text.</jats:p>",
                    "author": [{"given": "Ada", "family": "Lovelace"}, {"name": "ACM Consortium"}, "bad"],
                    "type": "journal-article",
                    "issued": {"date-parts": [[2026]]},
                    "created": {"date-time": "2026-02-03T00:00:00Z"},
                    "link": [{"content-type": "application/pdf", "URL": "https://x/pdf"}],
                },
                {"DOI": "10.1/missing-abstract", "title": ["T"], "published": {"date-parts": [[2026, 1, 1]]}},
                {"title": ["No DOI"], "abstract": "x", "published": {"date-parts": [[2026, 1, 1]]}},
                {"DOI": "10.1/no-date", "title": ["T"], "abstract": "x"},
            ]
        }
    }
    records = parse_crossref_payload(payload)
    assert len(records) == 1
    record = records[0]
    assert record.title == "A Good Title"
    assert record.summary == "Abstract & more text."
    assert record.authors == ["Ada Lovelace", "ACM Consortium"]
    assert record.categories == ["journal-article"]
    assert record.published == "2026-01-01"
    assert record.updated == "2026-02-03"
    assert record.abs_url == "https://doi.org/10.1/A"
    assert record.pdf_url == "https://x/pdf"
    assert parse_crossref_payload({}) == []


def test_fetch_offline_uses_snapshot(settings):
    settings.paths.raw_records_json.unlink()
    records = fetch_source_records(settings)
    assert len(records) == 24
    assert len(read_json(settings.paths.raw_records_json)) == 24


def test_fetch_live_retries_on_429_then_saves_raw(settings, monkeypatch):
    payload = read_json(settings.paths.raw_api_response)
    payload["message"]["items"] = payload["message"]["items"][:3]
    responses = [FakeResponse(429, headers={"Retry-After": "1"}), FakeResponse(503), FakeResponse(200, payload)]
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append(params)
        return responses.pop(0)

    monkeypatch.setattr(crossref.requests, "get", fake_get)
    monkeypatch.setattr(crossref.time, "sleep", lambda _: None)
    records = fetch_source_records(replace(settings, refresh_source=True))
    assert len(calls) == 3
    assert calls[0]["rows"] == settings.max_results and "has-abstract:true" in calls[0]["filter"]
    assert len(records) == 3
    assert len(read_json(settings.paths.raw_api_response)["message"]["items"]) == 3


def test_fetch_live_falls_back_to_snapshot_when_offline(settings, monkeypatch):
    def boom(*args, **kwargs):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(crossref.requests, "get", boom)
    monkeypatch.setattr(crossref.time, "sleep", lambda _: None)
    assert len(fetch_source_records(replace(settings, refresh_source=True))) == 24


def test_fetch_live_without_snapshot_raises(settings, monkeypatch):
    settings.paths.raw_api_response.unlink()
    monkeypatch.setattr(crossref.requests, "get", lambda *a, **k: FakeResponse(400))
    with pytest.raises(RuntimeError, match="HTTP 400"):
        fetch_source_records(settings)


def test_load_raw_records_tolerates_missing_fields(tmp_path):
    path = tmp_path / "records.json"
    write_json(path, [{"paper_id": "10.1/x", "title": "Title", "authors": None}])
    record = load_raw_records(path)[0]
    assert record.paper_id == "10.1/x"
    assert record.authors == [] and record.summary == ""
