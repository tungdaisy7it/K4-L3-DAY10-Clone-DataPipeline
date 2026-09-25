from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import shutil

import pytest

from core.config import Settings, load_settings
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import load_raw_records

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
RUN_DATE = datetime(2026, 8, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    """Tests never call paid LLMs or the live Crossref API."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MODEL", "mock")
    for name in ("REFRESH_SOURCE", "REFRESH_TEST_SET", "RUN_RAGAS"):
        monkeypatch.delenv(name, raising=False)


def make_project(root: Path) -> Settings:
    (root / "data" / "raw").mkdir(parents=True)
    for name in ("crossref_response.json", "crossref_records.json"):
        shutil.copy(RAW_DIR / name, root / "data" / "raw" / name)
    return load_settings(project_dir=root)


@pytest.fixture
def settings(tmp_path, offline_env) -> Settings:
    return make_project(tmp_path / "project")


@pytest.fixture
def clean_df(settings):
    return build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), RUN_DATE)
