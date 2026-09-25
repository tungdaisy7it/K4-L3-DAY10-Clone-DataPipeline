from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import METRIC_KEYS, generate_corruption_report
from pipelines.common import dataframe_fingerprint, file_sha256, load_dataframe, save_dataframe
from retrieval.index import LocalEmbeddingIndex


def repair_from_raw(settings: Settings, run_date: datetime) -> pd.DataFrame:
    """Idempotent repair: rebuild the clean dataset from the preserved raw records, never patch the corrupted copy."""
    return build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), run_date)


def _gate_alerts(quality: dict[str, Any], freshness: dict[str, Any]) -> list[str]:
    alerts = [f"quality check failed: {name}" for name in quality["failed_checks"]]
    if not freshness["is_fresh"]:
        alerts.append(f"freshness SLA breached: {freshness['alert']}")
    return alerts


def _print_comparison(states: dict[str, dict[str, Any]]) -> None:
    header = f"{'metric':<22}{'baseline':>12}{'corrupted':>12}{'repaired':>12}"
    print("\n" + header + "\n" + "-" * len(header))
    for key in METRIC_KEYS:
        values = [states[s]["metrics"][key] for s in ("baseline", "corrupted", "repaired")]
        print(f"{key:<22}" + "".join(f"{v:>12.4f}" for v in values))
    for label, getter in (
        ("quality_gate", lambda s: "PASS" if s["quality"]["success"] else "FAIL"),
        ("is_fresh", lambda s: str(s["freshness"]["is_fresh"])),
        ("rows", lambda s: str(s["quality"]["row_count"])),
    ):
        print(f"{label:<22}" + "".join(f"{getter(states[s]):>12}" for s in ("baseline", "corrupted", "repaired")))
    print()


def main(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    paths = settings.paths
    run_date = now_utc()
    required = [
        paths.clean_json,
        paths.eval_testset,
        paths.baseline_metrics,
        paths.baseline_answers,
        paths.raw_records_json,
    ]
    missing = [p.name for p in required if not p.exists()]
    if missing:
        raise SystemExit(f"[corruption] Missing baseline artifacts {missing}. Run `python script/run_phase1.py` first.")

    print("[corruption] 1/6 Load baseline artifacts")
    baseline_df = load_dataframe(paths.clean_json)
    baseline_metrics = read_json(paths.baseline_metrics)
    baseline_answers = read_json(paths.baseline_answers)
    baseline_quality = (
        read_json(paths.baseline_quality_report)
        if paths.baseline_quality_report.exists()
        else run_data_quality_checks(baseline_df, settings, "baseline")
    )
    baseline_freshness = (
        read_json(paths.freshness_report)
        if paths.freshness_report.exists()
        else build_freshness_report(baseline_df, settings, paths.freshness_report)
    )

    print("[corruption] 2/6 Inject 6 corruption scenarios")
    corrupted_df = corrupt_clean_dataframe(baseline_df, paths.corruption_log)
    save_dataframe(corrupted_df, paths.corrupted_clean_csv, paths.corrupted_clean_json)
    corruption_log = read_json(paths.corruption_log)
    print(f"  {corruption_log['input_rows']} -> {corruption_log['output_rows']} rows, "
          f"types: {[c['type'] for c in corruption_log['corruptions']]}")

    print("[corruption] 3/6 Observability gate on corrupted data")
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, paths.quality_dir / "corrupted_freshness_report.json"
    )
    alerts = _gate_alerts(corrupted_quality, corrupted_freshness)
    for alert in alerts:
        print(f"  [ALERT] {alert}")

    print("[corruption] 4/6 Silent-failure measurement (corrupted data indexed in an isolated collection)")
    corrupted_index = LocalEmbeddingIndex.build(corrupted_df, settings, paths.corrupted_embeddings_json)
    corrupted_eval = evaluate_pipeline(
        settings, corrupted_index, paths.eval_testset, paths.corrupted_metrics, paths.corrupted_answers
    )

    print("[corruption] 5/6 Auto-repair from raw snapshot")
    trigger = "gate tripped: " + "; ".join(alerts) if alerts else "manual (gate did not trip)"
    repaired_df = repair_from_raw(settings, run_date)
    second_pass = repair_from_raw(settings, run_date)
    save_dataframe(repaired_df, paths.repaired_clean_csv, paths.repaired_clean_json)
    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness = build_freshness_report(
        repaired_df, settings, paths.quality_dir / "repaired_freshness_report.json"
    )
    if not repaired_quality["success"]:
        raise SystemExit(f"[corruption] Repair did not pass the quality gate: {repaired_quality['failed_checks']}")
    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, paths.repaired_embeddings_json)
    repaired_eval = evaluate_pipeline(
        settings, repaired_index, paths.eval_testset, paths.repaired_metrics, paths.repaired_answers
    )
    repaired_fp = dataframe_fingerprint(repaired_df)
    repair_summary = {
        "trigger": trigger,
        "source": paths.raw_records_json.relative_to(paths.project_dir).as_posix(),
        "raw_records_sha256": file_sha256(paths.raw_records_json)[:16],
        "repaired_rows": len(repaired_df),
        "repaired_fingerprint": repaired_fp[:16],
        "idempotent (2 repair runs identical)": repaired_fp == dataframe_fingerprint(second_pass),
        "matches baseline content": repaired_fp == dataframe_fingerprint(baseline_df),
        "repaired_collection": repaired_index.collection_name,
        "repaired_vectors": repaired_index.collection.count(),
    }
    for key, value in repair_summary.items():
        print(f"  {key}: {value}")

    print("[corruption] 6/6 Comparison report")
    generate_corruption_report(
        paths.comparison_report,
        baseline_metrics,
        corrupted_eval.summary,
        repaired_eval.summary,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
        baseline_quality=baseline_quality,
        baseline_freshness=baseline_freshness,
        corruption_log=corruption_log,
        answers={"baseline": baseline_answers, "corrupted": corrupted_eval.answers, "repaired": repaired_eval.answers},
        repair_summary=repair_summary,
    )
    states = {
        "baseline": {"metrics": baseline_metrics, "quality": baseline_quality, "freshness": baseline_freshness},
        "corrupted": {"metrics": corrupted_eval.summary, "quality": corrupted_quality, "freshness": corrupted_freshness},
        "repaired": {"metrics": repaired_eval.summary, "quality": repaired_quality, "freshness": repaired_freshness},
    }
    _print_comparison(states)
    print(f"[corruption] DONE report -> {paths.comparison_report.relative_to(paths.project_dir).as_posix()}")
    return {state: values["metrics"] for state, values in states.items()}
