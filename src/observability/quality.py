from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json

os.environ.setdefault("GX_ANALYTICS_ENABLED", "False")

import great_expectations as gx  # noqa: E402

logging.getLogger("great_expectations").setLevel(logging.ERROR)

MIN_ROWS = 5
MAX_ROWS = 5000
MIN_SUMMARY_CHARS = 30
MIN_TITLE_CHARS = 8
MAX_STALE_RATIO = 0.25
MIN_SOURCE_COVERAGE = 0.95
REQUIRED_COLUMNS = ["paper_id", "title", "summary", "published", "text_for_embedding"]
NOISE_REGEX = r"[#@!%&*~^$<>?]{2,}|�|Ã"
DATE_REGEX = r"^\d{4}-\d{2}-\d{2}$"


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _quality_report_path(settings: Settings, report_name: str) -> Path:
    if report_name == "baseline":
        return settings.paths.baseline_quality_report
    if report_name == "corrupted":
        return settings.paths.corrupted_quality_report
    return settings.paths.quality_dir / f"{report_name}_quality_report.json"


def _build_suite(report_name: str) -> gx.ExpectationSuite:
    suite = gx.ExpectationSuite(name=f"papers_quality_{report_name}")
    suite.add_expectation(gx.expectations.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS))
    for column in REQUIRED_COLUMNS:
        suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column=column))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToBeUnique(column="paper_id"))
    suite.add_expectation(
        gx.expectations.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=MIN_SUMMARY_CHARS)
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValueLengthsToBeBetween(column="title", min_value=MIN_TITLE_CHARS)
    )
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotMatchRegex(column="summary", regex=NOISE_REGEX))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToMatchRegex(column="published", regex=DATE_REGEX))
    return suite


def _run_gx(df: pd.DataFrame, report_name: str) -> tuple[bool, list[dict[str, Any]]]:
    """Validate `df` with a GX 1.x ephemeral context (no file-based project needed)."""
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})
    suite = context.suites.add(_build_suite(report_name))
    validation = batch.validate(suite)

    results = []
    for item in validation.results:
        config = item.expectation_config
        kwargs = {key: value for key, value in config.kwargs.items() if key != "batch_id"}
        observed = item.result or {}
        results.append(
            {
                "expectation": config.type,
                "column": kwargs.get("column"),
                "kwargs": kwargs,
                "success": bool(item.success),
                "observed_value": observed.get("observed_value"),
                "unexpected_count": observed.get("unexpected_count"),
                "unexpected_percent": observed.get("unexpected_percent"),
                "partial_unexpected_list": (observed.get("partial_unexpected_list") or [])[:5],
            }
        )
    return bool(validation.success), _json_safe(results)


def _source_reconciliation(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    """Completeness check: every valid record in the raw source must reach the dataset."""
    raw_path = settings.paths.raw_records_json
    if not raw_path.exists():
        return {"check": "source_reconciliation", "success": True, "skipped": "raw records not found"}

    from ingestion.cleaning import build_clean_dataframe
    from ingestion.crossref import load_raw_records

    expected = set(build_clean_dataframe(load_raw_records(raw_path), now_utc())["paper_id"])
    present = set(df["paper_id"].dropna().astype(str).str.lower())
    missing = sorted(expected - present)
    coverage = 1.0 if not expected else (len(expected) - len(missing)) / len(expected)
    return {
        "check": "source_reconciliation",
        "success": coverage >= MIN_SOURCE_COVERAGE,
        "min_coverage": MIN_SOURCE_COVERAGE,
        "coverage": round(coverage, 4),
        "expected_papers": len(expected),
        "unique_papers": len(present),
        "missing_count": len(missing),
        "missing_paper_ids": missing,
    }


def _freshness(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    threshold = settings.freshness_threshold_days
    ages = pd.to_numeric(df["age_days"], errors="coerce") if "age_days" in df else pd.Series(dtype=float)
    published = pd.to_datetime(df.get("published", pd.Series(dtype=str)), errors="coerce")
    total = int(len(df))
    stale = int((ages > threshold).sum())
    ratio = stale / total if total else 1.0
    return {
        "threshold_days": threshold,
        "max_stale_ratio": MAX_STALE_RATIO,
        "total_rows": total,
        "stale_rows": stale,
        "stale_ratio": round(ratio, 4),
        "latest_published": published.max().strftime("%Y-%m-%d") if published.notna().any() else None,
        "oldest_published": published.min().strftime("%Y-%m-%d") if published.notna().any() else None,
        "latest_age_days": int(ages.min()) if ages.notna().any() else None,
        "median_age_days": float(ages.median()) if ages.notna().any() else None,
        "max_age_days": int(ages.max()) if ages.notna().any() else None,
        "is_fresh": total > 0 and ratio <= MAX_STALE_RATIO,
    }


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Quality gate = GX 1.x expectations + source reconciliation. Freshness is reported as a separate SLA signal."""
    gx_success, expectations = _run_gx(df, report_name)
    reconciliation = _source_reconciliation(df, settings)
    freshness = _freshness(df, settings)
    failed = [
        f"{item['expectation']}({item['column']})" if item["column"] else item["expectation"]
        for item in expectations
        if not item["success"]
    ]
    if not reconciliation["success"]:
        failed.append("source_reconciliation")

    report = {
        "report_name": report_name,
        "generated_at": now_utc().isoformat(),
        "engine": f"great_expectations {gx.__version__} (ephemeral context)",
        "row_count": int(len(df)),
        "success": gx_success and reconciliation["success"],
        "gx_success": gx_success,
        "statistics": {
            "evaluated_checks": len(expectations) + 1,
            "successful_checks": len(expectations) + 1 - len(failed),
            "failed_checks": len(failed),
        },
        "failed_checks": failed,
        "expectations": expectations,
        "source_reconciliation": reconciliation,
        "freshness": freshness,
    }
    write_json(_quality_report_path(settings, report_name), report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Freshness SLA: alert (`is_fresh=False`) when more than 25% of papers are older than the threshold."""
    payload = {"generated_at": now_utc().isoformat(), **_freshness(df, settings)}
    ages = pd.to_numeric(df["age_days"], errors="coerce").dropna() if "age_days" in df else pd.Series(dtype=float)
    bins = [(-10**6, 30, "0-30"), (30, 90, "31-90"), (90, 180, "91-180"), (180, 365, "181-365"), (365, 10**6, ">365")]
    payload["age_distribution"] = {label: int(((ages > low) & (ages <= high)).sum()) for low, high, label in bins}
    payload["alert"] = (
        None
        if payload["is_fresh"]
        else f"{payload['stale_rows']}/{payload['total_rows']} papers older than "
        f"{payload['threshold_days']} days (> {MAX_STALE_RATIO:.0%}); refresh the source."
    )
    write_json(Path(report_path), payload)
    return payload
