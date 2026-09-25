from __future__ import annotations

from dataclasses import replace

import pandas as pd

from core.utils import read_json
from ingestion.cleaning import CLEAN_COLUMNS, build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import PaperRecord

from conftest import RUN_DATE


def _record(**overrides) -> PaperRecord:
    base = PaperRecord(
        paper_id="10.1/A",
        title="A Title",
        summary="<jats:p>Some   summary text that is long enough.</jats:p>",
        authors=["Ada  Lovelace", "Ada Lovelace", ""],
        categories=["AI"],
        primary_category="AI",
        published="2026-07-01",
        updated="2026-07-01",
        abs_url="u",
        pdf_url="u",
        comment="c",
    )
    return replace(base, **overrides)


def test_clean_snapshot_shape(clean_df):
    assert len(clean_df) == 24
    assert list(clean_df.columns) == CLEAN_COLUMNS
    assert clean_df["paper_id"].is_unique
    assert clean_df["published"].is_monotonic_decreasing
    first = clean_df.iloc[0]
    assert first["text_for_embedding"].splitlines()[0] == f"Title: {first['title']}"
    assert [line.split(":")[0] for line in first["text_for_embedding"].splitlines()] == [
        "Title", "Authors", "Published", "Categories", "Summary",
    ]
    assert first["age_days"] == (pd.Timestamp(RUN_DATE).normalize() - pd.Timestamp(first["published"], tz="UTC")).days


def test_clean_dedup_normalize_and_filter():
    records = [
        _record(paper_id="10.1/A", updated="2026-07-01", title="Old version"),
        _record(paper_id="10.1/a", updated="2026-07-05", title="New version"),
        _record(paper_id="10.1/B", summary="   "),
        _record(paper_id="10.1/C", published="not-a-date"),
        _record(paper_id="10.1/D", title="<b>Tagged</b>   title"),
    ]
    df = build_clean_dataframe(records, RUN_DATE)
    assert sorted(df["paper_id"]) == ["10.1/a", "10.1/d"]
    assert df.set_index("paper_id").loc["10.1/a", "title"] == "New version"
    assert df.set_index("paper_id").loc["10.1/d", "title"] == "Tagged title"
    assert df.iloc[0]["authors"] == ["Ada Lovelace"]
    assert df.iloc[0]["summary"] == "Some summary text that is long enough."
    assert df.iloc[0]["age_days"] == 31


def test_clean_empty_input():
    assert list(build_clean_dataframe([], RUN_DATE).columns) == CLEAN_COLUMNS


def test_clean_invalid_updated_falls_back_to_published_and_is_deterministic():
    records = [
        _record(paper_id="10.1/B", published="2026-06-01", updated="not-a-date"),
        _record(paper_id="10.1/A", published="2026-07-01", updated=""),
    ]
    first = build_clean_dataframe(records, RUN_DATE.replace(tzinfo=None))
    second = build_clean_dataframe(records, RUN_DATE.replace(tzinfo=None))
    assert first["paper_id"].tolist() == ["10.1/a", "10.1/b"]
    assert first.set_index("paper_id").loc["10.1/b", "updated"] == "2026-06-01"
    pd.testing.assert_frame_equal(first, second)


def test_corruption_applies_six_logged_scenarios(clean_df, tmp_path):
    log_path = tmp_path / "corruption_log.json"
    corrupted = corrupt_clean_dataframe(clean_df, log_path)
    log = read_json(log_path)
    types = [item["type"] for item in log["corruptions"]]
    assert types == [
        "drop_latest_records", "blank_summary", "inject_noise", "truncate_title", "stale_date", "duplicate_rows",
    ]
    assert log["input_rows"] == 24 and log["output_rows"] == len(corrupted) == 24 - 5 + 3

    by_type = {item["type"]: item for item in log["corruptions"]}
    newest = clean_df.head(5)["paper_id"].tolist()
    assert by_type["drop_latest_records"]["affected_paper_ids"] == newest
    assert not set(newest) & set(corrupted["paper_id"])
    assert (corrupted["summary"] == "").sum() >= 3
    assert (corrupted["title"].str.len() < 8).sum() >= 3
    assert corrupted["paper_id"].duplicated().sum() == 3
    assert corrupted["summary"].str.contains("#@!%|&&\\*\\*|\\$\\$%%|~\\^\\^~|<\\?!>|�|Ã").any()
    stale_id = by_type["stale_date"]["affected_paper_ids"][0]
    old = clean_df.set_index("paper_id").loc[stale_id]
    new = corrupted[corrupted["paper_id"] == stale_id].iloc[0]
    assert new["age_days"] == old["age_days"] + 365
    assert f"Published: {new['published']}" in new["text_for_embedding"]


def test_corruption_is_deterministic(clean_df, tmp_path):
    first = corrupt_clean_dataframe(clean_df, tmp_path / "a.json")
    second = corrupt_clean_dataframe(clean_df, tmp_path / "b.json")
    pd.testing.assert_frame_equal(first, second)
