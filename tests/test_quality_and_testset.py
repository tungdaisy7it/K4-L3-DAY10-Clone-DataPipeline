from __future__ import annotations

import pytest

from core.utils import read_json
from evaluation.testset import QUESTION_TYPES, build_test_set
from ingestion.corruption import corrupt_clean_dataframe
from observability.quality import build_freshness_report, run_data_quality_checks


def test_quality_gate_passes_on_clean_data(settings, clean_df):
    report = run_data_quality_checks(clean_df, settings, "baseline")
    assert report["success"] is True and report["failed_checks"] == []
    assert "great_expectations 1." in report["engine"]
    types = {item["expectation"] for item in report["expectations"]}
    assert {
        "expect_table_row_count_to_be_between",
        "expect_column_values_to_not_be_null",
        "expect_column_values_to_be_unique",
        "expect_column_value_lengths_to_be_between",
    } <= types
    assert report["source_reconciliation"]["coverage"] == 1.0
    assert read_json(settings.paths.baseline_quality_report)["success"] is True


def test_quality_gate_detects_every_corruption(settings, clean_df, tmp_path):
    corrupted = corrupt_clean_dataframe(clean_df, tmp_path / "log.json")
    report = run_data_quality_checks(corrupted, settings, "corrupted")
    assert report["success"] is False
    assert set(report["failed_checks"]) >= {
        "expect_column_values_to_be_unique(paper_id)",
        "expect_column_value_lengths_to_be_between(summary)",
        "expect_column_value_lengths_to_be_between(title)",
        "expect_column_values_to_not_match_regex(summary)",
        "source_reconciliation",
    }
    assert report["source_reconciliation"]["missing_count"] == 5
    freshness = build_freshness_report(corrupted, settings, tmp_path / "fresh.json")
    assert freshness["is_fresh"] is False and "refresh the source" in freshness["alert"]
    assert settings.paths.corrupted_quality_report.exists()


def test_freshness_report_on_clean_data(settings, clean_df):
    report = build_freshness_report(clean_df, settings, settings.paths.freshness_report)
    assert report["is_fresh"] is True and report["alert"] is None
    assert report["total_rows"] == 24
    assert sum(report["age_distribution"].values()) == 24
    assert report["latest_published"] == clean_df["published"].max()


def test_quality_custom_report_name_and_missing_raw(settings, clean_df):
    settings.paths.raw_records_json.unlink()
    report = run_data_quality_checks(clean_df, settings, "test")
    assert "skipped" in report["source_reconciliation"]
    assert (settings.paths.quality_dir / "test_quality_report.json").exists()


def test_build_test_set(settings, clean_df):
    test_set = build_test_set(clean_df, settings.paths.eval_testset)
    assert len(test_set) == 10
    assert {item["question_type"] for item in test_set} == set(QUESTION_TYPES)
    assert len({item["id"] for item in test_set}) == 10
    ids = set(clean_df["paper_id"])
    for item in test_set:
        assert item["ground_truth"]
        assert set(item["ground_truth_doc_ids"]) <= ids
    assert read_json(settings.paths.eval_testset) == test_set


def test_build_test_set_requires_enough_documents(settings, clean_df):
    small = clean_df.head(3).copy()
    with pytest.raises(ValueError):
        build_test_set(small, settings.paths.eval_testset)
    apostrophes = clean_df.head(5).copy()
    apostrophes.loc[apostrophes.index[0], "title"] = "It's a title"
    assert all("It's" not in q["question"] for q in build_test_set(apostrophes, settings.paths.eval_testset))


def test_build_test_set_validates_required_schema(settings, clean_df):
    with pytest.raises(ValueError, match="missing required columns: categories_joined"):
        build_test_set(clean_df.drop(columns="categories_joined"), settings.paths.eval_testset)


def test_build_test_set_skips_empty_ground_truth_and_is_deterministic(settings, clean_df):
    incomplete = clean_df.copy()
    incomplete.loc[incomplete.index[1], "authors_joined"] = ""
    incomplete.loc[incomplete.index[3], "categories_joined"] = ""
    incomplete.loc[incomplete.index[5], "summary"] = ""
    first = build_test_set(incomplete, settings.paths.eval_testset)
    second = build_test_set(incomplete, settings.paths.eval_testset)
    assert first == second
    assert len({item["ground_truth_doc_ids"][0] for item in first}) == len(first)
    assert all(item["ground_truth"].strip() for item in first)
