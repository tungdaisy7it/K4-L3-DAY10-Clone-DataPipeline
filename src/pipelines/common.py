from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from core.utils import ensure_parent, write_csv

CONTENT_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "published",
    "updated",
    "text_for_embedding",
]


def save_dataframe(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    write_csv(df, csv_path)
    ensure_parent(json_path)
    df.to_json(json_path, orient="records", indent=2, force_ascii=False)


def load_dataframe(json_path: Path) -> pd.DataFrame:
    return pd.read_json(json_path, orient="records", dtype={"paper_id": str, "published": str, "updated": str})


def dataframe_fingerprint(df: pd.DataFrame) -> str:
    """Content hash that ignores row order and run-date dependent columns such as `age_days`."""
    payload = df[CONTENT_COLUMNS].sort_values(["paper_id", "title"]).to_json(orient="records", force_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
