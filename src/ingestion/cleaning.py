from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord, strip_markup

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "age_days",
    "abs_url",
    "pdf_url",
    "comment",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "text_for_embedding",
]


def compose_text_for_embedding(title: str, authors_joined: str, published: str, categories_joined: str, summary: str) -> str:
    return (
        f"Title: {title}\n"
        f"Authors: {authors_joined}\n"
        f"Published: {published}\n"
        f"Categories: {categories_joined}\n"
        f"Summary: {summary}"
    )


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """(Re)build helper columns from the base fields. Shared by cleaning and corruption."""
    out = df.copy()
    out["authors_joined"] = out["authors"].apply(lambda items: compact_join(list(items)))
    out["categories_joined"] = out["categories"].apply(lambda items: compact_join(list(items)))
    out["summary_chars"] = out["summary"].str.len().astype(int)
    out["text_for_embedding"] = [
        compose_text_for_embedding(row.title, row.authors_joined, row.published, row.categories_joined, row.summary)
        for row in out.itertuples(index=False)
    ]
    return out


def _clean_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        text = strip_markup(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _to_utc_date(value) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce", utc=True)


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Turn raw records into an embedding-ready dataframe.

    Rules: strip markup/whitespace, lowercase DOI as the stable `paper_id`, drop rows
    without id/title/summary or with an unparseable publication date, compute
    `age_days = run_date - published`, deduplicate by `paper_id` (keep the most
    recently updated version), then sort newest first.
    """
    rows = []
    for record in records:
        row = asdict(record)
        row["paper_id"] = normalize_whitespace(row["paper_id"]).lower()
        row["title"] = strip_markup(row["title"])
        row["summary"] = strip_markup(row["summary"])
        row["authors"] = _clean_list(row["authors"])
        row["categories"] = _clean_list(row["categories"])
        row["primary_category"] = strip_markup(row["primary_category"]) or (row["categories"] or [""])[0]
        row["comment"] = strip_markup(row["comment"])
        rows.append(row)

    df = pd.DataFrame(rows, columns=[column for column in CLEAN_COLUMNS if column in PaperRecord.__annotations__])
    if df.empty:
        return pd.DataFrame(columns=CLEAN_COLUMNS)

    published_ts = df["published"].map(_to_utc_date)
    updated_ts = df["updated"].map(_to_utc_date).fillna(published_ts)
    valid = (
        df["paper_id"].str.len().gt(0)
        & df["title"].str.len().gt(0)
        & df["summary"].str.len().gt(0)
        & published_ts.notna()
    )
    df = df[valid].copy()
    published_ts = published_ts[valid]
    updated_ts = updated_ts[valid]

    run_day = _to_utc_date(run_date).normalize()
    df["published"] = published_ts.dt.strftime("%Y-%m-%d")
    df["updated"] = updated_ts.dt.strftime("%Y-%m-%d")
    df["age_days"] = (run_day - published_ts.dt.normalize()).dt.days.astype(int)
    df["_updated_ts"] = updated_ts

    df = (
        df.sort_values(["paper_id", "_updated_ts"], ascending=[True, False])
        .drop_duplicates(subset="paper_id", keep="first")
        .drop(columns="_updated_ts")
    )
    df = add_derived_columns(df)
    df = df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    return df[CLEAN_COLUMNS]
